"""Orquestador del Agente Cívico.

A diferencia del Agente Institucional, este orquestador:
1. Ejecuta detección de crisis ANTES de cualquier respuesta.
2. Verifica solicitudes de PII de terceros.
3. No usa tool-calling (sin consultas en vivo para anónimos).
4. RAG solo recupera documentos públicos.
5. Soporta usuarios anónimos y autenticados.
"""

import re
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from app.agente.llm.base import LLMClient, Message
from app.agente.llm.factory import get_llm_client
from app.agente.rag.store import VectorStore, get_store
from app.agente_civico.safety.crisis import CrisisResult, detectar_crisis
from app.agente_civico.safety.pii import verificar_solicitud_pii
from app.agente_civico.system_prompt import SYSTEM_PROMPT_CIVICO
from app.core.config import settings
from app.schemas.civico import (
    CivicoChatResponse,
    CivicoFuente,
)

NO_SE = (
    "No tengo esa información en este momento. Te recomiendo llamar al "
    "**55 5449 6300** o acudir directamente a la alcaldía para que te orienten."
)

# Score mínimo de similitud para considerar un fragmento relevante.
_MIN_RAG_SCORE = 0.45


# ─── Helpers de prompt ─────────────────────────────────────────────────────


def _bloque_contexto_ciudadano(autenticado: bool, primera_visita: bool) -> str:
    lineas = ["## Contexto del usuario"]
    lineas.append(f"- autenticado: {'sí' if autenticado else 'no'}")
    if primera_visita:
        lineas.append("- primera_visita: sí (ofrece un breve tour)")
    if not autenticado:
        lineas.append(
            "- El usuario es anónimo. No puedes acceder a datos personalizados "
            "(trámites, reportes, citas). Si lo necesita, sugiérele iniciar sesión."
        )
    return "\n".join(lineas)


def _bloque_rag(frags: list[dict]) -> str:
    if not frags:
        return ""
    lineas = []
    for i, f in enumerate(frags, 1):
        m = f.get("metadata", {})
        lineas.append(f"[{i}] ({m.get('titulo', 'Documento')} · {m.get('seccion', '')})\n{f.get('document', '')}")
    return (
        "# CONTEXTO RECUPERADO (responde solo con esto y cita las fuentes [n])\n"
        + "\n\n".join(lineas)
    )


def _construir_mensajes(
    mensaje: str,
    historial: list[Message],
    frags: list[dict],
    autenticado: bool,
    primera_visita: bool,
) -> list[Message]:
    mensajes: list[Message] = [
        {
            "role": "system",
            "content": (
                f"{SYSTEM_PROMPT_CIVICO}\n\n"
                f"{_bloque_contexto_ciudadano(autenticado, primera_visita)}"
            ),
        }
    ]
    bloque = _bloque_rag(frags)
    if bloque:
        mensajes.append({"role": "system", "content": bloque})
    mensajes.extend(historial)
    mensajes.append({"role": "user", "content": mensaje})
    return mensajes


def _recuperar_publico(consulta: str, *, k: int = 5, store: VectorStore | None = None) -> list[dict]:
    """Recupera fragmentos del RAG limitados a documentos públicos."""
    store = store or get_store()
    try:
        crudos = store.query(
            consulta,
            n_results=k,
            where={"nivel": "publico"},
        )
    except Exception:
        crudos = []
    # Filtrar por score mínimo.
    resultado = []
    for f in crudos:
        dist = f.get("distance")
        if isinstance(dist, (int, float)) and (1 - dist) < _MIN_RAG_SCORE:
            continue
        resultado.append(f)
    return resultado


def _fuentes(frags: list[dict]) -> list[CivicoFuente]:
    vistos: dict[str, CivicoFuente] = {}
    for f in frags:
        m = f.get("metadata", {})
        doc_id = m.get("documento_id", "")
        if doc_id in vistos:
            continue
        dist = f.get("distance")
        score = round(1 - dist, 3) if isinstance(dist, (int, float)) else None
        if score is not None and score < _MIN_RAG_SCORE:
            continue
        vistos[doc_id] = CivicoFuente(
            documento=m.get("titulo", "Documento"),
            seccion=m.get("seccion"),
        )
    return list(vistos.values())


