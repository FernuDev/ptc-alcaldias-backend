"""Ruteo de tareas de campo (optimización del orden de visita).

Heurística de vecino más cercano (nearest-neighbor) sobre coordenadas
geográficas: partiendo de un punto de inicio (el centroide de las tareas o la
primera tarea), se visita en cada paso la tarea pendiente más cercana. Es una
aproximación rápida y suficiente para el despacho diario de una cuadrilla; no
pretende ser un TSP óptimo.

Las tareas sin coordenadas (``lat``/``lng`` nulos) se colocan al final del orden,
preservando su secuencia relativa, para no perderlas en la ruta.
"""

from __future__ import annotations

import math

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campo import Tarea


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Distancia en km entre dos coordenadas (fórmula del haversine)."""
    r = 6371.0  # radio terrestre medio (km)
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _centroide(coords: list[tuple[float, float]]) -> tuple[float, float]:
    n = len(coords)
    return (sum(c[0] for c in coords) / n, sum(c[1] for c in coords) / n)


def optimizar_ruta(tareas: list[Tarea]) -> list[Tarea]:
    """Devuelve las tareas reordenadas por vecino más cercano.

    Parte del centroide de las tareas con coordenadas y visita en cada paso la más
    cercana. Las tareas sin coordenadas se anexan al final en su orden original. No
    muta las instancias (solo reordena la lista); la persistencia de ``orden_ruta``
    la hace :func:`asignar_orden_ruta`.
    """
    con_coords = [t for t in tareas if t.lat is not None and t.lng is not None]
    sin_coords = [t for t in tareas if t.lat is None or t.lng is None]

    if len(con_coords) <= 1:
        return con_coords + sin_coords

    coords = [(t.lat, t.lng) for t in con_coords]  # type: ignore[misc]
    actual_lat, actual_lng = _centroide(coords)

    pendientes = list(con_coords)
    ordenadas: list[Tarea] = []
    while pendientes:
        siguiente = min(
            pendientes,
            key=lambda t: _haversine_km(actual_lat, actual_lng, t.lat, t.lng),  # type: ignore[arg-type]
        )
        ordenadas.append(siguiente)
        actual_lat, actual_lng = siguiente.lat, siguiente.lng  # type: ignore[assignment]
        pendientes.remove(siguiente)

    return ordenadas + sin_coords


def asignar_orden_ruta(tareas_ordenadas: list[Tarea]) -> None:
    """Asigna ``orden_ruta`` 1..N a las tareas en el orden dado (in-place)."""
    for i, tarea in enumerate(tareas_ordenadas, start=1):
        tarea.orden_ruta = i


async def generar_ruta_dia(
    cuadrilla_id: str,
    db: AsyncSession,
    *,
    tenant_id: str,
) -> list[Tarea]:
    """Calcula y persiste el orden de ruta de las tareas pendientes de una cuadrilla.

    Toma las tareas ``pendiente`` de la cuadrilla (acotadas al tenant), las ordena
    con :func:`optimizar_ruta`, fija ``orden_ruta`` y deja los cambios en la sesión
    (sin commit; lo confirma la request). Devuelve las tareas ya ordenadas.
    """
    result = await db.execute(
        select(Tarea).where(
            Tarea.tenant_id == tenant_id,
            Tarea.cuadrilla_id == cuadrilla_id,
            Tarea.estado == "pendiente",
        )
    )
    tareas = list(result.scalars().all())
    if not tareas:
        return []

    ordenadas = optimizar_ruta(tareas)
    asignar_orden_ruta(ordenadas)
    await db.flush()
    return ordenadas
