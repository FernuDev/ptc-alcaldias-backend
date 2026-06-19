"""Router de Configuración operativa del tenant (módulo 13).

Persiste por tenant: titular, contacto, SLA en días por prioridad, flujos de
atención y checklists de cuadrillas. El SLA aquí definido alimenta el cálculo
de cumplimiento en analítica.
"""

from fastapi import APIRouter

from app.core.dependencies import DB, AdminUser, CurrentUser
from app.models.tenant import Tenant
from app.schemas.config import (
    SLA_DIAS_DEFAULT,
    ConfiguracionRead,
    ConfiguracionUpdate,
)

router = APIRouter(prefix="/config", tags=["config"])


def _serialize(t: Tenant) -> ConfiguracionRead:
    return ConfiguracionRead(
        tenant_id=t.id,
        nombre=t.nombre,
        nombre_corto=t.nombre_corto,
        acronimo=t.acronimo,
        titular_nombre=t.titular_nombre,
        titular_cargo=t.titular_cargo,
        contacto=t.contacto,
        sla_dias=t.sla_dias or dict(SLA_DIAS_DEFAULT),
        flujos=t.flujos or [],
        checklists=t.checklists or {},
    )


@router.get("", response_model=ConfiguracionRead)
async def get_config(user: CurrentUser, db: DB):
    """Configuración del tenant del usuario autenticado."""
    t = await db.get(Tenant, user.tenant_id)
    return _serialize(t)


@router.put("", response_model=ConfiguracionRead)
async def update_config(data: ConfiguracionUpdate, user: AdminUser, db: DB):
    """Actualiza la configuración del tenant (solo admin)."""
    t = await db.get(Tenant, user.tenant_id)
    payload = data.model_dump(exclude_unset=True)
    if "titular_nombre" in payload:
        t.titular_nombre = payload["titular_nombre"]
    if "titular_cargo" in payload:
        t.titular_cargo = payload["titular_cargo"]
    if "contacto" in payload:
        t.contacto = payload["contacto"]
    if payload.get("sla_dias") is not None:
        t.sla_dias = payload["sla_dias"]
    if payload.get("flujos") is not None:
        t.flujos = [f.model_dump() if hasattr(f, "model_dump") else f for f in data.flujos]
    if payload.get("checklists") is not None:
        t.checklists = payload["checklists"]
    await db.flush()
    return _serialize(t)