# ─── Casos de uso ──────────────────────────────────────────────────────────


async def responder_chat(
    mensaje: str,
    historial: list[Message] | None = None,
    *,
    autenticado: bool = False,
    primera_visita: bool = False,
    db: AsyncSession | None = None,
    store: VectorStore | None = None,
    llm: LLMClient | None = None,
) -> CivicoChatResponse:
    """Procesa un mensaje del ciudadano y devuelve la respuesta del agente.

    Orden de ejecución:
    1. Detección de crisis (prioridad absoluta)
    2. Verificación de solicitud de PII de terceros
    3. Recuperación RAG (solo documentos públicos)
    4. Llamada al LLM
    """
    historial = historial or []
    llm = llm or get_llm_client()

    # 1. Detección de crisis — ANTES de todo.
    crisis: CrisisResult = detectar_crisis(mensaje)
    if crisis.es_crisis:
        return CivicoChatResponse(
            respuesta=crisis.respuesta or "",
            fuentes=[],
            es_crisis=True,
        )

    # 2. Verificación de PII.
    pii_check = verificar_solicitud_pii(mensaje)
    if pii_check.bloqueado:
        return CivicoChatResponse(
            respuesta=pii_check.respuesta or "",
            fuentes=[],
            es_crisis=False,
        )

    # 3. Recuperación RAG (solo documentos públicos).
    frags = _recuperar_publico(mensaje, store=store)

    # 4. Construir mensajes y llamar al LLM.
    mensajes = _construir_mensajes(
        mensaje, historial, frags,
        autenticado=autenticado,
        primera_visita=primera_visita,
    )

    texto = await llm.chat(
        mensajes,
        temperature=settings.LLM_TEMPERATURE + 0.1,  # Tono ligeramente más cálido
        max_tokens=settings.LLM_MAX_TOKENS,
    )

    fuentes = _fuentes(frags)
    sin_info = len(frags) == 0

    return CivicoChatResponse(
        respuesta=texto,
        fuentes=fuentes,
        es_crisis=False,
        sin_informacion=sin_info,
    )


async def stream_chat(
    mensaje: str,
    historial: list[Message] | None = None,
    *,
    autenticado: bool = False,
    primera_visita: bool = False,
    db: AsyncSession | None = None,
    store: VectorStore | None = None,
    llm: LLMClient | None = None,
) -> AsyncIterator[dict]:
    """Versión streaming del chat cívico.

    Emite eventos SSE:
    - {"delta": "<texto>"}  — fragmento de respuesta
    - {"fuentes": [...], "es_crisis": bool}  — evento final
    """
    historial = historial or []
    llm = llm or get_llm_client()

    # 1. Detección de crisis.
    crisis: CrisisResult = detectar_crisis(mensaje)
    if crisis.es_crisis:
        respuesta = crisis.respuesta or ""
        for parte in re.findall(r"\S+\s*", respuesta):
            yield {"delta": parte}
        yield {"fuentes": [], "es_crisis": True}
        return

    # 2. Verificación de PII.
    pii_check = verificar_solicitud_pii(mensaje)
    if pii_check.bloqueado:
        respuesta = pii_check.respuesta or ""
        for parte in re.findall(r"\S+\s*", respuesta):
            yield {"delta": parte}
        yield {"fuentes": [], "es_crisis": False}
        return

    # 3. RAG público.
    frags = _recuperar_publico(mensaje, store=store)

    # 4. LLM.
    mensajes = _construir_mensajes(
        mensaje, historial, frags,
        autenticado=autenticado,
        primera_visita=primera_visita,
    )

    texto = await llm.chat(
        mensajes,
        temperature=settings.LLM_TEMPERATURE + 0.1,
        max_tokens=settings.LLM_MAX_TOKENS,
    )

    for parte in re.findall(r"\S+\s*", texto):
        yield {"delta": parte}

    fuentes = _fuentes(frags)
    yield {
        "fuentes": [f.model_dump() for f in fuentes],
        "es_crisis": False,
        "sin_informacion": len(frags) == 0,
    }
