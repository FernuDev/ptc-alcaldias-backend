import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.notificacion import Notificacion
from app.models.user import User, user_areas
from app.schemas.notificacion import NotificacionConteo, NotificacionesList, NotificacionRead

logger = logging.getLogger(__name__)

# Roles que reciben notificaciones de gestión por defecto (los que pueden
# atender/gestionar un reporte u obra). El admin siempre recibe; los demás se
# acotan por área cuando hay categoría involucrada.
ROLES_RESPONSABLES = ("admin", "director_area", "supervisor")


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


# ─────────────────────────────────────────────────────────────────────────────
# Motor de notificaciones (escritura en runtime)
# ─────────────────────────────────────────────────────────────────────────────


async def create_notificacion(
    db: AsyncSession,
    *,
    user_id: str,
    tenant_id: str,
    tipo: str,
    titulo: str,
    cuerpo: str,
    href: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
) -> Notificacion:
    """Inserta una notificación in-app para un usuario.

    Genera ``id`` y ``fecha`` automáticamente. La fila se añade a la sesión
    (``db.add``) y se hace ``flush`` para asignar el PK; el commit corre en la
    unidad de trabajo de la request (igual que el resto de servicios).

    Punto de extensión PUSH: tras persistir la notificación in-app, aquí se
    podría encolar/disparar la entrega a un adaptador externo (FCM, APNs o
    Web-Push) leyendo los tokens del usuario destino. Para el demo la entrega
    real es in-app (la UI hace polling sobre ``/notificaciones``), por lo que el
    adaptador queda como gancho opcional y no bloquea el flujo.
    """
    notif = Notificacion(
        id=f"ntf-{uuid.uuid4().hex[:20]}",
        user_id=user_id,
        tenant_id=tenant_id,
        tipo=tipo,
        titulo=titulo,
        cuerpo=cuerpo,
        href=href,
        entity_type=entity_type,
        entity_id=entity_id,
        leida=False,
        fecha=datetime.now(UTC),
    )
    db.add(notif)
    await db.flush()

    # ── Gancho PUSH (no-op en demo) ────────────────────────────────────────
    # await _push_adapter.deliver(notif)  # FCM / APNs / Web-Push
    # Mantener defensivo: un fallo de push nunca debe abortar la transacción.

    return notif


async def _responsables_para(
    db: AsyncSession,
    *,
    tenant_id: str,
    categoria_id: str | None = None,
    excluir_user_id: str | None = None,
) -> list[User]:
    """Resuelve los usuarios del tenant que deben recibir una notificación.

    - Siempre incluye a los ``admin`` del tenant (control total).
    - Incluye a ``director_area``/``supervisor`` activos; si se pasa
      ``categoria_id``, se acotan a quienes tienen esa área asignada (un director
      sin esa área no recibe ruido de otra dirección).
    - Excluye al autor de la acción (``excluir_user_id``) para no auto-notificar.
    """
    stmt = (
        select(User)
        .where(User.tenant_id == tenant_id)
        .where(User.is_active == True)  # noqa: E712
        .where(User.role.in_(ROLES_RESPONSABLES))
    )

    if categoria_id is not None:
        # admin -> siempre; director/supervisor -> solo si tienen el área.
        con_area = (
            select(user_areas.c.user_id)
            .where(user_areas.c.categoria_id == categoria_id)
            .scalar_subquery()
        )
        stmt = stmt.where(or_(User.role == "admin", User.id.in_(con_area)))

    if excluir_user_id is not None:
        stmt = stmt.where(User.id != excluir_user_id)

    result = await db.execute(stmt)
    return list(result.scalars().all())


async def notificar_responsables(
    db: AsyncSession,
    *,
    tenant_id: str,
    tipo: str,
    titulo: str,
    cuerpo: str,
    href: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    categoria_id: str | None = None,
    excluir_user_id: str | None = None,
) -> int:
    """Crea una notificación para cada responsable relevante del tenant.

    Devuelve cuántas notificaciones se generaron. Es robusto: si no hay
    destinatarios devuelve 0 sin error. El llamador debe envolver la invocación
    de forma defensiva (las notificaciones no deben romper el flujo de negocio).
    """
    destinatarios = await _responsables_para(
        db,
        tenant_id=tenant_id,
        categoria_id=categoria_id,
        excluir_user_id=excluir_user_id,
    )
    for u in destinatarios:
        await create_notificacion(
            db,
            user_id=u.id,
            tenant_id=tenant_id,
            tipo=tipo,
            titulo=titulo,
            cuerpo=cuerpo,
            href=href,
            entity_type=entity_type,
            entity_id=entity_id,
        )
    return len(destinatarios)
