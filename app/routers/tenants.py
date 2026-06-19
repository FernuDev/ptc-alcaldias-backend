from fastapi import APIRouter

from app.core.dependencies import DB, AdminUser, Audit, CurrentUser
from app.schemas.tenant import TenantPublic, TenantRead, TenantUpdate
from app.services import tenant_service

router = APIRouter(prefix="/tenants", tags=["tenants"])


@router.get("", response_model=list[TenantPublic])
async def list_tenants(db: DB):
    tenants = await tenant_service.list_tenants(db)
    return [TenantPublic.model_validate(t) for t in tenants]


@router.get("/current", response_model=TenantRead)
async def get_current_tenant(user: CurrentUser, db: DB):
    tenant = await tenant_service.get_tenant(user.tenant_id, db)
    return TenantRead.model_validate(tenant)


@router.put("/current", response_model=TenantRead)
async def update_current_tenant(data: TenantUpdate, user: AdminUser, db: DB, audit: Audit):
    tenant = await tenant_service.update_tenant(user.tenant_id, data, db, audit, user.id)
    return TenantRead.model_validate(tenant)
