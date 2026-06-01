"""Pruebas de la analítica por intents: el alcance por área/tenant se respeta
porque se delega en los servicios existentes (datos reales sembrados)."""

import pytest
from sqlalchemy import select

from app.agente import analytics
from app.models.user import User


async def _user(db, uid: str) -> User:
    return (await db.execute(select(User).where(User.id == uid))).scalar_one()


async def test_distribucion_categoria_director_solo_su_area(db):
    director = await _user(db, "mc-dir-obras")  # área: bacheo
    datos = await analytics.ejecutar_intent("distribucion_categoria", director, db)
    ids = {d["id"] for d in datos}
    assert ids <= {"bacheo"}


async def test_distribucion_categoria_admin_ve_varias_areas(db):
    admin = await _user(db, "mc-admin")
    datos = await analytics.ejecutar_intent("distribucion_categoria", admin, db)
    ids = {d["id"] for d in datos}
    assert len(ids) > 1


async def test_intent_desconocido_lanza(db):
    admin = await _user(db, "mc-admin")
    with pytest.raises(ValueError):
        await analytics.ejecutar_intent("'; DROP TABLE reportes; --", admin, db)


async def test_kpis_devuelve_objeto(db):
    admin = await _user(db, "mc-admin")
    datos = await analytics.ejecutar_intent("kpis", admin, db)
    assert isinstance(datos, dict) and datos
