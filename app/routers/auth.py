from fastapi import APIRouter, Request

from app.core.config import settings
from app.core.dependencies import DB, Audit, CurrentUser
from app.core.security import limiter
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    RefreshRequest,
    RefreshResponse,
    RegisterRequest,
    TokenResponse,
)
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse)
async def register(data: RegisterRequest, db: DB, audit: Audit):
    """Registro público de ciudadanos."""
    access, refresh, user_brief = await auth_service.register_ciudadano(data, db, audit)
    return TokenResponse(access_token=access, refresh_token=refresh, user=user_brief)


@router.post("/login", response_model=TokenResponse)
@limiter.limit(settings.LOGIN_RATE_LIMIT)
async def login(request: Request, data: LoginRequest, db: DB, audit: Audit):
    access, refresh, user_brief = await auth_service.authenticate(
        data.email, data.password, db, audit
    )
    return TokenResponse(access_token=access, refresh_token=refresh, user=user_brief)


@router.post("/refresh", response_model=RefreshResponse)
async def refresh(data: RefreshRequest, db: DB, audit: Audit):
    access, new_refresh, user_id = await auth_service.refresh_tokens(data.refresh_token, db, audit)
    return RefreshResponse(access_token=access, refresh_token=new_refresh)


@router.post("/logout")
async def logout(user: CurrentUser, db: DB, audit: Audit):
    await auth_service.logout(user.id, db, audit)
    return {"detail": "Sesion cerrada"}


@router.post("/change-password")
async def change_password(data: ChangePasswordRequest, user: CurrentUser, db: DB, audit: Audit):
    await auth_service.change_password(user, data, db, audit)
    return {"detail": "Contrasena actualizada"}
