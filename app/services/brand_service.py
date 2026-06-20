"""Servicio de Marca (white-label) por tenant.

Responsabilidades:
- **Resolver** la marca efectiva de un tenant: defaults MC ▸ escalares
  (``primario``/``secundario``/``dorado``/``escudo_path``) ▸ overrides en
  ``tenant.brand``. Así un tenant sin marca configurada se ve como hoy, y uno
  con ``primario`` propio (p. ej. Tlalpan) hereda su color sin documento completo.
- **Actualizar** la marca: hace merge profundo del patch, escribe un snapshot en
  ``tenant_brand_history``, incrementa ``brand_version`` y sincroniza los
  escalares denormalizados que consumen PDF/login/público.
- **Historial / revertir / restablecer** al tema base.
- **Subir logos** reutilizando el storage existente (clave opaca por tenant).

No conoce HTTP: los routers pasan ``db``, ``audit`` y el ``user``.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditLogger
from app.core.exceptions import ConflictError, NotFoundError
from app.core.storage import StorageBackend, get_storage
from app.models.brand_history import TenantBrandHistory
from app.models.tenant import Tenant
from app.schemas.brand import (
    DEFAULT_BRAND_TOKENS,
    BrandRead,
    BrandTokens,
    BrandUpdate,
)

# Tipos MIME aceptados para activos de marca (incluye SVG, a diferencia de la
# subida genérica de evidencia). Favicon admite además ICO.
LOGO_CONTENT_TYPES: frozenset[str] = frozenset(
    {"image/svg+xml", "image/png", "image/webp", "image/jpeg"}
)
FAVICON_CONTENT_TYPES: frozenset[str] = LOGO_CONTENT_TYPES | {
    "image/x-icon",
    "image/vnd.microsoft.icon",
}
MAX_LOGO_BYTES = 2 * 1024 * 1024  # 2 MB

# Slots de logo válidos -> campo en BrandLogos.
LOGO_SLOTS = ("full", "mark", "login", "favicon")


def _deep_merge(base: dict, patch: dict) -> dict:
    """Merge recursivo: ``patch`` gana; los ``None`` de ``patch`` se ignoran."""
    out = dict(base)
    for k, v in patch.items():
        if v is None:
            continue
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def resolve_tokens(tenant: Tenant) -> BrandTokens:
    """Marca efectiva del tenant como ``BrandTokens`` (nunca lanza por defaults).

    Orden de precedencia (de menor a mayor):
      1. Defaults MC (``DEFAULT_BRAND_TOKENS``).
      2. Escalares del tenant: ``primario``→primary, ``secundario``→secondary,
         ``dorado``→accent, ``escudo_path``→logo.full (si no hay logo subido).
      3. ``tenant.brand`` (overrides explícitos del panel de Marca).
    """
    base = DEFAULT_BRAND_TOKENS.model_dump()

    scalar_color: dict = {}
    if tenant.primario:
        scalar_color["primary"] = tenant.primario
    if tenant.secundario:
        scalar_color["secondary"] = tenant.secundario
    if tenant.dorado:
        scalar_color["accent"] = tenant.dorado
    if scalar_color:
        base = _deep_merge(base, {"color": scalar_color})

    # Logo: prioriza el subido (logo_path); cae al escudo institucional.
    scalar_logo: dict = {}
    if tenant.logo_path:
        scalar_logo["full"] = tenant.logo_path
    elif tenant.escudo_path:
        scalar_logo["full"] = tenant.escudo_path
    if tenant.escudo_path and not tenant.logo_path:
        scalar_logo.setdefault("login", tenant.escudo_path)
    if tenant.favicon_path:
        scalar_logo["favicon"] = tenant.favicon_path
    if scalar_logo:
        base = _deep_merge(base, {"logo": scalar_logo})

    if tenant.brand:
        base = _deep_merge(base, tenant.brand)

    # Validación final: si por algún motivo el documento es inválido, caemos a
    # defaults en vez de romper la plataforma (principio: fallback siempre).
    try:
        return BrandTokens.model_validate(base)
    except Exception:
        return BrandTokens()


def to_read(tenant: Tenant) -> BrandRead:
    return BrandRead(
        tenant_id=tenant.id,
        version=tenant.brand_version or 1,
        tokens=resolve_tokens(tenant),
        updated_at=getattr(tenant, "updated_at", None),
        is_default=tenant.brand is None,
    )


async def get_tenant(tenant_id: str, db: AsyncSession) -> Tenant:
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise NotFoundError("Tenant", tenant_id)
    return tenant


def _sync_denormalized(tenant: Tenant, tokens: BrandTokens) -> None:
    """Refleja los tokens clave en columnas escalares legacy (PDF/login/público)."""
    tenant.primario = tokens.color.primary
    tenant.secundario = tokens.color.secondary
    tenant.dorado = tokens.color.accent
    if tokens.logo.full:
        tenant.logo_path = tokens.logo.full
    if tokens.logo.favicon:
        tenant.favicon_path = tokens.logo.favicon


async def _snapshot(
    tenant: Tenant, tokens: BrandTokens, db: AsyncSession, user_id: str | None
) -> None:
    db.add(
        TenantBrandHistory(
            id=str(uuid.uuid4()),
            tenant_id=tenant.id,
            version=tenant.brand_version,
            snapshot=tokens.model_dump(),
            updated_by=user_id,
        )
    )


async def update_brand(
    tenant_id: str,
    patch: BrandUpdate,
    db: AsyncSession,
    audit: AuditLogger,
    user_id: str,
) -> Tenant:
    """Aplica un patch parcial, versiona, snapshotea e historiza."""
    tenant = await get_tenant(tenant_id, db)
    current = resolve_tokens(tenant)

    patch_dict = patch.model_dump(exclude_unset=True, exclude_none=False)
    merged = _deep_merge(current.model_dump(), patch_dict)
    new_tokens = BrandTokens.model_validate(merged)  # valida hex/radius/fuente

    tenant.brand = new_tokens.model_dump()
    tenant.brand_version = (tenant.brand_version or 1) + 1
    _sync_denormalized(tenant, new_tokens)
    await _snapshot(tenant, new_tokens, db, user_id)

    await audit.log(
        action="update",
        user_id=user_id,
        tenant_id=tenant_id,
        entity_type="tenant_brand",
        entity_id=tenant_id,
        extra={"version": tenant.brand_version},
    )
    await db.flush()
    return tenant


async def reset_brand(
    tenant_id: str, db: AsyncSession, audit: AuditLogger, user_id: str
) -> Tenant:
    """Restablece al tema base MC (limpia overrides; conserva el primario escalar)."""
    tenant = await get_tenant(tenant_id, db)
    tenant.brand = None
    tenant.brand_version = (tenant.brand_version or 1) + 1
    base = resolve_tokens(tenant)
    await _snapshot(tenant, base, db, user_id)
    await audit.log(
        action="update",
        user_id=user_id,
        tenant_id=tenant_id,
        entity_type="tenant_brand",
        entity_id=tenant_id,
        extra={"version": tenant.brand_version, "reset": True},
    )
    await db.flush()
    return tenant


async def list_history(
    tenant_id: str, db: AsyncSession, limit: int = 50
) -> list[TenantBrandHistory]:
    result = await db.execute(
        select(TenantBrandHistory)
        .where(TenantBrandHistory.tenant_id == tenant_id)
        .order_by(TenantBrandHistory.version.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def revert_to(
    tenant_id: str,
    version: int,
    db: AsyncSession,
    audit: AuditLogger,
    user_id: str,
) -> Tenant:
    """Revierte la marca al snapshot de ``version`` del historial."""
    tenant = await get_tenant(tenant_id, db)
    result = await db.execute(
        select(TenantBrandHistory).where(
            TenantBrandHistory.tenant_id == tenant_id,
            TenantBrandHistory.version == version,
        )
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        raise NotFoundError("TenantBrandHistory", f"{tenant_id}@v{version}")

    tokens = BrandTokens.model_validate(entry.snapshot)
    tenant.brand = tokens.model_dump()
    tenant.brand_version = (tenant.brand_version or 1) + 1
    _sync_denormalized(tenant, tokens)
    await _snapshot(tenant, tokens, db, user_id)
    await audit.log(
        action="update",
        user_id=user_id,
        tenant_id=tenant_id,
        entity_type="tenant_brand",
        entity_id=tenant_id,
        extra={"version": tenant.brand_version, "reverted_from": version},
    )
    await db.flush()
    return tenant


async def upload_logo(
    tenant_id: str,
    slot: str,
    file: UploadFile,
    db: AsyncSession,
    audit: AuditLogger,
    user_id: str,
) -> Tenant:
    """Sube un activo de marca al storage y lo asocia al ``slot`` indicado.

    ``slot`` ∈ {full, mark, login, favicon}. Persiste la **clave de storage** en
    el documento de marca (``logo.<slot>``); el servido público lo resuelve el
    router (``GET /tenants/brand/asset/{key}``).
    """
    if slot not in LOGO_SLOTS:
        raise ConflictError(
            f"Slot de logo inválido: {slot!r}. Válidos: {', '.join(LOGO_SLOTS)}."
        )

    raw = await file.read()
    if not raw:
        raise ConflictError("El archivo está vacío.")
    if len(raw) > MAX_LOGO_BYTES:
        raise ConflictError(
            f"El logo excede el límite de {MAX_LOGO_BYTES // (1024 * 1024)} MB."
        )
    content_type = (file.content_type or "").lower()
    allowed = FAVICON_CONTENT_TYPES if slot == "favicon" else LOGO_CONTENT_TYPES
    if content_type not in allowed:
        raise ConflictError(
            f"Tipo no permitido ({content_type or 'desconocido'}). "
            f"Permitidos: {', '.join(sorted(allowed))}."
        )

    tenant = await get_tenant(tenant_id, db)
    storage = get_storage()
    key = StorageBackend.build_key(
        tenant_id, file.filename or f"brand-{slot}.{_ext(content_type)}"
    )
    await storage.save(raw, key, content_type)

    # Merge del slot en el documento de marca + denormalización.
    tokens = resolve_tokens(tenant)
    logo_patch = {slot: key}
    new_tokens = BrandTokens.model_validate(
        _deep_merge(tokens.model_dump(), {"logo": logo_patch})
    )
    tenant.brand = new_tokens.model_dump()
    tenant.brand_version = (tenant.brand_version or 1) + 1
    if slot == "favicon":
        tenant.favicon_path = key
    elif slot == "full":
        tenant.logo_path = key
    await _snapshot(tenant, new_tokens, db, user_id)
    await audit.log(
        action="update",
        user_id=user_id,
        tenant_id=tenant_id,
        entity_type="tenant_brand",
        entity_id=tenant_id,
        extra={"logo_slot": slot, "key": key, "size_bytes": len(raw)},
    )
    await db.flush()
    return tenant


def _ext(content_type: str) -> str:
    return {
        "image/svg+xml": "svg",
        "image/png": "png",
        "image/webp": "webp",
        "image/jpeg": "jpg",
        "image/x-icon": "ico",
        "image/vnd.microsoft.icon": "ico",
    }.get(content_type, "bin")


def asset_path(key: str) -> Path | None:
    """Ruta local del activo de marca, o ``None`` si no existe (servido público)."""
    return get_storage().get_path(key)


async def is_public_asset(key: str, db: AsyncSession) -> bool:
    """True solo si ``key`` es un activo de marca del tenant que la prefija.

    El servido público de activos es por *clave de storage* (``<tenant>/<uuid>``).
    Para que esto no filtre evidencia u otros uploads (mismo directorio base) ni
    permita **referencias cruzadas** (que un tenant exponga la clave de otro),
    solo se sirve una clave si:
      1. tiene el formato ``<tenant_id>/<archivo>``, y
      2. ese mismo tenant (el dueño por prefijo) la referencia como logo/favicon.
    Así un tenant nunca puede publicar activos fuera de su propio prefijo.
    """
    owner_id, sep, _ = key.partition("/")
    if not sep or not owner_id:
        return False
    tenant = (
        await db.execute(select(Tenant).where(Tenant.id == owner_id))
    ).scalar_one_or_none()
    if tenant is None:
        return False
    if key in (tenant.logo_path, tenant.favicon_path):
        return True
    logos = (tenant.brand or {}).get("logo") or {}
    return key in logos.values()
