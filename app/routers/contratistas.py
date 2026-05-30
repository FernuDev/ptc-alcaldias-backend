from fastapi import APIRouter

from app.core.dependencies import AdminUser, Audit, CurrentUser, DB
from app.schemas.contratista import ContratistaCreate, ContratistaRead, ContratistaUpdate
from app.services import contratista_service

router = APIRouter(prefix="/contratistas", tags=["contratistas"])


@router.get("", response_model=list[ContratistaRead])
async def list_contratistas(user: CurrentUser, db: DB):
    contratistas = await contratista_service.list_contratistas(db)
    return [ContratistaRead.model_validate(c) for c in contratistas]


@router.post("", response_model=ContratistaRead, status_code=201)
async def create_contratista(data: ContratistaCreate, user: AdminUser, db: DB, audit: Audit):
    c = await contratista_service.create_contratista(data, db, audit, user.id, user.tenant_id)
    return ContratistaRead.model_validate(c)


@router.put("/{contratista_id}", response_model=ContratistaRead)
async def update_contratista(contratista_id: str, data: ContratistaUpdate, user: AdminUser, db: DB, audit: Audit):
    c = await contratista_service.update_contratista(contratista_id, data, db, audit, user.id, user.tenant_id)
    return ContratistaRead.model_validate(c)


@router.delete("/{contratista_id}")
async def delete_contratista(contratista_id: str, user: AdminUser, db: DB, audit: Audit):
    await contratista_service.delete_contratista(contratista_id, db, audit, user.id, user.tenant_id)
    return {"detail": "Contratista eliminado"}
