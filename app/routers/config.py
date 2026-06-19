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
    STORAGE_SCHEME_DEFAULT,
    ZONA_PARAMS_DEFAULT,
    ConfiguracionRead,
    ConfiguracionUpdate,
    StorageNasConfig,
    TestStorageInput,
    TestStorageResult,
    ZonaParams,
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
        zona_params=ZonaParams(**{**ZONA_PARAMS_DEFAULT, **(t.zona_params or {})}),
        storage_scheme=t.storage_scheme or STORAGE_SCHEME_DEFAULT,
        storage_config=(
            StorageNasConfig(**t.storage_config) if t.storage_config else None
        ),
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
    if payload.get("zona_params") is not None:
        t.zona_params = data.zona_params.model_dump()
    if "storage_scheme" in payload and payload["storage_scheme"] is not None:
        t.storage_scheme = payload["storage_scheme"]
    if payload.get("storage_config") is not None:
        t.storage_config = data.storage_config.model_dump()
    await db.flush()
    return _serialize(t)


@router.post("/storage/test", response_model=TestStorageResult)
async def test_storage_connection(data: TestStorageInput, user: AdminUser):
    """Prueba (mock) la conexión a un NAS/almacenamiento del cliente.

    No persiste nada: las credenciales recibidas son transitorias y se descartan.
    En producción esto haría un handshake real contra el endpoint S3/SMB/NFS."""
    target = (data.endpoint or data.host or "").strip()
    if not target:
        return TestStorageResult(
            ok=False,
            latency_ms=0,
            message="Indica un host o endpoint para probar la conexión.",
        )
    # Latencia simulada determinista (no aleatoria) a partir del destino.
    latency = 20 + (len(target) * 7) % 120
    ok = len(target) >= 4
    message = (
        f"Conexión {data.tipo.upper()} establecida con {target} ({latency} ms)."
        if ok
        else f"No se pudo resolver «{target}»."
    )
    return TestStorageResult(ok=ok, latency_ms=latency, message=message)
