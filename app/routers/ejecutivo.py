"""Endpoints del Agente Ejecutivo (asistente del Alcalde), bajo /api/v1/ejecutivo.

Visión CROSS-DIRECCIONES. Protegido por el permiso ``EJECUTIVO_VER``; el tenant y
el alcance se derivan SIEMPRE del JWT real (nunca del body). Reutiliza el motor LLM
(DeepSeek) del Agente Institucional sin editarlo.
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.agente_ejecutivo import orchestrator
from app.core.dependencies import DB, Audit, get_current_user
from app.core.exceptions import ForbiddenError
from app.core.permissions import Permission, has_permission
from app.models.user import User
from app.schemas.ejecutivo import (
    CompromisoCreate,
    CompromisoOut,
    CompromisosResumen,
    CompromisoUpdate,
    EjecutivoChatRequest,
    EjecutivoChatResponse,
    ResumenEjecutivo,
    SentimientoResponse,
)
from app.services import compromiso_service


async def _ejecutivo_user(user: Annotated[User, Depends(get_current_user)]) -> User:
    """Exige el permiso EJECUTIVO_VER (Alcalde, dirección, supervisión, admin)."""
    if not has_permission(user.role, Permission.EJECUTIVO_VER):
        raise ForbiddenError(f"Requiere permiso: {Permission.EJECUTIVO_VER.value}")
    return user


EjecutivoUser = Annotated[User, Depends(_ejecutivo_user)]

router = APIRouter(prefix="/ejecutivo", tags=["ejecutivo"])


# ─── Chat ────────────────────────────────────────────────────────────────────


@router.post("/chat", response_model=EjecutivoChatResponse)
async def chat(req: EjecutivoChatRequest, user: EjecutivoUser, db: DB) -> EjecutivoChatResponse:
    """Pregunta en lenguaje natural -> respuesta del orquestador ejecutivo."""
    historial = [m.model_dump() for m in req.historial]
    return await orchestrator.responder_chat(db, user, req.mensaje, historial)


# ─── Compromisos ─────────────────────────────────────────────────────────────


@router.get("/compromisos", response_model=CompromisosResumen)
async def listar_compromisos(
    user: EjecutivoUser,
    db: DB,
    estado: str | None = None,
    area_id: str | None = None,
) -> CompromisosResumen:
    """Seguimiento agregado de compromisos (con filtros opcionales)."""
    if estado or area_id:
        items = await compromiso_service.list_compromisos(
            user.tenant_id, db, estado=estado, area_id=area_id
        )
        return CompromisosResumen(total=len(items), items=items)
    return await compromiso_service.resumen_compromisos(user.tenant_id, db)


@router.post("/compromisos", response_model=CompromisoOut, status_code=201)
async def crear_compromiso(
    data: CompromisoCreate, user: EjecutivoUser, db: DB, audit: Audit
) -> CompromisoOut:
    return await compromiso_service.create_compromiso(
        data, user.tenant_id, db, audit, user.id
    )


@router.put("/compromisos/{compromiso_id}", response_model=CompromisoOut)
async def actualizar_compromiso(
    compromiso_id: str,
    data: CompromisoUpdate,
    user: EjecutivoUser,
    db: DB,
    audit: Audit,
) -> CompromisoOut:
    return await compromiso_service.update_compromiso(
        compromiso_id, data, user.tenant_id, db, audit, user.id
    )


# ─── Sentimiento ciudadano ───────────────────────────────────────────────────


@router.get("/sentimiento", response_model=SentimientoResponse)
async def sentimiento(user: EjecutivoUser, db: DB) -> SentimientoResponse:
    """Análisis de sentimiento ciudadano (global y por área)."""
    return await orchestrator.analizar_sentimiento(user.tenant_id, db)


# ─── Resumen ejecutivo ───────────────────────────────────────────────────────


@router.get("/resumen", response_model=ResumenEjecutivo)
async def resumen(user: EjecutivoUser, db: DB) -> ResumenEjecutivo:
    """Síntesis ejecutiva cross-direcciones del estado de la alcaldía."""
    return await orchestrator.resumen_ejecutivo(db, user)
