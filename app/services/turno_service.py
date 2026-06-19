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
from app.models.campo import Tarea, Turno
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

    arrastradas = await _arrastrar_tareas(turno.cuadrilla_id, user, db)
    if arrastradas and audit is not None:
        await audit.log(
            action="update",
            user_id=user.id,
            tenant_id=user.tenant_id,
            entity_type="turno",
            entity_id=turno.id,
            extra={"carry_over": arrastradas},
        )
    return turno


async def _arrastrar_tareas(
    cuadrilla_id: str, user: User, db: AsyncSession
) -> int:
    """Arrastra (carry-over) las tareas no cerradas de la cuadrilla a la siguiente
    jornada: crea una continuación encadenada por ``carry_over_de`` con
    ``intento_n`` incrementado, sin borrar la original (REQ-07)."""
    abiertas = list(
        (
            await db.execute(
                select(Tarea).where(
                    Tarea.tenant_id == user.tenant_id,
                    Tarea.cuadrilla_id == cuadrilla_id,
                    Tarea.estado != "cerrada",
                )
            )
        )
        .scalars()
        .all()
    )
    if not abiertas:
        return 0
    # No re-arrastrar tareas que ya tienen una continuación (evita duplicar cadenas).
    ya_continuadas = set(
        (
            await db.execute(
                select(Tarea.carry_over_de).where(
                    Tarea.tenant_id == user.tenant_id,
                    Tarea.carry_over_de.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )
    n = 0
    for orig in abiertas:
        if orig.id in ya_continuadas:
            continue
        db.add(
            Tarea(
                tenant_id=user.tenant_id,
                cuadrilla_id=orig.cuadrilla_id,
                integrante_id=orig.integrante_id,
                origen_tipo=orig.origen_tipo,
                reporte_id=orig.reporte_id,
                obra_id=orig.obra_id,
                proyecto_id=orig.proyecto_id,
                proyecto_tarea_id=orig.proyecto_tarea_id,
                titulo=orig.titulo,
                descripcion=orig.descripcion,
                prioridad=orig.prioridad,
                estado="pendiente",
                lat=orig.lat,
                lng=orig.lng,
                colonia_id=orig.colonia_id,
                instrucciones=orig.instrucciones,
                checklist=list(orig.checklist or []),
                carry_over_de=orig.id,
                intento_n=(orig.intento_n or 1) + 1,
            )
        )
        n += 1
    if n:
        await db.flush()
    return n


async def turnos_activos(tenant_id: str, db: AsyncSession) -> list[Turno]:
    """Lista los turnos abiertos del tenant (uno por cuadrilla activa)."""
    result = await db.execute(
        select(Turno)
        .where(Turno.tenant_id == tenant_id, Turno.estado == "abierto")
        .order_by(Turno.inicio.desc())
    )
    return list(result.scalars().all())
