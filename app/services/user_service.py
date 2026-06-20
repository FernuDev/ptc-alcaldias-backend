from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditLogger, compute_changes
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.security import hash_password
from app.models.categoria import Categoria
from app.models.org_nodo import NIVELES_CAMPO, OrgNodo
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate


async def _resolve_nodo(
    db: AsyncSession, tenant_id: str, nodo_id: str | None
) -> OrgNodo | None:
    """Valida que el nodo exista y pertenezca al tenant (sin confiar en el body)."""
    if not nodo_id:
        return None
    result = await db.execute(
        select(OrgNodo).where(OrgNodo.id == nodo_id, OrgNodo.tenant_id == tenant_id)
    )
    nodo = result.scalar_one_or_none()
    if nodo is None:
        raise ValidationError(
            f"El nodo '{nodo_id}' no existe en este tenant"
        )
    return nodo


def _derive_es_campo(explicit: bool | None, nodo: OrgNodo | None) -> bool:
    if explicit is not None:
        return explicit
    if nodo is not None:
        return nodo.nivel in NIVELES_CAMPO
    return False


async def list_users(tenant_id: str, db: AsyncSession) -> list[User]:
    result = await db.execute(
        select(User).where(User.tenant_id == tenant_id).order_by(User.nombre)
    )
    return list(result.scalars().all())


async def get_user(user_id: str, tenant_id: str, db: AsyncSession) -> User:
    result = await db.execute(
        select(User).where(User.id == user_id, User.tenant_id == tenant_id)
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise NotFoundError("Usuario", user_id)
    return user


async def create_user(
    data: UserCreate,
    tenant_id: str,
    db: AsyncSession,
    audit: AuditLogger,
) -> User:
    existing = await db.execute(select(User).where(User.email == data.email))
    if existing.scalar_one_or_none():
        raise ConflictError(f"Email {data.email} ya registrado")

    nodo = await _resolve_nodo(db, tenant_id, data.nodo_id)

    user = User(
        id=data.id,
        tenant_id=tenant_id,
        email=data.email,
        nombre=data.nombre,
        iniciales=data.iniciales,
        cargo=data.cargo,
        role=data.role,
        avatar_tone=data.avatar_tone,
        password_hash=hash_password(data.password),
        nodo_id=data.nodo_id,
        es_campo=_derive_es_campo(data.es_campo, nodo),
    )

    if data.areas:
        cats_result = await db.execute(
            select(Categoria).where(Categoria.id.in_(data.areas))
        )
        user.areas = list(cats_result.scalars().all())

    db.add(user)
    await db.flush()

    await audit.log(
        action="create",
        user_id=audit.ip_address and user.id,  # self-referential
        tenant_id=tenant_id,
        entity_type="user",
        entity_id=user.id,
        extra={"email": user.email, "role": user.role},
    )

    return user


async def update_user(
    user_id: str,
    data: UserUpdate,
    tenant_id: str,
    db: AsyncSession,
    audit: AuditLogger,
    admin_user_id: str,
) -> User:
    user = await get_user(user_id, tenant_id, db)
    old = {
        "nombre": user.nombre,
        "cargo": user.cargo,
        "role": user.role,
        "is_active": user.is_active,
        "nodo_id": user.nodo_id,
        "es_campo": user.es_campo,
    }

    if data.nombre is not None:
        user.nombre = data.nombre
    if data.cargo is not None:
        user.cargo = data.cargo
    if data.role is not None:
        user.role = data.role
    if data.avatar_tone is not None:
        user.avatar_tone = data.avatar_tone
    if data.is_active is not None:
        user.is_active = data.is_active
    if data.areas is not None:
        cats_result = await db.execute(
            select(Categoria).where(Categoria.id.in_(data.areas))
        )
        user.areas = list(cats_result.scalars().all())
    if data.nodo_id is not None:
        nodo = await _resolve_nodo(db, tenant_id, data.nodo_id)
        user.nodo_id = data.nodo_id
        # Si no se especifica es_campo, re-derivar del nuevo nodo.
        if data.es_campo is None:
            user.es_campo = _derive_es_campo(None, nodo)
    if data.es_campo is not None:
        user.es_campo = data.es_campo

    new = {
        "nombre": user.nombre,
        "cargo": user.cargo,
        "role": user.role,
        "is_active": user.is_active,
        "nodo_id": user.nodo_id,
        "es_campo": user.es_campo,
    }
    changes = compute_changes(old, new)

    await audit.log(
        action="update",
        user_id=admin_user_id,
        tenant_id=tenant_id,
        entity_type="user",
        entity_id=user.id,
        changes=changes,
    )

    return user


async def delete_user(
    user_id: str,
    tenant_id: str,
    db: AsyncSession,
    audit: AuditLogger,
    admin_user_id: str,
) -> None:
    user = await get_user(user_id, tenant_id, db)
    user.is_active = False

    await audit.log(
        action="delete",
        user_id=admin_user_id,
        tenant_id=tenant_id,
        entity_type="user",
        entity_id=user.id,
    )
