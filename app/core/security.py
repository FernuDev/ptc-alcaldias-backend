import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import bcrypt as _bcrypt
from jose import JWTError, jwt
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings

# Bcrypt cost factor. Unificado entre la app y scripts/seed.py.
BCRYPT_ROUNDS = 12

# Rate limiter compartido (slowapi). Se instancia aquí —fuera de app.main—
# para que los routers puedan decorar endpoints sin importación circular.
# app.main registra este mismo objeto en app.state.limiter y añade el
# middleware + exception handler.
limiter = Limiter(key_func=get_remote_address)


def hash_password(password: str) -> str:
    return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(
    user_id: str,
    tenant_id: str,
    role: str,
    areas: list[str],
    nodo_id: str | None = None,
    es_campo: bool = False,
) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "role": role,
        "areas": areas,
        # R5 · REQ-17: contexto organizacional (informativo; la autorización
        # se resuelve sobre el User vivo, no sobre el token).
        "nodo_id": nodo_id,
        "es_campo": es_campo,
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Decode and verify an access token. Raises JWTError on failure."""
    return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])


def create_refresh_token() -> tuple[str, str]:
    """Return (raw_token, sha256_hash) pair."""
    raw = str(uuid.uuid4())
    hashed = hashlib.sha256(raw.encode()).hexdigest()
    return raw, hashed


def hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


__all__ = [
    "hash_password",
    "verify_password",
    "create_access_token",
    "decode_access_token",
    "create_refresh_token",
    "hash_refresh_token",
    "limiter",
    "BCRYPT_ROUNDS",
    "JWTError",
]
