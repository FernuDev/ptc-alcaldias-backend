from fastapi import APIRouter, Query

from app.core.dependencies import AdminUser, Audit, CurrentUser, DB
from app.schemas.common import PaginatedResponse
from app.schemas.reporte import (
    EvidenciaCreate,
    EvidenciaRead,
    EventoCreate,
    EventoRead,
    ReporteCreate,
    ReporteRead,
    ReporteUpdate,
)
from app.services import reporte_service

router = APIRouter(prefix="/reportes", tags=["reportes"])


@router.get("", response_model=PaginatedResponse[ReporteRead])
async def list_reportes(
    user: CurrentUser,
    db: DB,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: str = Query("fecha_creacion"),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    search: str | None = None,
    categorias: str | None = None,
    estados: str | None = None,
    prioridades: str | None = None,
    fuentes: str | None = None,
    colonia_ids: str | None = None,
):
    return await reporte_service.list_reportes(
        user,
        db,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_dir=sort_dir,
        search=search,
        categorias=categorias.split(",") if categorias else None,
        estados=estados.split(",") if estados else None,
        prioridades=prioridades.split(",") if prioridades else None,
        fuentes=fuentes.split(",") if fuentes else None,
        colonia_ids=colonia_ids.split(",") if colonia_ids else None,
    )


@router.get("/{reporte_id}", response_model=ReporteRead)
async def get_reporte(reporte_id: str, user: CurrentUser, db: DB):
    return await reporte_service.get_reporte(reporte_id, user, db)


@router.post("", response_model=ReporteRead, status_code=201)
async def create_reporte(data: ReporteCreate, user: CurrentUser, db: DB, audit: Audit):
    r = await reporte_service.create_reporte(data, user, db, audit)
    return ReporteRead.model_validate(r)


@router.put("/{reporte_id}", response_model=ReporteRead)
async def update_reporte(reporte_id: str, data: ReporteUpdate, user: CurrentUser, db: DB, audit: Audit):
    r = await reporte_service.update_reporte(reporte_id, data, user, db, audit)
    return ReporteRead.model_validate(r)


@router.delete("/{reporte_id}")
async def delete_reporte(reporte_id: str, user: AdminUser, db: DB, audit: Audit):
    await reporte_service.delete_reporte(reporte_id, user, db, audit)
    return {"detail": "Reporte eliminado"}


@router.post("/{reporte_id}/evidencias", response_model=EvidenciaRead, status_code=201)
async def add_evidencia(reporte_id: str, data: EvidenciaCreate, user: CurrentUser, db: DB, audit: Audit):
    ev = await reporte_service.add_evidencia(reporte_id, data, user, db, audit)
    return EvidenciaRead.model_validate(ev)


@router.post("/{reporte_id}/eventos", response_model=EventoRead, status_code=201)
async def add_evento(reporte_id: str, data: EventoCreate, user: CurrentUser, db: DB, audit: Audit):
    evt = await reporte_service.add_evento(reporte_id, data, user, db, audit)
    return EventoRead.model_validate(evt)
