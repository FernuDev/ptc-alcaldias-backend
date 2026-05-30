from datetime import datetime

from pydantic import BaseModel


class NotificacionRead(BaseModel):
    id: str
    user_id: str
    tenant_id: str
    tipo: str
    titulo: str
    cuerpo: str
    href: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    leida: bool
    fecha: datetime

    model_config = {"from_attributes": True}


class NotificacionConteo(BaseModel):
    total: int
    no_leidas: int


class NotificacionesList(BaseModel):
    items: list[NotificacionRead]
    total: int
    no_leidas: int
