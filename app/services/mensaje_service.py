"""Servicio del canal de mensajería monitor ↔ campo.

Mensajes de texto o notas de voz entre el monitor (oficina) y la cuadrilla en
calle, opcionalmente ligados a una tarea. El tenant SIEMPRE se deriva de
``user.tenant_id`` y se filtra por ``WHERE tenant_id``.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.campo import Mensaje, Tarea
from app.models.cuadrilla import Cuadrilla
from app.models.user import User


async def enviar(
    cuadrilla_id: str,
    autor_tipo: str,
    tipo: str,
    user: User,
    db: AsyncSession,
    *,
    texto: str | None = None,
    nota_voz_url: str | None = None,
    tarea_id: str | None = None,
) -> Mensaje:
    """Envía un mensaje (``texto`` o ``voz``) al canal de la cuadrilla.

    Valida la cuadrilla (y la tarea, si se pasa) dentro del tenant del usuario, y
    que el contenido sea coherente con ``tipo`` (texto -> ``texto``; voz ->
    ``nota_voz_url``). ``autor_id`` se rellena con el id del usuario emisor.
    """
    if tipo == "texto" and not texto:
        raise ConflictError("Un mensaje de texto requiere 'texto'.")
    if tipo == "voz" and not nota_voz_url:
        raise ConflictError("Una nota de voz requiere 'nota_voz_url'.")

    cuad = await db.execute(
        select(Cuadrilla).where(
            Cuadrilla.id == cuadrilla_id, Cuadrilla.tenant_id == user.tenant_id
        )
    )
    if cuad.scalar_one_or_none() is None:
        raise NotFoundError("Cuadrilla", cuadrilla_id)

    if tarea_id is not None:
        tarea = await db.execute(
            select(Tarea).where(
                Tarea.id == tarea_id, Tarea.tenant_id == user.tenant_id
            )
        )
        if tarea.scalar_one_or_none() is None:
            raise NotFoundError("Tarea", tarea_id)

    msg = Mensaje(
        tenant_id=user.tenant_id,
        cuadrilla_id=cuadrilla_id,
        tarea_id=tarea_id,
        autor_tipo=autor_tipo,
        autor_id=user.id,
        tipo=tipo,
        texto=texto,
        nota_voz_url=nota_voz_url,
    )
    db.add(msg)
    await db.flush()
    return msg


async def listar(
    user: User,
    db: AsyncSession,
    *,
    cuadrilla_id: str | None = None,
    tarea_id: str | None = None,
    limit: int = 100,
) -> list[Mensaje]:
    """Lista mensajes del tenant, filtrando por cuadrilla y/o tarea.

    Orden cronológico ascendente (los más antiguos primero, como un chat).
    """
    stmt = select(Mensaje).where(Mensaje.tenant_id == user.tenant_id)
    if cuadrilla_id is not None:
        stmt = stmt.where(Mensaje.cuadrilla_id == cuadrilla_id)
    if tarea_id is not None:
        stmt = stmt.where(Mensaje.tarea_id == tarea_id)
    stmt = stmt.order_by(Mensaje.created_at.asc()).limit(limit)

    result = await db.execute(stmt)
    return list(result.scalars().all())
