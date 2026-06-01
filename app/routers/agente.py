"""Endpoints del Agente Institucional, montados bajo /api/v1/agente.

Todos los endpoints que tocan datos reciben `CurrentUser` (JWT real) y derivan
el `UsuarioContexto` en el servidor; el rol/alcance nunca llega por el body.
"""

import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.agente import actions, analytics, orchestrator
from app.agente.context import derive_contexto
from app.agente.llm.factory import get_llm_client
from app.agente.rag.ingest import ingest_documento
from app.core.config import settings
from app.core.database import async_session_factory
from app.core.dependencies import DB, AdminUser, Audit, CurrentUser
from app.models.categoria import Categoria
from app.schemas.agente import (
    AgenteHealth,
    AnalyticsRequest,
    AnalyticsResponse,
    ChatRequest,
    ChatResponse,
    ClassifyRequest,
    ClassifyResponse,
    ConfirmActionRequest,
    ConfirmActionResponse,
    IngestDocRequest,
    IngestResponse,
    PrepareActionRequest,
    PreparedAction,
)

router = APIRouter(prefix="/agente", tags=["agente"])


async def _categorias_validas(db: DB) -> list[str]:
    rows = await db.execute(select(Categoria.id))
    return [r[0] for r in rows.all()]


def _llm_configurado() -> bool:
    """True si el proveedor activo tiene su API key presente."""
    provider = settings.LLM_PROVIDER.lower()
    if provider == "deepseek":
        return bool(settings.DEEPSEEK_API_KEY)
    if provider == "anthropic":
        return bool(settings.ANTHROPIC_API_KEY)
    return provider == "fake"


def _vector_store_estado() -> tuple[bool, int | None]:
    """Comprueba el almacén vectorial de forma perezosa y tolerante a fallos."""
    try:
        from app.agente.rag.store import get_store

        store = get_store()
        return True, store.count()
    except Exception:
        return False, None


@router.get("/health", response_model=AgenteHealth)
async def health(user: CurrentUser) -> AgenteHealth:
    store_ok, indexados = _vector_store_estado()
    llm_ok = _llm_configurado()
    return AgenteHealth(
        status="ok" if (llm_ok and store_ok) else "degraded",
        llm_provider=settings.LLM_PROVIDER,
        llm_configurado=llm_ok,
        vector_store_ok=store_ok,
        documentos_indexados=indexados,
    )


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, user: CurrentUser, db: DB) -> ChatResponse:
    historial = [m.model_dump() for m in req.historial]
    return await orchestrator.responder_chat(db, user, req.mensaje, historial)


@router.post("/chat/stream")
async def chat_stream(req: ChatRequest, user: CurrentUser) -> StreamingResponse:
    """Respuesta por streaming (SSE). Maneja su propia sesión DB porque el cuerpo
    se consume después de retornar, fuera del ciclo de la dependencia get_db."""
    historial = [m.model_dump() for m in req.historial]

    async def gen():
        async with async_session_factory() as db:
            try:
                async for evento in orchestrator.stream_chat(db, user, req.mensaje, historial):
                    yield f"data: {json.dumps(evento, ensure_ascii=False)}\n\n"
                await db.commit()
            except Exception as exc:  # noqa: BLE001
                await db.rollback()
                yield f"event: error\ndata: {json.dumps({'error': str(exc)})}\n\n"
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.post("/classify", response_model=ClassifyResponse)
async def classify(req: ClassifyRequest, user: CurrentUser, db: DB) -> ClassifyResponse:
    ctx = derive_contexto(user)
    cats = await _categorias_validas(db)
    return await orchestrator.clasificar_reporte(db, ctx, req.descripcion, cats)


@router.post("/analytics", response_model=AnalyticsResponse)
async def analytics_endpoint(req: AnalyticsRequest, user: CurrentUser, db: DB) -> AnalyticsResponse:
    ctx = derive_contexto(user)
    disponibles = analytics.intents_disponibles()

    intent = req.intent
    if not intent and req.consulta:
        intent = await analytics.seleccionar_intent(req.consulta, get_llm_client())

    if not intent or intent not in disponibles:
        # No se reconoció un intent: devuelve el catálogo para que el cliente elija.
        return AnalyticsResponse(intent=None, disponibles=disponibles)

    datos = await analytics.ejecutar_intent(intent, user, db, req.params)
    resumen = await analytics.narrar(get_llm_client(), intent, datos, ctx)
    return AnalyticsResponse(intent=intent, datos=datos, resumen=resumen, disponibles=disponibles)


@router.post("/ingest", response_model=IngestResponse)
async def ingest(req: IngestDocRequest, admin: AdminUser, db: DB) -> IngestResponse:
    """Carga un documento a la base de conocimiento. Solo administradores."""
    doc = await ingest_documento(
        db,
        titulo=req.titulo,
        contenido=req.contenido,
        nivel=req.nivel_visibilidad,
        tenant_id=req.tenant_id,
        area_id=req.area_id,
        fuente=req.fuente,
    )
    return IngestResponse(documento_id=doc.id, fragmentos=doc.fragmentos)


@router.post("/actions/prepare", response_model=PreparedAction)
async def prepare_action(req: PrepareActionRequest, user: CurrentUser, db: DB) -> PreparedAction:
    ctx = derive_contexto(user)
    return await actions.preparar_accion(
        db,
        ctx,
        user,
        tipo=req.tipo,
        entity_type=req.entity_type,
        entity_id=req.entity_id,
        params=req.params,
    )


@router.post("/actions/confirm", response_model=ConfirmActionResponse)
async def confirm_action(
    req: ConfirmActionRequest, user: CurrentUser, db: DB, audit: Audit
) -> ConfirmActionResponse:
    ctx = derive_contexto(user)
    return await actions.confirmar_accion(db, ctx, user, req.accion_id, audit)
