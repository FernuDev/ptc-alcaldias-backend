from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditLogger, compute_changes
from app.core.exceptions import ConflictError, NotFoundError
from app.core.security import hash_password
from app.models.categoria import Categoria
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate


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
    old = {"nombre": user.nombre, "cargo": user.cargo, "role": user.role, "is_active": user.is_active}

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

    new = {"nombre": user.nombre, "cargo": user.cargo, "role": user.role, "is_active": user.is_active}
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
