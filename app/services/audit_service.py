import math
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.schemas.audit import AuditLogRead
from app.schemas.common import PaginatedResponse


async def query_logs(
    tenant_id: str,
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 50,
    user_id: str | None = None,
    action: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> PaginatedResponse[AuditLogRead]:
    stmt = select(AuditLog).where(AuditLog.tenant_id == tenant_id)

    if user_id:
        stmt = stmt.where(AuditLog.user_id == user_id)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    if date_from:
        stmt = stmt.where(AuditLog.timestamp >= date_from)
    if date_to:
        stmt = stmt.where(AuditLog.timestamp <= date_to)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = stmt.order_by(AuditLog.timestamp.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(stmt)
    logs = list(result.scalars().all())
    items = [AuditLogRead.model_validate(log) for log in logs]

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=math.ceil(total / page_size) if page_size else 1,
    )


async def get_log(log_id: int, tenant_id: str, db: AsyncSession) -> AuditLogRead | None:
    result = await db.execute(
        select(AuditLog).where(AuditLog.id == log_id, AuditLog.tenant_id == tenant_id)
    )
    log = result.scalar_one_or_none()
    if log is None:
        return None
    return AuditLogRead.model_validate(log)
