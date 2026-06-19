"""Router 'mi-ruta' del trabajador de campo (vista del propio integrante).

A diferencia de ``/tareas`` (despacho, orientado al monitor) o ``/monitor`` (vista
global del coordinador), estos endpoints son egocéntricos: resuelven el
``Integrante`` vinculado al usuario autenticado (por ``Integrante.user_id``) y le
devuelven SU cuadrilla, SU turno activo y SU ruta de tareas del día.

Permiso: cualquier rol con ``CAMPO_EJECUTAR`` (jefe_cuadrilla / inspector / admin).
Si la cuenta no tiene un integrante vinculado, se responde 404 claro.

El tenant SIEMPRE proviene del JWT. La integración registra este router en
``main.py`` (no se toca aquí).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.dependencies import DB, require_permission
from app.core.exceptions import NotFoundError
from app.core.permissions import Permission
from app.models.user import User
from app.schemas.campo import TareaRead, TurnoRead
from app.schemas.cuadrilla import CuadrillaRead
from app.services import tarea_service, turno_service

router = APIRouter(prefix="/campo", tags=["campo-me"])

# Trabajador de campo: cualquier rol con capacidad de ejecutar en calle.
CampoUser = Annotated[User, Depends(require_permission(Permission.CAMPO_EJECUTAR))]


class IntegranteRead(BaseModel):
    """Datos del integrante de campo vinculado a la cuenta autenticada."""

    id: str
    cuadrilla_id: str
    tenant_id: str
    user_id: str | None = None
    nombre: str
    rol_campo: str  # jefe | integrante
    telefono: str | None = None
    activo: bool

    model_config = {"from_attributes": True}


class MiCuadrillaResponse(BaseModel):
    cuadrilla: CuadrillaRead
    integrante: IntegranteRead
    turno_activo: TurnoRead | None = None


class MiRutaResponse(BaseModel):
    cuadrilla_id: str
    tareas: list[TareaRead] = []


def _cuadrilla_read(cuadrilla) -> CuadrillaRead:
    # `especialidades` es una relación a Categoria; se serializa a sus ids (igual
    # que el router de cuadrillas), por eso no se usa model_validate directo.
    return CuadrillaRead(
        id=cuadrilla.id,
        tenant_id=cuadrilla.tenant_id,
        nombre=cuadrilla.nombre,
        integrantes=cuadrilla.integrantes,
        especialidades=[e.id for e in cuadrilla.especialidades],
    )


@router.get("/mi-cuadrilla", response_model=MiCuadrillaResponse)
async def mi_cuadrilla(user: CampoUser, db: DB):
    """Devuelve la cuadrilla, el integrante y el turno activo del usuario actual.

    Resuelve el ``Integrante`` por ``user_id``. Si la cuenta no está vinculada a
    un integrante de campo, responde 404.
    """
    integrante = await tarea_service.integrante_de_usuario(user, db)
    if integrante is None:
        raise NotFoundError("Integrante para el usuario", user.id)

    # La relación `cuadrilla` viene cargada (lazy="selectin") con el integrante.
    cuadrilla = integrante.cuadrilla

    turnos = await turno_service.turnos_activos(user.tenant_id, db)
    turno_activo = next(
        (t for t in turnos if t.cuadrilla_id == integrante.cuadrilla_id), None
    )

    return MiCuadrillaResponse(
        cuadrilla=_cuadrilla_read(cuadrilla),
        integrante=IntegranteRead.model_validate(integrante),
        turno_activo=(
            TurnoRead.model_validate(turno_activo) if turno_activo else None
        ),
    )


@router.get("/mi-ruta", response_model=MiRutaResponse)
async def mi_ruta(user: CampoUser, db: DB):
    """Devuelve las tareas de la cuadrilla del usuario, ordenadas como ruta.

    Orden: ``orden_ruta`` ascendente (nulls al final), luego prioridad y fecha de
    creación. Responde 404 si la cuenta no tiene integrante vinculado.
    """
    integrante = await tarea_service.integrante_de_usuario(user, db)
    if integrante is None:
        raise NotFoundError("Integrante para el usuario", user.id)

    tareas = await tarea_service.tareas_de_cuadrilla_ruteadas(
        integrante.cuadrilla_id, user, db
    )
    return MiRutaResponse(
        cuadrilla_id=integrante.cuadrilla_id,
        tareas=[TareaRead.model_validate(t) for t in tareas],
    )
