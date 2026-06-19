"""Acciones con confirmación humana (human-in-the-loop).

El agente nunca muta el sistema directamente:
1. `preparar_accion` valida el alcance (vía los services, que aplican tenant+área),
   persiste una propuesta `pendiente` y la devuelve SIN ejecutarla.
2. `confirmar_accion` ejecuta esa propuesta — y solo entonces — reutilizando los
   services existentes (que vuelven a validar y registran auditoría).

Además expone dos análisis de IA reutilizables (lectura, sin mutación):
- `detectar_duplicados`: heurística sólida (misma categoría + cercanía geográfica
  + ventana temporal + similitud de texto difusa) para encontrar reportes que
  probablemente describen el mismo incidente.
- `sugerir_reclasificacion`: propone categoría/prioridad apoyándose en el
  clasificador del Agente Cívico (LLM + red de seguridad por keywords).
"""

import math
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agente.context import UsuarioContexto, derive_contexto
from app.core.audit import AuditLogger
from app.models.agente_accion import AgenteAccion
from app.models.user import User
from app.schemas.agente import ConfirmActionResponse, PreparedAction
from app.schemas.obra import ObraUpdate
from app.schemas.reporte import ReporteRead, ReporteUpdate
from app.services import obra_service, reporte_service

VIGENCIA = timedelta(minutes=15)

# Campos que cada entidad acepta en su Update (se filtra el payload por seguridad).
_CAMPOS_REPORTE = {"estado", "prioridad", "cuadrilla_id", "costo_estimado", "gasto_real"}
_CAMPOS_OBRA = {
    "estado", "prioridad", "avance_pct", "presupuesto_ejercido", "contratista_id", "fecha_fin_real"
}


def _now() -> datetime:
    return datetime.now(UTC)


def _payload_y_descripcion(tipo: str, entity_type: str, params: dict) -> tuple[dict, str]:
    """Traduce (tipo, params) a un payload de cambios + descripción legible."""
    cerrar_estado = "concluida" if entity_type == "obra" else "cerrado"

    if tipo == "cerrar":
        return {"estado": cerrar_estado}, f"Cerrar {entity_type} (estado → {cerrar_estado})"
    if tipo == "cambiar_estado":
        nuevo = params.get("estado")
        return {"estado": nuevo}, f"Cambiar estado de {entity_type} a '{nuevo}'"
    if tipo in ("asignar", "turnar"):
        if entity_type == "obra":
            cid = params.get("contratista_id")
            return {"contratista_id": cid}, f"Turnar obra al contratista '{cid}'"
        cid = params.get("cuadrilla_id")
        return {"cuadrilla_id": cid, "estado": "asignado"}, f"Turnar reporte a la cuadrilla '{cid}'"
    if tipo == "borrador":
        return {"borrador": params.get("texto", "")}, f"Borrador preparado para {entity_type}"
    raise ValueError(f"Tipo de acción no soportado: {tipo!r}")


async def preparar_accion(
    db: AsyncSession,
    ctx: UsuarioContexto,
    user: User,
    *,
    tipo: str,
    entity_type: str,
    entity_id: str,
    params: dict,
) -> PreparedAction:
    # Validación de alcance: si está fuera del tenant/área del usuario, estos
    # services lanzan NotFoundError (→ 404) antes de preparar nada.
    if entity_type == "reporte":
        await reporte_service.get_reporte(entity_id, user, db)
    elif entity_type == "obra":
        await obra_service.get_obra(entity_id, user, db)
    else:
        raise ValueError(f"entity_type no soportado: {entity_type!r}")

    payload, descripcion = _payload_y_descripcion(tipo, entity_type, params)

    accion = AgenteAccion(
        user_id=ctx.id,
        tenant_id=ctx.tenant_id,
        tipo=tipo,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload,
        estado="pendiente",
        expires_at=_now() + VIGENCIA,
    )
    db.add(accion)
    await db.flush()

    return PreparedAction(
        accion_id=accion.id,
        tipo=tipo,
        entity_type=entity_type,
        entity_id=entity_id,
        descripcion=descripcion,
        payload=payload,
    )


