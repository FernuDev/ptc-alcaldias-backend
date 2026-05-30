from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditLogger
from app.core.exceptions import NotFoundError
from app.models.contratista import Contratista
from app.schemas.contratista import ContratistaCreate, ContratistaUpdate


async def list_contratistas(db: AsyncSession) -> list[Contratista]:
    result = await db.execute(select(Contratista).order_by(Contratista.id))
    return list(result.scalars().all())


async def create_contratista(
    data: ContratistaCreate, db: AsyncSession, audit: AuditLogger, user_id: str, tenant_id: str
) -> Contratista:
    c = Contratista(
        id=data.id, razon_social=data.razon_social, rfc=data.rfc, calificacion=data.calificacion
    )
    db.add(c)
    await audit.log(action="create", user_id=user_id, tenant_id=tenant_id, entity_type="contratista", entity_id=c.id)
    return c


async def update_contratista(
    contratista_id: str, data: ContratistaUpdate, db: AsyncSession, audit: AuditLogger, user_id: str, tenant_id: str
) -> Contratista:
    result = await db.execute(select(Contratista).where(Contratista.id == contratista_id))
    c = result.scalar_one_or_none()
    if c is None:
        raise NotFoundError("Contratista", contratista_id)
    if data.razon_social is not None:
        c.razon_social = data.razon_social
    if data.rfc is not None:
        c.rfc = data.rfc
    if data.calificacion is not None:
        c.calificacion = data.calificacion
    await audit.log(action="update", user_id=user_id, tenant_id=tenant_id, entity_type="contratista", entity_id=c.id)
    return c


async def delete_contratista(
    contratista_id: str, db: AsyncSession, audit: AuditLogger, user_id: str, tenant_id: str
) -> None:
    result = await db.execute(select(Contratista).where(Contratista.id == contratista_id))
    c = result.scalar_one_or_none()
    if c is None:
        raise NotFoundError("Contratista", contratista_id)
    await db.delete(c)
    await audit.log(action="delete", user_id=user_id, tenant_id=tenant_id, entity_type="contratista", entity_id=contratista_id)
