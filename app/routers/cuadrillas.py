from fastapi import APIRouter

from app.core.dependencies import DB, AdminUser, Audit, BackofficeUser, CurrentUser
from app.core.scoping import rbac_heredado_activo, user_scope_cuadrilla_ids
from app.schemas.cuadrilla import (
    CuadrillaCreate,
    CuadrillaRead,
    CuadrillaUpdate,
    IntegranteCreate,
    IntegranteRead,
    IntegranteUpdate,
)
from app.services import cuadrilla_service

router = APIRouter(prefix="/cuadrillas", tags=["cuadrillas"])


@router.get("", response_model=list[CuadrillaRead])
async def list_cuadrillas(user: CurrentUser, db: DB):
    cuadrillas = await cuadrilla_service.list_cuadrillas(user.tenant_id, db)
    # R5 · Fase 4: RBAC heredado — un JUD solo ve las cuadrillas de su sub-árbol.
    if rbac_heredado_activo():
        scope = await user_scope_cuadrilla_ids(db, user)
        if scope is not None:
            allowed = set(scope)
            cuadrillas = [c for c in cuadrillas if c.id in allowed]
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


# ─── Integrantes (editables por quien tiene la cuadrilla en su sub-árbol) ──────
@router.get("/{cuadrilla_id}/integrantes", response_model=list[IntegranteRead])
async def list_integrantes(cuadrilla_id: str, user: BackofficeUser, db: DB):
    items = await cuadrilla_service.list_integrantes(db, user, cuadrilla_id)
    return [IntegranteRead.model_validate(i) for i in items]


@router.post(
    "/{cuadrilla_id}/integrantes", response_model=IntegranteRead, status_code=201
)
async def add_integrante(
    cuadrilla_id: str,
    data: IntegranteCreate,
    user: BackofficeUser,
    db: DB,
    audit: Audit,
):
    i = await cuadrilla_service.add_integrante(db, user, cuadrilla_id, data, audit)
    return IntegranteRead.model_validate(i)


@router.put(
    "/{cuadrilla_id}/integrantes/{integrante_id}", response_model=IntegranteRead
)
async def update_integrante(
    cuadrilla_id: str,
    integrante_id: str,
    data: IntegranteUpdate,
    user: BackofficeUser,
    db: DB,
    audit: Audit,
):
    i = await cuadrilla_service.update_integrante(
        db, user, cuadrilla_id, integrante_id, data, audit
    )
    return IntegranteRead.model_validate(i)


@router.delete("/{cuadrilla_id}/integrantes/{integrante_id}")
async def delete_integrante(
    cuadrilla_id: str,
    integrante_id: str,
    user: BackofficeUser,
    db: DB,
    audit: Audit,
):
    await cuadrilla_service.delete_integrante(db, user, cuadrilla_id, integrante_id, audit)
    return {"detail": "Integrante eliminado"}
