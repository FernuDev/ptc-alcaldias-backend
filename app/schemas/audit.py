from datetime import datetime
from typing import Any

from pydantic import BaseModel, field_serializer


class AuditLogRead(BaseModel):
    id: int
    timestamp: datetime
    user_id: str | None = None
    tenant_id: str | None = None
    action: str
    entity_type: str | None = None
    entity_id: str | None = None
    changes: dict[str, Any] | None = None
    ip_address: Any | None = None
    user_agent: str | None = None
    extra: dict[str, Any] | None = None

    @field_serializer("ip_address")
    @classmethod
    def serialize_ip(cls, v: Any) -> str | None:
        return str(v) if v is not None else None

    model_config = {"from_attributes": True}
