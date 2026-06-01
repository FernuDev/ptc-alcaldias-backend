"""Orquestador del Agente Institucional.

Une, en este orden: contexto de permisos → recuperación RAG filtrada →
construcción del prompt → LLM → bitácora. El LLM nunca ve fragmentos fuera del
alcance del usuario.
"""

import json
import re
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from app.agente import tools
from app.agente.context import UsuarioContexto, derive_contexto
from app.agente.llm.base import LLMClient, Message
from app.agente.llm.factory import get_llm_client
from app.agente.prompts.system_prompt import SYSTEM_PROMPT
from app.agente.rag.permissions import build_chroma_where, filtrar_candidatos
from app.agente.rag.store import VectorStore, get_store
from app.models.agente_interaccion import AgenteInteraccion
from app.models.user import User
from app.schemas.agente import ChatResponse, ClassifyResponse, Fuente, Navegacion

NO_SE = (
    "No tengo esa información en la base de conocimiento disponible para tu "
    "alcance. Te sugiero consultarlo con el área correspondiente."
)

# Máximo de rondas de herramientas antes de forzar una respuesta final.
MAX_TOOL_ROUNDS = 4

# Nota que habilita al modelo a consultar datos en vivo con herramientas.
HERRAMIENTAS_NOTA = (
    "## Herramientas\n"
    "Dispones de herramientas para consultar datos EN VIVO del sistema, siempre "
    "limitadas a tu alcance: consultar_reporte (por folio o id), buscar_reportes, "
    "consultar_obra y metricas. También puedes NAVEGAR: usa la herramienta 'navegar' "
    "para abrir una pantalla del sistema (dashboard, bandeja, reportes, obras, personal, "
    "configuracion) o el detalle de un reporte/obra; el usuario verá un botón para abrirla. "
    "Úsalas cuando te pregunten por un folio, caso, obra o cifra, o cuando pidan ver/ir a "
    "una pantalla. La regla de 'responder solo con información disponible' incluye los "
    "resultados de estas herramientas además de la base de conocimiento. Si una herramienta "
    "no devuelve datos, dilo claramente; no inventes."
)

# Palabras que fuerzan marcado de emergencia/sensibilidad (red de seguridad
# independiente del criterio del modelo).
_EMERGENCIA_KW = (
    "arma", "disparo", "balacera", "violencia", "golpe", "sangre", "herido",
    "muerto", "incendio", "fuego", "explosión", "explosion", "secuestro",
    "amenaza", "suicid", "ahogad", "cadáver", "cadaver",
)


# ─── Helpers de prompt ─────────────────────────────────────────────────────


def _bloque_usuario(ctx: UsuarioContexto) -> str:
    areas = ", ".join(ctx.areas) if ctx.areas else "todas (alcance global)"
    return (
        "## Usuario actual (no excedas este alcance)\n"
        f"- rol: {ctx.rol}\n"
        f"- alcance_datos: {ctx.alcance_datos}\n"
        f"- tenant: {ctx.tenant_id}\n"
        f"- areas: {areas}\n"
        f"- seguridad_reservada: {str(ctx.seguridad_reservada).lower()}"
    )


def _bloque_contexto(frags: list[dict]) -> str:
    if not frags:
        return ""
    lineas = []
    for i, f in enumerate(frags, 1):
        m = f.get("metadata", {})
        lineas.append(f"[{i}] ({m.get('titulo')} · {m.get('seccion')})\n{f.get('document', '')}")
    return "# CONTEXTO RECUPERADO (responde solo con esto y cita las fuentes [n])\n" + "\n\n".join(
        lineas
    )


def construir_mensajes(
    ctx: UsuarioContexto,
    mensaje: str,
    historial: list[Message],
    frags: list[dict],
) -> list[Message]:
    mensajes: list[Message] = [
        {
            "role": "system",
            "content": f"{SYSTEM_PROMPT}\n\n{_bloque_usuario(ctx)}\n\n{HERRAMIENTAS_NOTA}",
        }
    ]
    bloque = _bloque_contexto(frags)
    if bloque:
        mensajes.append({"role": "system", "content": bloque})
    mensajes.extend(historial)
    mensajes.append({"role": "user", "content": mensaje})
    return mensajes


def recuperar(
    ctx: UsuarioContexto, consulta: str, *, k: int = 5, store: VectorStore | None = None
) -> list[dict]:
    """Recupera fragmentos del RAG ya filtrados por permisos (doble barrera)."""
    store = store or get_store()
    try:
        crudos = store.query(consulta, n_results=k, where=build_chroma_where(ctx))
    except Exception:
        crudos = []
    return filtrar_candidatos(ctx, crudos)


