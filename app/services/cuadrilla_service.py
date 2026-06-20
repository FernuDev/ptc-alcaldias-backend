import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditLogger, compute_changes
from app.core.exceptions import ForbiddenError, NotFoundError
from app.core.scoping import is_global_scope, user_scope_cuadrilla_ids
from app.models.categoria import Categoria
from app.models.cuadrilla import Cuadrilla, Integrante
from app.models.user import User
from app.schemas.cuadrilla import (
    CuadrillaCreate,
    CuadrillaUpdate,
    IntegranteCreate,
    IntegranteUpdate,
)
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


# ─────────────────────────────────────────────────────────────────────────────
# Integrantes de cuadrilla (RBAC heredado: cada quien gestiona su sub-árbol)
# ─────────────────────────────────────────────────────────────────────────────
async def _cuadrilla_en_alcance(
    db: AsyncSession, user: User, cuadrilla_id: str
) -> Cuadrilla:
    """Carga la cuadrilla validando tenant y alcance del usuario en el árbol."""
    c = (
        await db.execute(
            select(Cuadrilla).where(
                Cuadrilla.id == cuadrilla_id, Cuadrilla.tenant_id == user.tenant_id
            )
        )
    ).scalar_one_or_none()
    if c is None:
        raise NotFoundError("Cuadrilla", cuadrilla_id)
    if not is_global_scope(user):
        scope = set(await user_scope_cuadrilla_ids(db, user) or [])
        if cuadrilla_id not in scope:
            raise ForbiddenError(
                "Esa cuadrilla está fuera de tu alcance en el organigrama"
            )
    return c


async def _sync_integrantes_count(
    db: AsyncSession, cuadrilla: Cuadrilla
) -> None:
    n = (
        await db.execute(
            select(func.count()).select_from(Integrante).where(
                Integrante.cuadrilla_id == cuadrilla.id
            )
        )
    ).scalar() or 0
    cuadrilla.integrantes = int(n)


async def list_integrantes(
    db: AsyncSession, user: User, cuadrilla_id: str
) -> list[Integrante]:
    await _cuadrilla_en_alcance(db, user, cuadrilla_id)
    rows = await db.execute(
        select(Integrante)
        .where(Integrante.cuadrilla_id == cuadrilla_id)
        .order_by(Integrante.rol_campo != "jefe", Integrante.nombre)
    )
    return list(rows.scalars().all())


async def add_integrante(
    db: AsyncSession,
    user: User,
    cuadrilla_id: str,
    data: IntegranteCreate,
    audit: AuditLogger,
) -> Integrante:
    c = await _cuadrilla_en_alcance(db, user, cuadrilla_id)
    ing = Integrante(
        id=str(uuid.uuid4()),
        cuadrilla_id=cuadrilla_id,
        tenant_id=user.tenant_id,
        user_id=data.user_id,
        nombre=data.nombre.strip(),
        rol_campo=data.rol_campo,
        telefono=data.telefono,
        activo=data.activo,
    )
    db.add(ing)
    await db.flush()
    await _sync_integrantes_count(db, c)
    await audit.log(
        action="create",
        user_id=user.id,
        tenant_id=user.tenant_id,
        entity_type="integrante",
        entity_id=ing.id,
        extra={"cuadrilla_id": cuadrilla_id, "nombre": ing.nombre},
    )
    return ing


async def update_integrante(
    db: AsyncSession,
    user: User,
    cuadrilla_id: str,
    integrante_id: str,
    data: IntegranteUpdate,
    audit: AuditLogger,
) -> Integrante:
    await _cuadrilla_en_alcance(db, user, cuadrilla_id)
    ing = (
        await db.execute(
            select(Integrante).where(
                Integrante.id == integrante_id,
                Integrante.cuadrilla_id == cuadrilla_id,
                Integrante.tenant_id == user.tenant_id,
            )
        )
    ).scalar_one_or_none()
    if ing is None:
        raise NotFoundError("Integrante", integrante_id)
    old = {
        "nombre": ing.nombre,
        "rol_campo": ing.rol_campo,
        "telefono": ing.telefono,
        "activo": ing.activo,
    }
    if data.nombre is not None:
        ing.nombre = data.nombre.strip()
    if data.rol_campo is not None:
        ing.rol_campo = data.rol_campo
    if data.telefono is not None:
        ing.telefono = data.telefono or None
    if data.activo is not None:
        ing.activo = data.activo
    if data.user_id is not None:
        ing.user_id = data.user_id or None
    new = {
        "nombre": ing.nombre,
        "rol_campo": ing.rol_campo,
        "telefono": ing.telefono,
        "activo": ing.activo,
    }
    await audit.log(
        action="update",
        user_id=user.id,
        tenant_id=user.tenant_id,
        entity_type="integrante",
        entity_id=ing.id,
        changes=compute_changes(old, new),
    )
    return ing


async def delete_integrante(
    db: AsyncSession,
    user: User,
    cuadrilla_id: str,
    integrante_id: str,
    audit: AuditLogger,
) -> None:
    c = await _cuadrilla_en_alcance(db, user, cuadrilla_id)
    ing = (
        await db.execute(
            select(Integrante).where(
                Integrante.id == integrante_id,
                Integrante.cuadrilla_id == cuadrilla_id,
                Integrante.tenant_id == user.tenant_id,
            )
        )
    ).scalar_one_or_none()
    if ing is None:
        raise NotFoundError("Integrante", integrante_id)
    await db.delete(ing)
    await db.flush()
    await _sync_integrantes_count(db, c)
    await audit.log(
        action="delete",
        user_id=user.id,
        tenant_id=user.tenant_id,
        entity_type="integrante",
        entity_id=integrante_id,
        extra={"cuadrilla_id": cuadrilla_id},
    )
