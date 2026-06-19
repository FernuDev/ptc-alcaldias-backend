"""Router de rastreo GPS de cuadrillas (mapa en vivo del monitor).

Registra pines de ubicación en serie temporal (los manda el dispositivo en
campo) y resuelve la última posición conocida por cuadrilla. La lógica vive en
``ubicacion_service``.

Permisos:
  - Registrar un pin es trabajo de campo: exige ``CAMPO_EJECUTAR``.
  - Consultar las posiciones actuales solo exige estar autenticado.

El tenant SIEMPRE proviene del JWT. La integración registra este router en
``main.py`` (no se toca aquí).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.dependencies import DB, CurrentUser, require_permission
from app.core.permissions import Permission
from app.models.user import User
from app.schemas.campo import PosicionRead, UbicacionCreate, UbicacionRead
from app.services import ubicacion_service

router = APIRouter(prefix="/ubicacion", tags=["ubicacion"])

CampoUser = Annotated[User, Depends(require_permission(Permission.CAMPO_EJECUTAR))]


@router.post("", response_model=UbicacionRead, status_code=201)
async def registrar_ubicacion(data: UbicacionCreate, user: CampoUser, db: DB):
    """Registra un nuevo pin GPS para la cuadrilla (timestamp = ahora)."""
    ubic = await ubicacion_service.registrar(
        data.cuadrilla_id,
        data.lat,
        data.lng,
        user,
        db,
        integrante_id=data.integrante_id,
    )
    return UbicacionRead.model_validate(ubic)


@router.get("/actuales", response_model=list[PosicionRead])
async def posiciones_actuales(user: CurrentUser, db: DB):
    """Última posición conocida por cuadrilla del tenant (mapa en vivo)."""
    posiciones = await ubicacion_service.posiciones_actuales(user.tenant_id, db)
    return [PosicionRead.model_validate(p) for p in posiciones]
