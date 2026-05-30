from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.colonia import Colonia


async def list_colonias(tenant_id: str, db: AsyncSession) -> list[Colonia]:
    result = await db.execute(
        select(Colonia).where(Colonia.tenant_id == tenant_id).order_by(Colonia.nombre)
    )
    return list(result.scalars().all())
