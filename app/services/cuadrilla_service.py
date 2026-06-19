import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditLogger
from app.core.exceptions import NotFoundError
from app.models.categoria import Categoria
from app.models.cuadrilla import Cuadrilla
from app.schemas.cuadrilla import CuadrillaCreate, CuadrillaUpdate
from app.services import notificacion_service

logger = logging.getLogger(__name__)


async def list_cuadrillas(tenant_id: str, db: AsyncSession) -> list[Cuadrilla]:
    result = await db.execute(
        select(Cuadrilla).where(Cuadrilla.tenant_id == tenant_id).order_by(Cuadrilla.id)
    )
    return list(result.scalars().all())


async def create_cuadrilla(
    data: CuadrillaCreate, tenant_id: str, db: AsyncSession, audit: AuditLogger, user_id: str
) -> Cuadrilla:
    c = Cuadrilla(
        id=data.id, tenant_id=tenant_id, nombre=data.nombre, integrantes=data.integrantes
    )
    if data.especialidades:
        cats = await db.execute(select(Categoria).where(Categoria.id.in_(data.especialidades)))
        c.especialidades = list(cats.scalars().all())
    db.add(c)
    await db.flush()
    await audit.log(action="create", user_id=user_id, tenant_id=tenant_id, entity_type="cuadrilla", entity_id=c.id)

    # Avisa a los responsables que hay una nueva cuadrilla disponible para despacho.
    # Defensivo: una falla de notificación no debe romper el alta de la cuadrilla.
    try:
        await notificacion_service.notificar_responsables(
            db,
            tenant_id=tenant_id,
            tipo="alerta",
            titulo=f"Nueva cuadrilla disponible · {c.nombre}",
            cuerpo=f"La cuadrilla {c.id} quedó registrada y lista para despacho.",
            href="/cuadrillas",
            entity_type="cuadrilla",
            entity_id=c.id,
            excluir_user_id=user_id,
        )
    except Exception:  # noqa: BLE001 — las notificaciones nunca rompen el flujo
        logger.exception("No se pudo notificar el alta de la cuadrilla %s", c.id)

    return c


async def update_cuadrilla(
    cuadrilla_id: str, data: CuadrillaUpdate, tenant_id: str, db: AsyncSession, audit: AuditLogger, user_id: str
) -> Cuadrilla:
    result = await db.execute(
        select(Cuadrilla).where(Cuadrilla.id == cuadrilla_id, Cuadrilla.tenant_id == tenant_id)
    )
    c = result.scalar_one_or_none()
    if c is None:
        raise NotFoundError("Cuadrilla", cuadrilla_id)
    if data.nombre is not None:
        c.nombre = data.nombre
    if data.integrantes is not None:
        c.integrantes = data.integrantes
    if data.especialidades is not None:
        cats = await db.execute(select(Categoria).where(Categoria.id.in_(data.especialidades)))
        c.especialidades = list(cats.scalars().all())
    await audit.log(action="update", user_id=user_id, tenant_id=tenant_id, entity_type="cuadrilla", entity_id=c.id)
    return c


async def delete_cuadrilla(
    cuadrilla_id: str, tenant_id: str, db: AsyncSession, audit: AuditLogger, user_id: str
) -> None:
    result = await db.execute(
        select(Cuadrilla).where(Cuadrilla.id == cuadrilla_id, Cuadrilla.tenant_id == tenant_id)
    )
    c = result.scalar_one_or_none()
    if c is None:
        raise NotFoundError("Cuadrilla", cuadrilla_id)
    await db.delete(c)
    await audit.log(action="delete", user_id=user_id, tenant_id=tenant_id, entity_type="cuadrilla", entity_id=cuadrilla_id)
