import mimetypes

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse

from app.core.dependencies import DB, AdminUser, Audit, CurrentUser
from app.core.exceptions import NotFoundError
from app.schemas.brand import (
    BrandHistoryEntry,
    BrandRead,
    BrandRevertInput,
    BrandUpdate,
)
from app.schemas.tenant import TenantPublic, TenantRead, TenantUpdate
from app.services import brand_service, tenant_service

router = APIRouter(prefix="/tenants", tags=["tenants"])


@router.get("", response_model=list[TenantPublic])
async def list_tenants(db: DB):
    tenants = await tenant_service.list_tenants(db)
    return [TenantPublic.model_validate(t) for t in tenants]


@router.get("/current", response_model=TenantRead)
async def get_current_tenant(user: CurrentUser, db: DB):
    tenant = await tenant_service.get_tenant(user.tenant_id, db)
    return TenantRead.model_validate(tenant)


@router.put("/current", response_model=TenantRead)
async def update_current_tenant(data: TenantUpdate, user: AdminUser, db: DB, audit: Audit):
    tenant = await tenant_service.update_tenant(user.tenant_id, data, db, audit, user.id)
    return TenantRead.model_validate(tenant)


# ── Marca (white-label) ───────────────────────────────────────────────────────
# IMPORTANTE: las rutas literales /current/... se declaran ANTES de
# /{tenant_id}/brand para que "current" no sea capturado como tenant_id.


@router.get("/current/brand", response_model=BrandRead)
async def get_current_brand(user: CurrentUser, db: DB):
    """Marca resuelta (defaults ▸ escalares ▸ overrides) del tenant del usuario."""
    tenant = await brand_service.get_tenant(user.tenant_id, db)
    return brand_service.to_read(tenant)


@router.put("/current/brand", response_model=BrandRead)
async def update_current_brand(data: BrandUpdate, user: AdminUser, db: DB, audit: Audit):
    """Actualiza la marca (solo admin). Versiona e historiza el cambio."""
    tenant = await brand_service.update_brand(user.tenant_id, data, db, audit, user.id)
    return brand_service.to_read(tenant)


@router.post("/current/brand/reset", response_model=BrandRead)
async def reset_current_brand(user: AdminUser, db: DB, audit: Audit):
    """Restablece la marca al tema base MC (limpia overrides)."""
    tenant = await brand_service.reset_brand(user.tenant_id, db, audit, user.id)
    return brand_service.to_read(tenant)


@router.get("/current/brand/history", response_model=list[BrandHistoryEntry])
async def get_current_brand_history(user: AdminUser, db: DB):
    """Historial de versiones de marca del tenant (para revertir)."""
    return await brand_service.list_history(user.tenant_id, db)


@router.post("/current/brand/revert", response_model=BrandRead)
async def revert_current_brand(
    data: BrandRevertInput, user: AdminUser, db: DB, audit: Audit
):
    """Revierte la marca a una versión anterior del historial."""
    tenant = await brand_service.revert_to(
        user.tenant_id, data.version, db, audit, user.id
    )
    return brand_service.to_read(tenant)


@router.post("/current/brand/logo", response_model=BrandRead)
async def upload_current_brand_logo(
    user: AdminUser,
    db: DB,
    audit: Audit,
    file: UploadFile = File(...),
    slot: str = Form("full"),
):
    """Sube un activo de marca (full | mark | login | favicon) al storage."""
    tenant = await brand_service.upload_logo(
        user.tenant_id, slot, file, db, audit, user.id
    )
    return brand_service.to_read(tenant)


@router.get("/brand/asset/{key:path}")
async def serve_brand_asset(key: str, db: DB):
    """Sirve un activo de marca por su clave de storage (PÚBLICO).

    Los logos son públicos por naturaleza (aparecen en el login antes de
    autenticar). Solo se sirven claves referenciadas como activo de marca.
    """
    if not await brand_service.is_public_asset(key, db):
        raise NotFoundError("BrandAsset", key)
    path = brand_service.asset_path(key)
    if path is None:
        raise NotFoundError("BrandAsset", key)
    media_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    # Endurecimiento para SVG: renderiza bien vía <img>, pero al navegar directo
    # a la URL un SVG con <script> se ejecutaría como documento. ``sandbox`` (sin
    # allow-scripts) lo neutraliza y ``nosniff`` evita MIME sniffing.
    headers = {
        "Content-Security-Policy": "sandbox; default-src 'none'; style-src 'unsafe-inline'",
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "public, max-age=300",
    }
    return FileResponse(path, media_type=media_type, headers=headers)


@router.get("/{tenant_id}/brand", response_model=BrandRead)
async def get_tenant_brand(tenant_id: str, db: DB):
    """Marca pública resuelta de un tenant (sin auth): login y app ciudadana."""
    tenant = await brand_service.get_tenant(tenant_id, db)
    return brand_service.to_read(tenant)
