"""Servicio de rastreo GPS de cuadrillas (mapa en vivo del monitor).

Registra pines de ubicación en serie temporal y resuelve la última posición
conocida por cuadrilla para pintar el mapa en vivo. El tenant SIEMPRE se deriva
de ``user.tenant_id`` y se filtra por ``WHERE tenant_id``.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.campo import Ubicacion
from app.models.cuadrilla import Cuadrilla
from app.models.user import User


async def registrar(
    cuadrilla_id: str,
    lat: float,
    lng: float,
    user: User,
    db: AsyncSession,
    *,
    integrante_id: str | None = None,
) -> Ubicacion:
    """Registra un nuevo pin GPS para la cuadrilla (timestamp = ahora).

    Valida que la cuadrilla exista dentro del tenant del usuario.
    """
    cuad = await db.execute(
        select(Cuadrilla).where(
            Cuadrilla.id == cuadrilla_id, Cuadrilla.tenant_id == user.tenant_id
        )
    )
    if cuad.scalar_one_or_none() is None:
        raise NotFoundError("Cuadrilla", cuadrilla_id)

    ubic = Ubicacion(
        tenant_id=user.tenant_id,
        cuadrilla_id=cuadrilla_id,
        integrante_id=integrante_id,
        lat=lat,
        lng=lng,
        timestamp=datetime.now(UTC),
    )
    db.add(ubic)
    await db.flush()
    return ubic


async def posiciones_actuales(tenant_id: str, db: AsyncSession) -> list[Ubicacion]:
    """Última ``Ubicacion`` por cuadrilla del tenant (para el mapa en vivo).

    Usa una subconsulta con el ``max(timestamp)`` por cuadrilla y se queda con la
    fila más reciente de cada una. Devuelve a lo sumo un pin por cuadrilla.
    """
    ultimas = (
        select(
            Ubicacion.cuadrilla_id.label("cuadrilla_id"),
            func.max(Ubicacion.timestamp).label("max_ts"),
        )
        .where(Ubicacion.tenant_id == tenant_id)
        .group_by(Ubicacion.cuadrilla_id)
        .subquery()
    )

    stmt = (
        select(Ubicacion)
        .join(
            ultimas,
            (Ubicacion.cuadrilla_id == ultimas.c.cuadrilla_id)
            & (Ubicacion.timestamp == ultimas.c.max_ts),
        )
        .where(Ubicacion.tenant_id == tenant_id)
        .order_by(Ubicacion.cuadrilla_id)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())
