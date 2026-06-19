"""Pruebas de la analítica por intents: el alcance por área/tenant se respeta
porque se delega en los servicios existentes (datos reales sembrados)."""

import pytest
from sqlalchemy import select

from app.agente import analytics
from app.models.user import User
from app.services import stats_service


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


async def test_volumen_anclado_al_dato_mas_reciente(db):
    # Regresión: el volumen ancla la ventana a max(fecha_creacion), no al reloj
    # real. Con datos de demo "congelados" en el pasado, una ventana basada en
    # datetime.now() no solaparía y la gráfica quedaría vacía. Una ventana de 7
    # días desde el reporte más reciente debe incluir al menos ese día.
    admin = await _user(db, "mc-admin")
    datos = await stats_service.volumen_por_dia(admin, db, dias=7)
    assert datos, "el volumen no debe quedar vacío con datos sembrados"
    assert sum(d.recibidos for d in datos) > 0
