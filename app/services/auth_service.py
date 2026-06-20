import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditLogger
from app.core.config import settings
from app.core.exceptions import ConflictError, UnauthorizedError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.auth import ChangePasswordRequest, RegisterRequest, UserBrief


async def authenticate(
    email: str,
    password: str,
    db: AsyncSession,
    audit: AuditLogger,
) -> tuple[str, str, UserBrief]:
    """Authenticate user, return (access_token, refresh_token, user_brief)."""
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(password, user.password_hash):
        await audit.log(
            action="login_failed",
            extra={"email": email},
        )
        raise UnauthorizedError("Email o contrasena incorrectos")

    if not user.is_active:
        await audit.log(
            action="login_failed",
            user_id=user.id,
            tenant_id=user.tenant_id,
            extra={"reason": "inactive"},
        )
        raise UnauthorizedError("Cuenta desactivada")

    area_ids = [a.id for a in user.areas]
    nodo = getattr(user, "nodo", None)
    es_campo = bool(getattr(user, "es_campo", False))
    access_token = create_access_token(
        user.id, user.tenant_id, user.role, area_ids, user.nodo_id, es_campo
    )
    raw_refresh, refresh_hash = create_refresh_token()

    family_id = uuid.uuid4()
    rt = RefreshToken(
        user_id=user.id,
        token_hash=refresh_hash,
        family_id=family_id,
        expires_at=datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        ip_address=audit.ip_address,
        user_agent=audit.user_agent,
    )
    db.add(rt)

    await audit.log(
        action="login",
        user_id=user.id,
        tenant_id=user.tenant_id,
        entity_type="session",
    )

    user_brief = UserBrief(
        id=user.id,
        tenant_id=user.tenant_id,
        email=user.email,
        nombre=user.nombre,
        iniciales=user.iniciales,
        cargo=user.cargo,
        role=user.role,
        areas=area_ids,
        avatar_tone=user.avatar_tone,
        nodo_id=user.nodo_id,
        rol_nivel=nodo.nivel if nodo else None,
        es_campo=es_campo,
    )

    return access_token, raw_refresh, user_brief


async def refresh_tokens(
    raw_token: str,
    db: AsyncSession,
    audit: AuditLogger,
) -> tuple[str, str, str]:
    """Rotate refresh token. Returns (access_token, new_refresh_token, user_id)."""
    token_hash = hash_refresh_token(raw_token)

    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    rt = result.scalar_one_or_none()

    if rt is None:
        raise UnauthorizedError("Refresh token invalido")

    if rt.revoked_at is not None:
        # Token reuse detected — revoke entire family
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == rt.family_id)
            .where(RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )
        await audit.log(
            action="token_reuse_detected",
            user_id=rt.user_id,
            entity_type="session",
            extra={"family_id": str(rt.family_id)},
        )
        raise UnauthorizedError("Token reutilizado — sesion revocada")

    if rt.expires_at < datetime.now(UTC):
        raise UnauthorizedError("Refresh token expirado")

    if rt.replaced_by is not None:
        # Already used
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == rt.family_id)
            .where(RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )
        raise UnauthorizedError("Token reutilizado — sesion revocada")

    # Load user
    user_result = await db.execute(select(User).where(User.id == rt.user_id))
    user = user_result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise UnauthorizedError("Usuario no encontrado o inactivo")

    # Create new refresh token in same family
    new_raw, new_hash = create_refresh_token()
    new_rt = RefreshToken(
        user_id=user.id,
        token_hash=new_hash,
        family_id=rt.family_id,
        expires_at=datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        ip_address=audit.ip_address,
        user_agent=audit.user_agent,
    )
    db.add(new_rt)
    await db.flush()

    # Mark old token as replaced
    rt.replaced_by = new_rt.id
    rt.revoked_at = datetime.now(UTC)

    area_ids = [a.id for a in user.areas]
    access_token = create_access_token(
        user.id,
        user.tenant_id,
        user.role,
        area_ids,
        user.nodo_id,
        bool(getattr(user, "es_campo", False)),
    )

    await audit.log(
        action="token_refresh",
        user_id=user.id,
        tenant_id=user.tenant_id,
        entity_type="session",
    )

    return access_token, new_raw, user.id


async def logout(
    user_id: str,
    db: AsyncSession,
    audit: AuditLogger,
) -> None:
    """Revoke all active refresh tokens for user."""
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id)
        .where(RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    await audit.log(
        action="logout",
        user_id=user_id,
        entity_type="session",
    )


async def register_ciudadano(
    data: RegisterRequest,
    db: AsyncSession,
    audit: AuditLogger,
) -> tuple[str, str, UserBrief]:
    """Registra un ciudadano nuevo. Devuelve (access_token, refresh_token, user_brief)."""
    # Verificar que el email no esté en uso.
    result = await db.execute(select(User).where(User.email == data.email))
    if result.scalar_one_or_none() is not None:
        raise ConflictError("Ya existe una cuenta con este correo")

    # Generar id e iniciales.
    user_id = f"c-{uuid.uuid4().hex[:12]}"
    partes = data.nombre.strip().split()
    iniciales = "".join(p[0].upper() for p in partes[:2]) if partes else "C"

    user = User(
        id=user_id,
        tenant_id=data.tenant_id,
        email=data.email,
        nombre=data.nombre.strip(),
        iniciales=iniciales,
        cargo="Ciudadano",
        role="ciudadano",
        password_hash=hash_password(data.password),
    )
    db.add(user)
    await db.flush()

    area_ids: list[str] = []
    access_token = create_access_token(user.id, user.tenant_id, user.role, area_ids)
    raw_refresh, refresh_hash = create_refresh_token()

    family_id = uuid.uuid4()
    rt = RefreshToken(
        user_id=user.id,
        token_hash=refresh_hash,
        family_id=family_id,
        expires_at=datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        ip_address=audit.ip_address,
        user_agent=audit.user_agent,
    )
    db.add(rt)

    await audit.log(
        action="register",
        user_id=user.id,
        tenant_id=user.tenant_id,
        entity_type="user",
        entity_id=user.id,
    )

    user_brief = UserBrief(
        id=user.id,
        tenant_id=user.tenant_id,
        email=user.email,
        nombre=user.nombre,
        iniciales=user.iniciales,
        cargo=user.cargo,
        role=user.role,
        areas=area_ids,
        avatar_tone=None,
    )

    return access_token, raw_refresh, user_brief


async def change_password(
    user: User,
    data: ChangePasswordRequest,
    db: AsyncSession,
    audit: AuditLogger,
) -> None:
    if not verify_password(data.current_password, user.password_hash):
        raise UnauthorizedError("Contrasena actual incorrecta")
    user.password_hash = hash_password(data.new_password)
    await audit.log(
        action="password_change",
        user_id=user.id,
        tenant_id=user.tenant_id,
        entity_type="user",
        entity_id=user.id,
    )
