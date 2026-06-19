"""Router del Agente Cívico — endpoints públicos para la app ciudadana.

A diferencia del agente institucional, estos endpoints son accesibles
sin autenticación (para consultas generales) y con autenticación
opcional (para seguimiento personalizado).
"""

import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.agente.llm.factory import get_llm_client
from app.agente.rag.store import get_store
from app.agente_civico import orchestrator as civico_orchestrator
from app.core.config import settings
from app.core.database import get_db
from app.core.security import JWTError, decode_access_token
from app.schemas.civico import (
    CivicoChatRequest,
    CivicoChatResponse,
    CivicoClassifyRequest,
    CivicoClassifyResponse,
    CivicoHealth,
    PrefillReporteRequest,
    PrefillReporteResponse,
)

router = APIRouter(prefix="/civico", tags=["civico"])

# Bearer scheme opcional — no lanza error si no hay token.
_optional_bearer = HTTPBearer(auto_error=False)


async def _es_autenticado(
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
) -> bool:
    """Devuelve True si el request trae un JWT válido."""
    if credentials is None:
        return False
    try:
        decode_access_token(credentials.credentials)
        return True
    except (JWTError, Exception):
        return False


# ─── Chat ─────────────────────────────────────────────────────────────────


@router.post("/chat", response_model=CivicoChatResponse)
async def chat(
    data: CivicoChatRequest,
    autenticado: bool = Depends(_es_autenticado),
    db: AsyncSession = Depends(get_db),
):
    """Chat con el Agente Cívico. No requiere autenticación."""
    historial = [{"role": m.role, "content": m.content} for m in data.historial]
    return await civico_orchestrator.responder_chat(
        mensaje=data.mensaje,
        historial=historial,
        autenticado=autenticado or data.contexto.autenticado,
        primera_visita=data.contexto.primera_visita,
        db=db,
    )


@router.post("/chat/stream")
async def chat_stream(
    data: CivicoChatRequest,
    autenticado: bool = Depends(_es_autenticado),
    db: AsyncSession = Depends(get_db),
):
    """Chat con streaming (SSE) para la UX móvil."""
    historial = [{"role": m.role, "content": m.content} for m in data.historial]

    async def _generar():
        async for evento in civico_orchestrator.stream_chat(
            mensaje=data.mensaje,
            historial=historial,
            autenticado=autenticado or data.contexto.autenticado,
            primera_visita=data.contexto.primera_visita,
            db=db,
        ):
            yield f"data: {json.dumps(evento, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(_generar(), media_type="text/event-stream")


# ─── Clasificación ────────────────────────────────────────────────────────


@router.post("/classify", response_model=CivicoClassifyResponse)
async def classify(data: CivicoClassifyRequest):
    """Clasifica la descripción de un reporte ciudadano."""
    from app.agente_civico.safety.crisis import detectar_crisis

    # Detección de emergencia por palabras clave (red de seguridad).
    crisis = detectar_crisis(data.descripcion)
    if crisis.es_crisis:
        return CivicoClassifyResponse(
            categoria_sugerida="emergencia",
            prioridad_sugerida="critica",
            es_emergencia=True,
            justificacion="Se detectaron indicios de emergencia. Llama al 911.",
        )

    # Clasificación simple por heurística (el LLM se usa para el chat).
    llm = get_llm_client()
    instruccion = (
        "Clasifica el siguiente reporte ciudadano de la Alcaldía La Magdalena "
        "Contreras. Responde SOLO con un objeto JSON con las claves: "
        "categoria_sugerida (string), prioridad_sugerida (baja|media|alta|critica), "
        "es_emergencia (bool), justificacion (string breve)."
    )
    mensajes = [
        {"role": "system", "content": instruccion},
        {"role": "user", "content": data.descripcion},
    ]
    crudo = await llm.chat(mensajes)

    # Parsear JSON del modelo.
    try:
        inicio = crudo.index("{")
        fin = crudo.rindex("}") + 1
        datos = json.loads(crudo[inicio:fin])
    except (ValueError, json.JSONDecodeError):
        datos = {}

    return CivicoClassifyResponse(
        categoria_sugerida=datos.get("categoria_sugerida", "otros"),
        prioridad_sugerida=datos.get("prioridad_sugerida", "media")
        if datos.get("prioridad_sugerida") in ("baja", "media", "alta", "critica")
        else "media",
        es_emergencia=bool(datos.get("es_emergencia", False)),
        justificacion=datos.get("justificacion", "Clasificación preliminar."),
    )


# ─── Pre-llenado de reportes ──────────────────────────────────────────────


@router.post("/reportes/prefill", response_model=PrefillReporteResponse)
async def prefill_reporte(data: PrefillReporteRequest):
    """Pre-llena un borrador de reporte. NO lo envía — requiere confirmación."""
    return PrefillReporteResponse(
        descripcion=data.descripcion,
        categoria_id=data.categoria_id,
        colonia_id=data.colonia_id,
        lng=data.lng,
        lat=data.lat,
        requiere_confirmacion=True,
    )


# ─── Health ───────────────────────────────────────────────────────────────


@router.get("/health", response_model=CivicoHealth)
async def health():
    """Verificación de estado del agente cívico."""
    llm_ok = bool(settings.DEEPSEEK_API_KEY or settings.ANTHROPIC_API_KEY)
    try:
        store = get_store()
        vs_ok = store.count() >= 0
    except Exception:
        vs_ok = False

    return CivicoHealth(
        status="ok" if llm_ok and vs_ok else "degraded",
        llm_provider=settings.LLM_PROVIDER,
        llm_configurado=llm_ok,
        vector_store_ok=vs_ok,
    )