async def confirmar_accion(
    db: AsyncSession,
    ctx: UsuarioContexto,
    user: User,
    accion_id: str,
    audit: AuditLogger,
) -> ConfirmActionResponse:
    accion = (
        await db.execute(
            select(AgenteAccion).where(
                AgenteAccion.id == accion_id, AgenteAccion.user_id == ctx.id
            )
        )
    ).scalar_one_or_none()

    if accion is None:
        return ConfirmActionResponse(
            accion_id=accion_id,
            estado="no_encontrada",
            detalle="Acción inexistente o de otro usuario.",
        )
    if accion.estado != "pendiente":
        return ConfirmActionResponse(
            accion_id=accion_id, estado="error", detalle=f"La acción ya está '{accion.estado}'."
        )
    if accion.expires_at < _now():
        accion.estado = "expirada"
        await db.flush()
        return ConfirmActionResponse(
            accion_id=accion_id,
            estado="expirada",
            detalle="La propuesta caducó; vuelve a prepararla.",
        )

    # Ejecución real (salvo borradores, que no mutan el sistema).
    if accion.tipo != "borrador":
        cambios = accion.payload
        if accion.entity_type == "reporte":
            data = ReporteUpdate(**{k: v for k, v in cambios.items() if k in _CAMPOS_REPORTE})
            await reporte_service.update_reporte(accion.entity_id, data, user, db, audit)
        elif accion.entity_type == "obra":
            data = ObraUpdate(**{k: v for k, v in cambios.items() if k in _CAMPOS_OBRA})
            await obra_service.update_obra(accion.entity_id, data, user, db, audit)

    accion.estado = "confirmada"
    accion.confirmed_at = _now()
    await audit.log(
        action="agente_confirm",
        user_id=ctx.id,
        tenant_id=ctx.tenant_id,
        entity_type=accion.entity_type,
        entity_id=accion.entity_id,
        extra={"tipo": accion.tipo, "accion_id": accion.id, "payload": accion.payload},
    )
    await db.flush()

    return ConfirmActionResponse(
        accion_id=accion_id, estado="confirmada", detalle=f"Acción '{accion.tipo}' ejecutada."
    )


# ─── Detección de duplicados ───────────────────────────────────────────────
#
# Heurística de varios factores (sin servicios externos): dos reportes son
# probablemente el mismo incidente si comparten categoría, ocurren cerca en el
# espacio (≲ ~150 m) y en el tiempo (ventana configurable), y describen lo mismo
# (similitud difusa de título/descripción). Cada factor aporta a un score 0–1 y
# se combina con una etiqueta de confianza explicable.

# Parámetros por defecto (ajustables por el llamador).
RADIO_DUPLICADO_M = 150.0
VENTANA_DUPLICADO = timedelta(days=7)
UMBRAL_DUPLICADO = 0.55  # score mínimo para reportar un candidato

# Estados que ya no compiten como "duplicado abierto" pero siguen siendo útiles
# como referencia histórica; se incluyen con menor peso.
_ESTADOS_ABIERTOS = {"nuevo", "asignado", "en_proceso"}

_STOPWORDS = {
    "de", "la", "el", "en", "y", "a", "los", "las", "un", "una", "por", "con",
    "que", "del", "se", "su", "para", "al", "lo", "le", "es", "hay", "como",
    "esta", "este", "muy", "no", "si", "sobre", "entre", "calle", "colonia",
}


@dataclass
class CandidatoDuplicado:
    """Un reporte candidato a duplicar al reporte de referencia."""

    reporte: ReporteRead
    score: float
    confianza: str  # alta | media | baja
    distancia_m: float | None
    horas_diferencia: float | None
    similitud_texto: float
    misma_categoria: bool
    misma_colonia: bool
    motivos: list[str] = field(default_factory=list)


def _normalizar(texto: str | None) -> str:
    if not texto:
        return ""
    t = unicodedata.normalize("NFKD", texto.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9áéíóúñ ]", " ", t)).strip()


def _tokens(texto: str) -> set[str]:
    return {w for w in _normalizar(texto).split() if len(w) > 2 and w not in _STOPWORDS}


