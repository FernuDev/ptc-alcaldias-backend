"""Servicio de turnos de campo (jornadas operativas de las cuadrillas).

Una cuadrilla abre un turno al iniciar su jornada y lo cierra al terminar. Solo
puede existir un turno ``abierto`` por cuadrilla a la vez. El tenant SIEMPRE se
deriva de ``user.tenant_id`` y se filtra por ``WHERE tenant_id``.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditLogger
from app.core.exceptions import ConflictError, NotFoundError
from app.models.campo import Turno
from app.models.cuadrilla import Cuadrilla
from app.models.user import User


async def _turno_abierto_de(
    cuadrilla_id: str, tenant_id: str, db: AsyncSession
) -> Turno | None:
    result = await db.execute(
        select(Turno).where(
            Turno.tenant_id == tenant_id,
            Turno.cuadrilla_id == cuadrilla_id,
            Turno.estado == "abierto",
        )
    )
    return result.scalar_one_or_none()


async def abrir_turno(
    cuadrilla_id: str,
    user: User,
    db: AsyncSession,
    audit: AuditLogger | None = None,
) -> Turno:
    """Abre un turno para la cuadrilla. Falla si ya hay uno abierto.

    Valida que la cuadrilla exista dentro del tenant del usuario.
    """
    cuad = await db.execute(
        select(Cuadrilla).where(
            Cuadrilla.id == cuadrilla_id, Cuadrilla.tenant_id == user.tenant_id
        )
    )
    if cuad.scalar_one_or_none() is None:
        raise NotFoundError("Cuadrilla", cuadrilla_id)

    if await _turno_abierto_de(cuadrilla_id, user.tenant_id, db) is not None:
        raise ConflictError(f"La cuadrilla {cuadrilla_id} ya tiene un turno abierto.")

    turno = Turno(
        tenant_id=user.tenant_id,
        cuadrilla_id=cuadrilla_id,
        inicio=datetime.now(UTC),
        estado="abierto",
    )
    db.add(turno)
    await db.flush()

    if audit is not None:
        await audit.log(
            action="create",
            user_id=user.id,
            tenant_id=user.tenant_id,
            entity_type="turno",
            entity_id=turno.id,
            extra={"cuadrilla_id": cuadrilla_id},
        )
    return turno


async def cerrar_turno(
    turno_id: str,
    user: User,
    db: AsyncSession,
    audit: AuditLogger | None = None,
) -> Turno:
    """Cierra un turno abierto del tenant. Falla si no existe o ya está cerrado."""
    result = await db.execute(
        select(Turno).where(Turno.id == turno_id, Turno.tenant_id == user.tenant_id)
    )
    turno = result.scalar_one_or_none()
    if turno is None:
        raise NotFoundError("Turno", turno_id)
    if turno.estado == "cerrado":
        raise ConflictError("El turno ya está cerrado.")

    turno.estado = "cerrado"
    turno.fin = datetime.now(UTC)
    await db.flush()

    if audit is not None:
        await audit.log(
            action="update",
            user_id=user.id,
            tenant_id=user.tenant_id,
            entity_type="turno",
            entity_id=turno.id,
            changes={"estado": {"old": "abierto", "new": "cerrado"}},
        )
    return turno


async def turnos_activos(tenant_id: str, db: AsyncSession) -> list[Turno]:
    """Lista los turnos abiertos del tenant (uno por cuadrilla activa)."""
    result = await db.execute(
        select(Turno)
        .where(Turno.tenant_id == tenant_id, Turno.estado == "abierto")
        .order_by(Turno.inicio.desc())
    )
    return list(result.scalars().all())
