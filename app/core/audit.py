from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog


class AuditLogger:
    """Writes immutable audit records within the current DB transaction."""

    def __init__(
        self,
        db: AsyncSession,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ):
        self.db = db
        self.ip_address = ip_address
        self.user_agent = user_agent

    async def log(
        self,
        *,
        action: str,
        user_id: str | None = None,
        tenant_id: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        changes: dict | None = None,
        extra: dict | None = None,
    ) -> AuditLog:
        entry = AuditLog(
            user_id=user_id,
            tenant_id=tenant_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            changes=changes,
            ip_address=self.ip_address,
            user_agent=self.user_agent,
            extra=extra,
        )
        self.db.add(entry)
        await self.db.flush()
        return entry


def compute_changes(old: dict, new: dict) -> dict | None:
    """Compute a {field: {old, new}} diff between two dicts. Returns None if no changes."""
    diff = {}
    for key in set(old) | set(new):
        old_val = old.get(key)
        new_val = new.get(key)
        if old_val != new_val:
            diff[key] = {"old": old_val, "new": new_val}
    return diff or None
