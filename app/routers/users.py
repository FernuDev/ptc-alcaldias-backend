from fastapi import APIRouter

from app.core.dependencies import DB, AdminUser, Audit
from app.models.user import User
from app.schemas.user import UserCreate, UserRead, UserUpdate
from app.services import user_service

router = APIRouter(prefix="/users", tags=["users"])


def _to_read(u: User) -> UserRead:
    nodo = getattr(u, "nodo", None)
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
        nodo_id=u.nodo_id,
        rol_nivel=nodo.nivel if nodo else None,
        es_campo=bool(getattr(u, "es_campo", False)),
    )


@router.get("", response_model=list[UserRead])
async def list_users(user: AdminUser, db: DB):
    users = await user_service.list_users(user.tenant_id, db)
    return [_to_read(u) for u in users]


@router.get("/{user_id}", response_model=UserRead)
async def get_user(user_id: str, user: AdminUser, db: DB):
    u = await user_service.get_user(user_id, user.tenant_id, db)
    return _to_read(u)


@router.post("", response_model=UserRead, status_code=201)
async def create_user(data: UserCreate, user: AdminUser, db: DB, audit: Audit):
    u = await user_service.create_user(data, user.tenant_id, db, audit)
    return _to_read(u)


@router.put("/{user_id}", response_model=UserRead)
async def update_user(user_id: str, data: UserUpdate, user: AdminUser, db: DB, audit: Audit):
    u = await user_service.update_user(user_id, data, user.tenant_id, db, audit, user.id)
    return _to_read(u)


@router.delete("/{user_id}")
async def delete_user(user_id: str, user: AdminUser, db: DB, audit: Audit):
    await user_service.delete_user(user_id, user.tenant_id, db, audit, user.id)
    return {"detail": "Usuario desactivado"}