def _fuentes(frags: list[dict]) -> list[Fuente]:
    vistos: dict[str, Fuente] = {}
    for f in frags:
        m = f.get("metadata", {})
        doc_id = m.get("documento_id", "")
        if doc_id in vistos:
            continue
        dist = f.get("distance")
        vistos[doc_id] = Fuente(
            documento_id=doc_id,
            titulo=m.get("titulo", "Documento"),
            seccion=m.get("seccion"),
            nivel=m.get("nivel", "interno"),
            score=round(1 - dist, 3) if isinstance(dist, int | float) else None,
        )
    return list(vistos.values())


def _fuentes_tools(usadas: list[str]) -> list[Fuente]:
    """Fuente sintética por cada herramienta usada (chip 'consulta en vivo')."""
    out: list[Fuente] = []
    for name in dict.fromkeys(usadas):  # únicos, preservando orden
        out.append(
            Fuente(
                documento_id=f"tool:{name}",
                titulo=f"{tools.ETIQUETAS.get(name, name)} · consulta en vivo",
                seccion=None,
                nivel="interno",
                score=None,
            )
        )
    return out


async def _loop_tools(
    llm: LLMClient,
    mensajes: list[Message],
    user: User,
    db: AsyncSession,
) -> tuple[str, list[str], list[Navegacion]]:
    """Ciclo de tool-calling: el modelo pide herramientas, se ejecutan con el
    alcance del usuario y se le devuelven, hasta que produce una respuesta final.
    Devuelve (texto_final, herramientas_usadas, navegaciones)."""
    usadas: list[str] = []
    navegaciones: list[Navegacion] = []
    for _ in range(MAX_TOOL_ROUNDS):
        res = await llm.complete(mensajes, tools=tools.TOOLS_SCHEMA)
        if not res.tool_calls:
            return res.content or "", usadas, navegaciones

        mensajes.append(
            {
                "role": "assistant",
                "content": res.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": tc.arguments},
                    }
                    for tc in res.tool_calls
                ],
            }
        )
        for tc in res.tool_calls:
            usadas.append(tc.name)
            try:
                args = json.loads(tc.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            salida = await tools.ejecutar_tool(tc.name, args, user, db)
            if isinstance(salida, dict) and isinstance(salida.get("navegacion"), dict):
                navegaciones.append(Navegacion(**salida["navegacion"]))
            mensajes.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(salida, ensure_ascii=False, default=str),
                }
            )

    # Límite alcanzado: forzar respuesta final sin más herramientas.
    res = await llm.complete(mensajes)
    return res.content or "", usadas, navegaciones


async def _registrar(
    db: AsyncSession,
    ctx: UsuarioContexto,
    *,
    canal: str,
    pregunta: str,
    respuesta: str,
    fuentes: list[Fuente],
    sin_informacion: bool,
) -> None:
    db.add(
        AgenteInteraccion(
            user_id=ctx.id,
            tenant_id=ctx.tenant_id,
            rol=ctx.rol,
            canal=canal,
            pregunta=pregunta[:8000],
            respuesta=respuesta[:8000],
            fuentes=[f.model_dump() for f in fuentes] or None,
            sin_informacion=sin_informacion,
        )
    )
    await db.flush()


# ─── Casos de uso ──────────────────────────────────────────────────────────


async def responder_chat(
    db: AsyncSession,
    user: User,
    mensaje: str,
    historial: list[Message] | None = None,
    *,
    store: VectorStore | None = None,
    llm: LLMClient | None = None,
) -> ChatResponse:
    ctx = derive_contexto(user)
    historial = historial or []
    llm = llm or get_llm_client()

    frags = recuperar(ctx, mensaje, store=store)
    mensajes = construir_mensajes(ctx, mensaje, historial, frags)
    texto, usadas, navegacion = await _loop_tools(llm, mensajes, user, db)

    fuentes = _fuentes(frags) + _fuentes_tools(usadas)
    sin_info = len(frags) == 0 and len(usadas) == 0
    await _registrar(
        db, ctx, canal="chat", pregunta=mensaje, respuesta=texto,
        fuentes=fuentes, sin_informacion=sin_info,
    )
    return ChatResponse(
        respuesta=texto, fuentes=fuentes, sin_informacion=sin_info, navegacion=navegacion
    )


