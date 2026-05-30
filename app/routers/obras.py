from fastapi import APIRouter, Query

from app.core.dependencies import AdminUser, Audit, CurrentUser, DB
from app.schemas.common import PaginatedResponse
from app.schemas.obra import (
    CalleAfectadaCreate,
    CalleAfectadaRead,
    DocumentoCreate,
    DocumentoRead,
    EquipoCreate,
    EquipoRead,
    ObraCreate,
    ObraEvidenciaCreate,
    ObraEvidenciaRead,
    ObraRead,
    ObraUpdate,
    TimelineCreate,
    TimelineRead,
)
from app.services import obra_service

router = APIRouter(prefix="/obras", tags=["obras"])


@router.get("", response_model=PaginatedResponse[ObraRead])
async def list_obras(
    user: CurrentUser,
    db: DB,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: str = Query("fecha_inicio"),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    search: str | None = None,
    categorias: str | None = None,
    estados: str | None = None,
    prioridades: str | None = None,
    colonia_ids: str | None = None,
):
    return await obra_service.list_obras(
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
        colonia_ids=colonia_ids.split(",") if colonia_ids else None,
    )


@router.get("/{obra_id}", response_model=ObraRead)
async def get_obra(obra_id: str, user: CurrentUser, db: DB):
    return await obra_service.get_obra(obra_id, user, db)


@router.post("", response_model=ObraRead, status_code=201)
async def create_obra(data: ObraCreate, user: AdminUser, db: DB, audit: Audit):
    o = await obra_service.create_obra(data, user, db, audit)
    return ObraRead.model_validate(o)


@router.put("/{obra_id}", response_model=ObraRead)
async def update_obra(obra_id: str, data: ObraUpdate, user: CurrentUser, db: DB, audit: Audit):
    o = await obra_service.update_obra(obra_id, data, user, db, audit)
    return ObraRead.model_validate(o)


@router.delete("/{obra_id}")
async def delete_obra(obra_id: str, user: AdminUser, db: DB, audit: Audit):
    await obra_service.delete_obra(obra_id, user, db, audit)
    return {"detail": "Obra eliminada"}


@router.post("/{obra_id}/equipo", response_model=EquipoRead, status_code=201)
async def add_equipo(obra_id: str, data: EquipoCreate, user: CurrentUser, db: DB, audit: Audit):
    m = await obra_service.add_equipo(obra_id, data, user, db, audit)
    return EquipoRead.model_validate(m)


@router.post("/{obra_id}/calles", response_model=CalleAfectadaRead, status_code=201)
async def add_calle(obra_id: str, data: CalleAfectadaCreate, user: CurrentUser, db: DB, audit: Audit):
    c = await obra_service.add_calle(obra_id, data, user, db, audit)
    return CalleAfectadaRead.model_validate(c)


@router.post("/{obra_id}/timeline", response_model=TimelineRead, status_code=201)
async def add_timeline(obra_id: str, data: TimelineCreate, user: CurrentUser, db: DB, audit: Audit):
    tl = await obra_service.add_timeline(obra_id, data, user, db, audit)
    return TimelineRead.model_validate(tl)


@router.post("/{obra_id}/documentos", response_model=DocumentoRead, status_code=201)
async def add_documento(obra_id: str, data: DocumentoCreate, user: CurrentUser, db: DB, audit: Audit):
    d = await obra_service.add_documento(obra_id, data, user, db, audit)
    return DocumentoRead.model_validate(d)


@router.post("/{obra_id}/evidencias", response_model=ObraEvidenciaRead, status_code=201)
async def add_evidencia(obra_id: str, data: ObraEvidenciaCreate, user: CurrentUser, db: DB, audit: Audit):
    ev = await obra_service.add_evidencia(obra_id, data, user, db, audit)
    return ObraEvidenciaRead.model_validate(ev)
