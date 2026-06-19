"""Router del canal de mensajería monitor ↔ campo.

Mensajes de texto o notas de voz entre el monitor (oficina) y la cuadrilla en
calle, opcionalmente ligados a una tarea. La lógica vive en ``mensaje_service``.

Permisos: cualquier perfil operativo que despacha o ejecuta puede usar el canal,
por lo que basta estar autenticado (``CurrentUser``); el ``autor_tipo``
distingue origen monitor/campo. El tenant SIEMPRE proviene del JWT. La
integración registra este router en ``main.py`` (no se toca aquí).
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.core.dependencies import DB, CurrentUser
from app.schemas.campo import MensajeCreate, MensajeRead
from app.services import mensaje_service

router = APIRouter(prefix="/mensajes", tags=["mensajes"])


@router.get("", response_model=list[MensajeRead])
async def list_mensajes(
    user: CurrentUser,
    db: DB,
    cuadrilla_id: str | None = None,
    tarea_id: str | None = None,
    limit: int = Query(100, ge=1, le=500),
):
    """Lista mensajes del tenant (orden cronológico), filtrando por cuadrilla/tarea."""
    mensajes = await mensaje_service.listar(
        user,
        db,
        cuadrilla_id=cuadrilla_id,
        tarea_id=tarea_id,
        limit=limit,
    )
    return [MensajeRead.model_validate(m) for m in mensajes]


@router.post("", response_model=MensajeRead, status_code=201)
async def enviar_mensaje(data: MensajeCreate, user: CurrentUser, db: DB):
    """Envía un mensaje (texto o nota de voz) al canal de la cuadrilla."""
    msg = await mensaje_service.enviar(
        data.cuadrilla_id,
        data.autor_tipo,
        data.tipo,
        user,
        db,
        texto=data.texto,
        nota_voz_url=data.nota_voz_url,
        tarea_id=data.tarea_id,
    )
    return MensajeRead.model_validate(msg)
