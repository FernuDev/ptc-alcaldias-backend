from fastapi import APIRouter

from app.core.dependencies import DB, AdminUser, Audit, CurrentUser
from app.schemas.cuadrilla import CuadrillaCreate, CuadrillaRead, CuadrillaUpdate
from app.services import cuadrilla_service

router = APIRouter(prefix="/cuadrillas", tags=["cuadrillas"])


@router.get("", response_model=list[CuadrillaRead])
async def list_cuadrillas(user: CurrentUser, db: DB):
    cuadrillas = await cuadrilla_service.list_cuadrillas(user.tenant_id, db)
    result = []
    for c in cuadrillas:
        result.append(CuadrillaRead(
            id=c.id,
            tenant_id=c.tenant_id,
            nombre=c.nombre,
            integrantes=c.integrantes,
            especialidades=[e.id for e in c.especialidades],
        ))
    return result


@router.post("", response_model=CuadrillaRead, status_code=201)
async def create_cuadrilla(data: CuadrillaCreate, user: AdminUser, db: DB, audit: Audit):
    c = await cuadrilla_service.create_cuadrilla(data, user.tenant_id, db, audit, user.id)
    return CuadrillaRead(
        id=c.id, tenant_id=c.tenant_id, nombre=c.nombre, integrantes=c.integrantes,
        especialidades=[e.id for e in c.especialidades],
    )


@router.put("/{cuadrilla_id}", response_model=CuadrillaRead)
async def update_cuadrilla(cuadrilla_id: str, data: CuadrillaUpdate, user: AdminUser, db: DB, audit: Audit):
    c = await cuadrilla_service.update_cuadrilla(cuadrilla_id, data, user.tenant_id, db, audit, user.id)
    return CuadrillaRead(
        id=c.id, tenant_id=c.tenant_id, nombre=c.nombre, integrantes=c.integrantes,
        especialidades=[e.id for e in c.especialidades],
    )


@router.delete("/{cuadrilla_id}")
async def delete_cuadrilla(cuadrilla_id: str, user: AdminUser, db: DB, audit: Audit):
    await cuadrilla_service.delete_cuadrilla(cuadrilla_id, user.tenant_id, db, audit, user.id)
    return {"detail": "Cuadrilla eliminada"}
