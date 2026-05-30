from datetime import datetime

from fastapi import APIRouter, Query

from app.core.dependencies import AdminUser, DB
from app.core.exceptions import NotFoundError
from app.schemas.audit import AuditLogRead
from app.schemas.common import PaginatedResponse
from app.services import audit_service

router = APIRouter(prefix="/audit-logs", tags=["audit"])


@router.get("", response_model=PaginatedResponse[AuditLogRead])
async def list_audit_logs(
    user: AdminUser,
    db: DB,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user_id: str | None = None,
    action: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
):
    return await audit_service.query_logs(
        user.tenant_id,
        db,
        page=page,
        page_size=page_size,
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        date_from=date_from,
        date_to=date_to,
    )


@router.get("/{log_id}", response_model=AuditLogRead)
async def get_audit_log(log_id: int, user: AdminUser, db: DB):
    log = await audit_service.get_log(log_id, user.tenant_id, db)
    if log is None:
        raise NotFoundError("AuditLog", str(log_id))
    return log
