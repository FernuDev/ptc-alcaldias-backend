from fastapi import APIRouter, Query

from app.core.dependencies import CurrentUser, DB
from app.schemas.notificacion import NotificacionConteo, NotificacionRead, NotificacionesList
from app.services import notificacion_service

router = APIRouter(prefix="/notificaciones", tags=["notificaciones"])


@router.get("", response_model=NotificacionesList)
async def list_notificaciones(
    user: CurrentUser,
    db: DB,
    limit: int = Query(20, ge=1, le=100),
    solo_no_leidas: bool = Query(False),
):
    return await notificacion_service.list_notificaciones(
        user, db, limit=limit, solo_no_leidas=solo_no_leidas
    )


@router.get("/conteo", response_model=NotificacionConteo)
async def conteo(user: CurrentUser, db: DB):
    return await notificacion_service.get_conteo(user, db)


@router.put("/{notif_id}/leer", response_model=NotificacionRead)
async def marcar_leida(notif_id: str, user: CurrentUser, db: DB):
    return await notificacion_service.marcar_leida(notif_id, user, db)


@router.put("/leer-todas")
async def marcar_todas_leidas(user: CurrentUser, db: DB):
    count = await notificacion_service.marcar_todas_leidas(user, db)
    return {"detail": f"{count} notificaciones marcadas como leidas"}
