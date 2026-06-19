from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditLogger
from app.core.database import get_db
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.permissions import Permission, has_permission
from app.core.security import JWTError, decode_access_token
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)


class TokenPayload:
    """Parsed JWT claims."""

    def __init__(self, data: dict):
        self.user_id: str = data["sub"]
        self.tenant_id: str = data["tenant_id"]
        self.role: str = data["role"]
        self.areas: list[str] = data.get("areas", [])


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    if credentials is None:
        raise UnauthorizedError("Token de acceso requerido")
    try:
        payload = decode_access_token(credentials.credentials)
    except JWTError:
        raise UnauthorizedError("Token invalido o expirado")

    user_id = payload.get("sub")
    if not user_id:
        raise UnauthorizedError("Token invalido")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise UnauthorizedError("Usuario no encontrado o inactivo")
    return user


async def get_token_payload(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> TokenPayload:
    if credentials is None:
        raise UnauthorizedError("Token de acceso requerido")
    try:
        payload = decode_access_token(credentials.credentials)
    except JWTError:
        raise UnauthorizedError("Token invalido o expirado")
    return TokenPayload(payload)


def require_role(*roles: str):
    """Dependency factory that enforces the user has one of the given roles."""

    async def _check(user: Annotated[User, Depends(get_current_user)]) -> User:
        if user.role not in roles:
            raise ForbiddenError(f"Requiere rol: {', '.join(roles)}")
        return user

    return _check


def require_permission(*perms: Permission | str):
    """Dependency factory that enforces the user's role grants ALL given permissions.

    Consulta la matriz rol->permisos de :mod:`app.core.permissions`. Es análoga a
    :func:`require_role` pero razona sobre capacidades en lugar de roles concretos,
    lo que evita acoplar los endpoints a la lista exacta de roles.
    """

    perm_values = [Permission(p) for p in perms]

    async def _check(user: Annotated[User, Depends(get_current_user)]) -> User:
        missing = [p for p in perm_values if not has_permission(user.role, p)]
        if missing:
            raise ForbiddenError(
                f"Requiere permiso: {', '.join(p.value for p in missing)}"
            )
        return user

    return _check


async def get_audit_logger(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AuditLogger:
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    return AuditLogger(db=db, ip_address=ip, user_agent=ua)


CurrentUser = Annotated[User, Depends(get_current_user)]
AdminUser = Annotated[User, Depends(require_role("admin"))]
DB = Annotated[AsyncSession, Depends(get_db)]
Audit = Annotated[AuditLogger, Depends(get_audit_logger)]

# Atajos por rol para los nuevos perfiles operativos. No reemplazan a los
# existentes (AdminUser, CurrentUser) y conviven con require_permission.
SupervisorUser = Annotated[
    User, Depends(require_role("admin", "director_area", "supervisor"))
]
JefeCuadrillaUser = Annotated[
    User, Depends(require_role("admin", "supervisor", "jefe_cuadrilla"))
]
InspectorUser = Annotated[
    User, Depends(require_role("admin", "supervisor", "inspector"))
]
