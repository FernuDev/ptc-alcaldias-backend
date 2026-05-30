from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.notificacion import Notificacion
from app.models.user import User
from app.schemas.notificacion import NotificacionConteo, NotificacionRead, NotificacionesList


async def list_notificaciones(
    user: User,
    db: AsyncSession,
    *,
    limit: int = 20,
    solo_no_leidas: bool = False,
) -> NotificacionesList:
    base = select(Notificacion).where(Notificacion.user_id == user.id)

    # Total count
    total_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(total_q)).scalar() or 0

    # Unread count
    unread_q = select(func.count()).select_from(
        base.where(Notificacion.leida == False).subquery()  # noqa: E712
    )
    no_leidas = (await db.execute(unread_q)).scalar() or 0

    # Items query
    stmt = base
    if solo_no_leidas:
        stmt = stmt.where(Notificacion.leida == False)  # noqa: E712
    stmt = stmt.order_by(Notificacion.fecha.desc()).limit(limit)

    result = await db.execute(stmt)
    items = [NotificacionRead.model_validate(n) for n in result.scalars().all()]

    return NotificacionesList(items=items, total=total, no_leidas=no_leidas)


async def get_conteo(user: User, db: AsyncSession) -> NotificacionConteo:
    total_q = select(func.count()).select_from(Notificacion).where(Notificacion.user_id == user.id)
    total = (await db.execute(total_q)).scalar() or 0

    unread_q = (
        select(func.count())
        .select_from(Notificacion)
        .where(Notificacion.user_id == user.id, Notificacion.leida == False)  # noqa: E712
    )
    no_leidas = (await db.execute(unread_q)).scalar() or 0

    return NotificacionConteo(total=total, no_leidas=no_leidas)


async def marcar_leida(notif_id: str, user: User, db: AsyncSession) -> NotificacionRead:
    result = await db.execute(
        select(Notificacion).where(Notificacion.id == notif_id, Notificacion.user_id == user.id)
    )
    notif = result.scalar_one_or_none()
    if notif is None:
        raise NotFoundError("Notificacion", notif_id)
    notif.leida = True
    return NotificacionRead.model_validate(notif)


async def marcar_todas_leidas(user: User, db: AsyncSession) -> int:
    result = await db.execute(
        update(Notificacion)
        .where(Notificacion.user_id == user.id, Notificacion.leida == False)  # noqa: E712
        .values(leida=True)
    )
    return result.rowcount