async def stream_chat(
    db: AsyncSession,
    user: User,
    mensaje: str,
    historial: list[Message] | None = None,
    *,
    store: VectorStore | None = None,
    llm: LLMClient | None = None,
) -> AsyncIterator[dict]:
    """Emite eventos estructurados (SSE) y registra la bitácora al final.

    Resuelve primero las herramientas (no-streaming) y luego transmite la
    respuesta final por palabras, para preservar el efecto de tipeo sin pagar
    una segunda llamada al modelo. Cada evento es un dict:
      - {"delta": "<texto>"}                          fragmento de respuesta
      - {"fuentes": [...], "sin_informacion": bool}    evento final con citas
    """
    ctx = derive_contexto(user)
    historial = historial or []
    llm = llm or get_llm_client()

    frags = recuperar(ctx, mensaje, store=store)
    mensajes = construir_mensajes(ctx, mensaje, historial, frags)
    texto, usadas, navegacion = await _loop_tools(llm, mensajes, user, db)

    for parte in re.findall(r"\S+\s*", texto):
        yield {"delta": parte}

    fuentes = _fuentes(frags) + _fuentes_tools(usadas)
    sin_info = len(frags) == 0 and len(usadas) == 0
    yield {
        "fuentes": [f.model_dump() for f in fuentes],
        "sin_informacion": sin_info,
        "navegacion": [n.model_dump() for n in navegacion],
    }

    await _registrar(
        db, ctx, canal="chat", pregunta=mensaje, respuesta=texto,
        fuentes=fuentes, sin_informacion=sin_info,
    )


def _detectar_emergencia(texto: str) -> bool:
    t = texto.lower()
    return any(kw in t for kw in _EMERGENCIA_KW)


async def clasificar_reporte(
    db: AsyncSession,
    ctx: UsuarioContexto,
    descripcion: str,
    categorias_validas: list[str],
    *,
    llm: LLMClient | None = None,
) -> ClassifyResponse:
    llm = llm or get_llm_client()

    instruccion = (
        f"{SYSTEM_PROMPT}\n\n{_bloque_usuario(ctx)}\n\n"
        "# TAREA: CLASIFICACIÓN\n"
        "Clasifica el siguiente reporte ciudadano. Responde SOLO con un objeto JSON "
        "con las claves: categoria_sugerida (una de: "
        f"{', '.join(categorias_validas)}), prioridad_sugerida "
        "(baja|media|alta|critica), es_sensible (bool), es_emergencia (bool), "
        "canal_recomendado (string o null), justificacion (string breve)."
    )
    mensajes: list[Message] = [
        {"role": "system", "content": instruccion},
        {"role": "user", "content": descripcion},
    ]
    crudo = await llm.chat(mensajes)

    datos = _parse_json_laxo(crudo)
    categoria = datos.get("categoria_sugerida")
    if categoria not in categorias_validas:
        categoria = _heuristica_categoria(descripcion, categorias_validas)

    prioridad = datos.get("prioridad_sugerida")
    if prioridad not in ("baja", "media", "alta", "critica"):
        prioridad = "media"

    # Red de seguridad: las palabras de emergencia mandan sobre el modelo.
    emergencia = bool(datos.get("es_emergencia")) or _detectar_emergencia(descripcion)
    sensible = bool(datos.get("es_sensible")) or emergencia
    canal = datos.get("canal_recomendado")
    if emergencia and not canal:
        canal = "911 / línea de emergencias"

    resp = ClassifyResponse(
        categoria_sugerida=categoria,
        prioridad_sugerida="critica" if emergencia else prioridad,
        es_sensible=sensible,
        es_emergencia=emergencia,
        canal_recomendado=canal,
        justificacion=(
            datos.get("justificacion") or "Clasificación preliminar; requiere validación humana."
        ),
    )
    await _registrar(
        db, ctx, canal="classify", pregunta=descripcion, respuesta=resp.model_dump_json(),
        fuentes=[], sin_informacion=False,
    )
    return resp


def _parse_json_laxo(texto: str) -> dict:
    """Extrae el primer objeto JSON del texto del modelo; {} si no hay."""
    try:
        inicio = texto.index("{")
        fin = texto.rindex("}") + 1
        return json.loads(texto[inicio:fin])
    except (ValueError, json.JSONDecodeError):
        return {}


def _heuristica_categoria(descripcion: str, categorias_validas: list[str]) -> str:
    """Fallback por palabras clave si el modelo no devuelve una categoría válida."""
    t = descripcion.lower()
    reglas = {
        "bacheo": ("bache", "pavimento", "hoyo", "carpeta"),
        "alumbrado": ("luminaria", "foco", "alumbrado", "lámpara", "lampara"),
        "semaforos": ("semáforo", "semaforo"),
        "agua": ("agua", "fuga", "tinaco", "suministro"),
        "drenaje": ("drenaje", "coladera", "alcantarilla", "atarjea"),
        "limpia": ("basura", "limpia", "residuos"),
        "comercio_vp": ("ambulante", "comercio", "puesto"),
        "parques": ("parque", "jardín", "jardin", "cancha"),
        "arboles": ("árbol", "arbol", "poda", "rama"),
        "seguridad": ("robo", "asalto", "seguridad", "vandal"),
    }
    for cat, kws in reglas.items():
        if cat in categorias_validas and any(k in t for k in kws):
            return cat
    return categorias_validas[0] if categorias_validas else "otros"
