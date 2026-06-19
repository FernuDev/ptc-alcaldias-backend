from fastapi import APIRouter

from app.core.dependencies import DB, AdminUser, Audit
from app.schemas.user import UserCreate, UserRead, UserUpdate
from app.services import user_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserRead])
async def list_users(user: AdminUser, db: DB):
    users = await user_service.list_users(user.tenant_id, db)
    result = []
    for u in users:
        result.append(UserRead(
            id=u.id,
            tenant_id=u.tenant_id,
            email=u.email,
            nombre=u.nombre,
            iniciales=u.iniciales,
            cargo=u.cargo,
            role=u.role,
            areas=[a.id for a in u.areas],
            avatar_tone=u.avatar_tone,
            is_active=u.is_active,
        ))
    return result


@router.get("/{user_id}", response_model=UserRead)
async def get_user(user_id: str, user: AdminUser, db: DB):
    u = await user_service.get_user(user_id, user.tenant_id, db)
    return UserRead(
        id=u.id,
        tenant_id=u.tenant_id,
        email=u.email,
        nombre=u.nombre,
        iniciales=u.iniciales,
        cargo=u.cargo,
        role=u.role,
        areas=[a.id for a in u.areas],
        avatar_tone=u.avatar_tone,
        is_active=u.is_active,
    )


@router.post("", response_model=UserRead, status_code=201)
async def create_user(data: UserCreate, user: AdminUser, db: DB, audit: Audit):
    u = await user_service.create_user(data, user.tenant_id, db, audit)
    return UserRead(
        id=u.id,
        tenant_id=u.tenant_id,
        email=u.email,
        nombre=u.nombre,
        iniciales=u.iniciales,
        cargo=u.cargo,
        role=u.role,
        areas=[a.id for a in u.areas],
        avatar_tone=u.avatar_tone,
        is_active=u.is_active,
    )


@router.put("/{user_id}", response_model=UserRead)
async def update_user(user_id: str, data: UserUpdate, user: AdminUser, db: DB, audit: Audit):
    u = await user_service.update_user(user_id, data, user.tenant_id, db, audit, user.id)
    return UserRead(
        id=u.id,
        tenant_id=u.tenant_id,
        email=u.email,
        nombre=u.nombre,
        iniciales=u.iniciales,
        cargo=u.cargo,
        role=u.role,
        areas=[a.id for a in u.areas],
        avatar_tone=u.avatar_tone,
        is_active=u.is_active,
    )


@router.delete("/{user_id}")
async def delete_user(user_id: str, user: AdminUser, db: DB, audit: Audit):
    await user_service.delete_user(user_id, user.tenant_id, db, audit, user.id)
    return {"detail": "Usuario desactivado"}
