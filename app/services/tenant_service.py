from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditLogger, compute_changes
from app.core.exceptions import NotFoundError
from app.models.tenant import Tenant
from app.schemas.tenant import TenantUpdate


async def list_tenants(db: AsyncSession) -> list[Tenant]:
    result = await db.execute(select(Tenant).order_by(Tenant.nombre))
    return list(result.scalars().all())


async def get_tenant(tenant_id: str, db: AsyncSession) -> Tenant:
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise NotFoundError("Tenant", tenant_id)
    return tenant


async def update_tenant(
    tenant_id: str,
    data: TenantUpdate,
    db: AsyncSession,
    audit: AuditLogger,
    user_id: str,
) -> Tenant:
    tenant = await get_tenant(tenant_id, db)
    old = {
        "nombre": tenant.nombre,
        "nombre_corto": tenant.nombre_corto,
        "primario": tenant.primario,
    }

    if data.nombre is not None:
        tenant.nombre = data.nombre
    if data.nombre_corto is not None:
        tenant.nombre_corto = data.nombre_corto
    if data.primario is not None:
        tenant.primario = data.primario
    if data.secundario is not None:
        tenant.secundario = data.secundario
    if data.dorado is not None:
        tenant.dorado = data.dorado

    new = {
        "nombre": tenant.nombre,
        "nombre_corto": tenant.nombre_corto,
        "primario": tenant.primario,
    }
    changes = compute_changes(old, new)

    await audit.log(
        action="update",
        user_id=user_id,
        tenant_id=tenant_id,
        entity_type="tenant",
        entity_id=tenant_id,
        changes=changes,
    )

    return tenant
