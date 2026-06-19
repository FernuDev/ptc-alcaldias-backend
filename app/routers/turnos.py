"""Router de turnos de campo (jornadas operativas de las cuadrillas).

Una cuadrilla abre un turno al iniciar su jornada y lo cierra al terminar. Solo
puede existir un turno ``abierto`` por cuadrilla a la vez. La lógica vive en
``turno_service``. Despachar turnos exige ``CUADRILLA_DESPACHAR``.

El tenant SIEMPRE proviene del JWT. La integración registra este router en
``main.py`` (no se toca aquí).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.dependencies import DB, Audit, CurrentUser, require_permission
from app.core.permissions import Permission
from app.models.user import User
from app.schemas.campo import TurnoAbrirInput, TurnoRead
from app.services import turno_service

router = APIRouter(prefix="/turnos", tags=["turnos"])

DespachaUser = Annotated[
    User, Depends(require_permission(Permission.CUADRILLA_DESPACHAR))
]


@router.post("/abrir", response_model=TurnoRead, status_code=201)
async def abrir_turno(data: TurnoAbrirInput, user: DespachaUser, db: DB, audit: Audit):
    """Abre un turno para la cuadrilla (falla si ya tiene uno abierto)."""
    turno = await turno_service.abrir_turno(data.cuadrilla_id, user, db, audit)
    return TurnoRead.model_validate(turno)


@router.post("/{turno_id}/cerrar", response_model=TurnoRead)
async def cerrar_turno(turno_id: str, user: DespachaUser, db: DB, audit: Audit):
    """Cierra un turno abierto del tenant."""
    turno = await turno_service.cerrar_turno(turno_id, user, db, audit)
    return TurnoRead.model_validate(turno)


@router.get("/activos", response_model=list[TurnoRead])
async def turnos_activos(user: CurrentUser, db: DB):
    """Lista los turnos abiertos del tenant (uno por cuadrilla activa)."""
    turnos = await turno_service.turnos_activos(user.tenant_id, db)
    return [TurnoRead.model_validate(t) for t in turnos]
