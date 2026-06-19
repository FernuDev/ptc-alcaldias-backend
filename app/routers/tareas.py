"""Router de tareas de campo (despacho operativo a cuadrillas).

Una tarea es el trabajo concreto que ejecuta una cuadrilla en calle. Se origina
en un reporte, una obra o se crea manualmente, y avanza por la máquina de estados
``pendiente -> en_ruta -> en_sitio -> cerrada``. La lógica vive en
``tarea_service``; aquí solo se expone vía HTTP.

Permisos:
  - Crear / asignar / cambiar estado / cerrar exigen ``CUADRILLA_DESPACHAR``.
  - Actualizar el checklist (trabajo de calle) exige ``CAMPO_EJECUTAR``.
  - La lectura solo exige estar autenticado (``CurrentUser``).

El tenant SIEMPRE proviene del JWT. La integración registra este router en
``main.py`` (no se toca aquí).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import DB, Audit, CurrentUser, require_permission
from app.core.exceptions import ConflictError
from app.core.permissions import Permission
from app.models.user import User
from app.schemas.campo import (
    AsignarInput,
    ChecklistInput,
    EstadoInput,
    TareaCreate,
    TareaRead,
)
from app.services import tarea_service

router = APIRouter(prefix="/tareas", tags=["tareas"])

# Despacho operativo: crear, asignar y mover tareas por la máquina de estados.
DespachaUser = Annotated[
    User, Depends(require_permission(Permission.CUADRILLA_DESPACHAR))
]
# Ejecución de campo: marcar pasos del checklist en sitio.
CampoUser = Annotated[User, Depends(require_permission(Permission.CAMPO_EJECUTAR))]


@router.get("", response_model=list[TareaRead])
async def list_tareas(
    user: CurrentUser,
    db: DB,
    estado: str | None = Query(None, pattern=r"^(pendiente|en_ruta|en_sitio|cerrada)$"),
    cuadrilla_id: str | None = None,
    colonia_id: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """Lista tareas del tenant con filtros y paginado en memoria.

    El servicio devuelve todas las tareas que cumplen los filtros (ordenadas por
    ruta); aquí se recorta la página solicitada para el frontend.
    """
    tareas = await tarea_service.list_tareas(
        user,
        db,
        estado=estado,
        cuadrilla_id=cuadrilla_id,
        colonia_id=colonia_id,
    )
    inicio = (page - 1) * page_size
    return [TareaRead.model_validate(t) for t in tareas[inicio : inicio + page_size]]


@router.get("/{tarea_id}", response_model=TareaRead)
async def get_tarea(tarea_id: str, user: CurrentUser, db: DB):
    tarea = await tarea_service.get_tarea(tarea_id, user, db)
    return TareaRead.model_validate(tarea)


@router.post("", response_model=TareaRead, status_code=201)
async def create_tarea(data: TareaCreate, user: DespachaUser, db: DB, audit: Audit):
    """Crea una tarea desde un reporte, una obra o de forma manual.

    El ``origen_tipo`` decide qué identificador/título es obligatorio y a qué
    helper del servicio se delega.
    """
    checklist = (
        [item.model_dump() for item in data.checklist] if data.checklist else None
    )

    if data.origen_tipo == "reporte":
        if not data.reporte_id:
            raise ConflictError("origen_tipo 'reporte' requiere reporte_id.")
        tarea = await tarea_service.crear_tarea_desde_reporte(
            data.reporte_id,
            user,
            db,
            audit,
            cuadrilla_id=data.cuadrilla_id,
            integrante_id=data.integrante_id,
            instrucciones=data.instrucciones,
        )
    elif data.origen_tipo == "obra":
        if not data.obra_id:
            raise ConflictError("origen_tipo 'obra' requiere obra_id.")
        tarea = await tarea_service.crear_tarea_desde_obra(
            data.obra_id,
            user,
            db,
            audit,
            cuadrilla_id=data.cuadrilla_id,
            integrante_id=data.integrante_id,
            titulo=data.titulo,
            instrucciones=data.instrucciones,
        )
    else:  # manual
        if not data.titulo:
            raise ConflictError("origen_tipo 'manual' requiere titulo.")
        tarea = await tarea_service.crear_tarea_manual(
            data.titulo,
            user,
            db,
            audit,
            descripcion=data.descripcion,
            prioridad=data.prioridad,
            cuadrilla_id=data.cuadrilla_id,
            integrante_id=data.integrante_id,
            lat=data.lat,
            lng=data.lng,
            colonia_id=data.colonia_id,
            instrucciones=data.instrucciones,
            checklist=checklist,
        )
    return TareaRead.model_validate(tarea)


@router.put("/{tarea_id}/asignar", response_model=TareaRead)
async def asignar_tarea(
    tarea_id: str, data: AsignarInput, user: DespachaUser, db: DB, audit: Audit
):
    """Asigna (o reasigna) la tarea a una cuadrilla y, opcionalmente, a un integrante."""
    tarea = await tarea_service.asignar(
        tarea_id,
        data.cuadrilla_id,
        user,
        db,
        audit,
        integrante_id=data.integrante_id,
    )
    return TareaRead.model_validate(tarea)


@router.put("/{tarea_id}/estado", response_model=TareaRead)
async def cambiar_estado(
    tarea_id: str, data: EstadoInput, user: DespachaUser, db: DB, audit: Audit
):
    """Avanza la tarea por la máquina de estados (rechaza saltos inválidos).

    Pasar a ``cerrada`` por esta vía exige evidencia antes/después; conviene usar
    el endpoint dedicado ``POST /{id}/cerrar``.
    """
    tarea = await tarea_service.cambiar_estado(tarea_id, data.estado, user, db, audit)
    return TareaRead.model_validate(tarea)


@router.post("/{tarea_id}/cerrar", response_model=TareaRead)
async def cerrar_tarea(tarea_id: str, user: DespachaUser, db: DB, audit: Audit):
    """Cierra la tarea exigiendo evidencia antes/después y propaga al reporte."""
    tarea = await tarea_service.cerrar_tarea(tarea_id, user, db, audit)
    return TareaRead.model_validate(tarea)


@router.put("/{tarea_id}/checklist", response_model=TareaRead)
async def actualizar_checklist(
    tarea_id: str, data: ChecklistInput, user: CampoUser, db: DB, audit: Audit
):
    """Reemplaza el checklist de la tarea (marca pasos hechos desde campo).

    Operación de campo: usa ``CAMPO_EJECUTAR``. Reescribe la lista completa de
    pasos y registra el cambio en auditoría.
    """
    tarea = await tarea_service.get_tarea(tarea_id, user, db)
    old = tarea.checklist
    tarea.checklist = [item.model_dump() for item in data.checklist]
    await db.flush()
    await audit.log(
        action="update",
        user_id=user.id,
        tenant_id=user.tenant_id,
        entity_type="tarea",
        entity_id=tarea.id,
        changes={"checklist": {"old": old, "new": tarea.checklist}},
    )
    return TareaRead.model_validate(tarea)
