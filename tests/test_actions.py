"""Pruebas del flujo human-in-the-loop: prepare NO muta, confirm SÍ, y el alcance
se valida al preparar. Todo se revierte (fixture db con rollback)."""

import pytest
from sqlalchemy import select

from app.agente import actions
from app.agente.context import derive_contexto
from app.core.audit import AuditLogger
from app.core.exceptions import NotFoundError
from app.models.reporte import Reporte
from app.models.user import User


async def _user(db, uid: str) -> User:
    return (await db.execute(select(User).where(User.id == uid))).scalar_one()


async def test_prepare_no_muta_y_confirm_ejecuta(db):
    admin = await _user(db, "mc-admin")
    ctx = derive_contexto(admin)

    rid = "MC-RC-0002"
    reporte = (await db.execute(select(Reporte).where(Reporte.id == rid))).scalar_one()
    estado_inicial = reporte.estado
    objetivo = "en_proceso" if estado_inicial != "en_proceso" else "asignado"

    prepared = await actions.preparar_accion(
        db, ctx, admin,
        tipo="cambiar_estado", entity_type="reporte", entity_id=rid,
        params={"estado": objetivo},
    )
    assert prepared.requiere_confirmacion is True

    # Tras PREPARE el reporte NO cambió.
    await db.refresh(reporte)
    assert reporte.estado == estado_inicial

    # Tras CONFIRM sí cambió.
    resp = await actions.confirmar_accion(db, ctx, admin, prepared.accion_id, AuditLogger(db=db))
    assert resp.estado == "confirmada"
    await db.refresh(reporte)
    assert reporte.estado == objetivo


async def test_confirm_dos_veces_falla(db):
    admin = await _user(db, "mc-admin")
    ctx = derive_contexto(admin)
    prepared = await actions.preparar_accion(
        db, ctx, admin, tipo="cambiar_estado", entity_type="reporte",
        entity_id="MC-RC-0003", params={"estado": "en_proceso"},
    )
    audit = AuditLogger(db=db)
    primera = await actions.confirmar_accion(db, ctx, admin, prepared.accion_id, audit)
    segunda = await actions.confirmar_accion(db, ctx, admin, prepared.accion_id, audit)
    assert primera.estado == "confirmada"
    assert segunda.estado == "error"


async def test_confirm_no_encontrada(db):
    admin = await _user(db, "mc-admin")
    ctx = derive_contexto(admin)
    resp = await actions.confirmar_accion(db, ctx, admin, "inexistente", AuditLogger(db=db))
    assert resp.estado == "no_encontrada"


async def test_prepare_fuera_de_alcance_lanza_404(db):
    director = await _user(db, "mc-dir-obras")  # área: bacheo
    ctx = derive_contexto(director)
    otro = (
        await db.execute(
            select(Reporte)
            .where(Reporte.tenant_id == "magdalena-contreras", Reporte.categoria_id != "bacheo")
            .limit(1)
        )
    ).scalar_one()
    with pytest.raises(NotFoundError):
        await actions.preparar_accion(
            db, ctx, director, tipo="cerrar", entity_type="reporte",
            entity_id=otro.id, params={},
        )