def _similitud_texto(a: str, b: str) -> float:
    """Similitud difusa 0–1: media de Jaccard de tokens y ratio de secuencia.

    Combina dos señales complementarias: solapamiento de vocabulario (robusto a
    reordenamientos) y similitud de secuencia (sensible a frases idénticas).
    """
    na, nb = _normalizar(a), _normalizar(b)
    if not na or not nb:
        return 0.0
    ta, tb = _tokens(a), _tokens(b)
    jaccard = len(ta & tb) / len(ta | tb) if (ta or tb) else 0.0
    ratio = SequenceMatcher(None, na, nb).ratio()
    return round((jaccard + ratio) / 2, 3)


def _distancia_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Distancia Haversine en metros entre dos coordenadas."""
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return r * 2 * math.atan2(math.sqrt(h), math.sqrt(1 - h))


def _puntuar_candidato(
    base: ReporteRead,
    cand: ReporteRead,
    *,
    radio_m: float,
    ventana: timedelta,
) -> CandidatoDuplicado | None:
    """Calcula el score de duplicado de `cand` respecto a `base`.

    Devuelve ``None`` cuando ni la geografía ni la colonia ni el texto dan
    señal alguna (no es candidato).
    """
    motivos: list[str] = []
    misma_categoria = base.categoria_id == cand.categoria_id
    misma_colonia = base.colonia_id == cand.colonia_id

    # 1) Geografía.
    distancia = None
    score_geo = 0.0
    lejos_fisicamente = False
    if None not in (base.lat, base.lng, cand.lat, cand.lng):
        distancia = _distancia_m(base.lat, base.lng, cand.lat, cand.lng)
        if distancia <= radio_m:
            score_geo = 1.0 - (distancia / radio_m)  # 1 en el mismo punto, 0 en el borde
            motivos.append(f"a {distancia:.0f} m de distancia")
        else:
            # Hay coordenadas válidas y están claramente lejos: no es el mismo punto.
            lejos_fisicamente = True
    if score_geo == 0.0 and misma_colonia:
        # Sin cercanía por coordenadas pero misma colonia: señal geográfica débil.
        score_geo = 0.35
        lejos_fisicamente = False
        motivos.append("misma colonia")

    # 2) Tiempo.
    horas = None
    score_tiempo = 0.0
    if base.fecha_creacion and cand.fecha_creacion:
        delta = abs(base.fecha_creacion - cand.fecha_creacion)
        horas = delta.total_seconds() / 3600
        if delta <= ventana:
            score_tiempo = 1.0 - (delta / ventana)
            if horas < 24:
                motivos.append(f"reportado con {horas:.0f} h de diferencia")
            else:
                motivos.append(f"reportado a {horas / 24:.0f} día(s) de diferencia")

    # 3) Texto.
    sim_texto = max(
        _similitud_texto(base.titulo, cand.titulo),
        _similitud_texto(
            f"{base.titulo} {base.descripcion or ''}",
            f"{cand.titulo} {cand.descripcion or ''}",
        ),
    )
    if sim_texto >= 0.5:
        motivos.append(f"texto {int(sim_texto * 100)}% similar")

    # 4) Categoría.
    score_cat = 1.0 if misma_categoria else 0.0
    if misma_categoria:
        motivos.append("misma categoría")

    # Si no hay ninguna señal espacial ni textual, no es candidato.
    if score_geo == 0.0 and sim_texto < 0.45:
        return None

    # Combinación ponderada (geografía y categoría pesan más por ser las señales
    # más fiables de "mismo incidente físico").
    score = (
        0.32 * score_geo
        + 0.22 * score_cat
        + 0.20 * score_tiempo
        + 0.26 * sim_texto
    )
    # Penaliza si la categoría difiere: rara vez el mismo incidente cambia de área.
    if not misma_categoria:
        score *= 0.7
    # Penaliza si hay coordenadas válidas pero el reporte está físicamente lejos
    # (fuera del radio y en otra colonia): probablemente un incidente distinto del
    # mismo tipo, no un duplicado. Lo mantiene como candidato de baja confianza.
    if lejos_fisicamente and not misma_colonia:
        score *= 0.6

    score = round(min(score, 1.0), 3)
    if score >= 0.75:
        confianza = "alta"
    elif score >= 0.6:
        confianza = "media"
    else:
        confianza = "baja"

    return CandidatoDuplicado(
        reporte=cand,
        score=score,
        confianza=confianza,
        distancia_m=round(distancia, 1) if distancia is not None else None,
        horas_diferencia=round(horas, 1) if horas is not None else None,
        similitud_texto=sim_texto,
        misma_categoria=misma_categoria,
        misma_colonia=misma_colonia,
        motivos=motivos,
    )


async def detectar_duplicados(
    reporte_id: str,
    user: User,
    db: AsyncSession,
    *,
    radio_m: float = RADIO_DUPLICADO_M,
    ventana: timedelta = VENTANA_DUPLICADO,
    umbral: float = UMBRAL_DUPLICADO,
    limite: int = 10,
) -> tuple[ReporteRead, list[CandidatoDuplicado]]:
    """Detecta posibles duplicados de un reporte dentro del alcance del usuario.

    Reutiliza ``reporte_service`` (tenant + área), por lo que nunca devuelve
    reportes fuera del alcance. Devuelve el reporte base y los candidatos
    ordenados por score descendente.
    """
    base = await reporte_service.get_reporte(reporte_id, user, db)

    # Universo: misma categoría (canal más probable) en una ventana amplia.
    # Pedimos una página generosa y filtramos en memoria por score; el volumen
    # por categoría/tenant es manejable para una demo y evita SQL geoespacial.
    pag = await reporte_service.list_reportes(
        user,
        db,
        page_size=200,
        categorias=[base.categoria_id],
        sort_by="fecha_creacion",
        sort_dir="desc",
    )

    candidatos: list[CandidatoDuplicado] = []
    for cand in pag.items:
        if cand.id == base.id:
            continue
        c = _puntuar_candidato(base, cand, radio_m=radio_m, ventana=ventana)
        if c and c.score >= umbral:
            candidatos.append(c)

    candidatos.sort(key=lambda c: c.score, reverse=True)
    return base, candidatos[:limite]


# ─── Sugerencia de reclasificación ─────────────────────────────────────────


@dataclass
class SugerenciaReclasificacion:
    """Propuesta de categoría/prioridad para un reporte (no se aplica sola)."""

    reporte_id: str
    folio: str
    titulo: str
    categoria_actual: str
    categoria_sugerida: str
    cambia_categoria: bool
    prioridad_actual: str
    prioridad_sugerida: str
    cambia_prioridad: bool
    es_emergencia: bool
    es_sensible: bool
    justificacion: str


async def sugerir_reclasificacion(
    reporte_id: str,
    user: User,
    db: AsyncSession,
    *,
    llm=None,
) -> SugerenciaReclasificacion:
    """Sugiere categoría/prioridad para un reporte usando el clasificador cívico.

    Se apoya en ``orchestrator.clasificar_reporte`` (LLM real + red de seguridad
    por keywords). Si el LLM no está disponible, ese clasificador ya cae a una
    heurística por palabras clave, por lo que esta función siempre responde.
    """
    from app.agente import orchestrator
    from app.models.categoria import Categoria

    base = await reporte_service.get_reporte(reporte_id, user, db)
    ctx = derive_contexto(user)

    cats = [r[0] for r in (await db.execute(select(Categoria.id))).all()]

    texto = f"{base.titulo}. {base.descripcion or ''}".strip()
    clasif = await orchestrator.clasificar_reporte(db, ctx, texto, cats, llm=llm)

    cat_sug = clasif.categoria_sugerida or base.categoria_id
    prio_sug = clasif.prioridad_sugerida or base.prioridad

    return SugerenciaReclasificacion(
        reporte_id=base.id,
        folio=base.folio,
        titulo=base.titulo,
        categoria_actual=base.categoria_id,
        categoria_sugerida=cat_sug,
        cambia_categoria=cat_sug != base.categoria_id,
        prioridad_actual=base.prioridad,
        prioridad_sugerida=prio_sug,
        cambia_prioridad=prio_sug != base.prioridad,
        es_emergencia=clasif.es_emergencia,
        es_sensible=clasif.es_sensible,
        justificacion=clasif.justificacion,
    )
