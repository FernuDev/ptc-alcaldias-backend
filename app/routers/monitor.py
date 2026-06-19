"""Router del monitor en vivo de cuadrillas (sala de despacho).

Agrega las vistas operativas que consume el tablero del monitor:

  - ``GET  /monitor/posiciones``               pines GPS actuales por cuadrilla.
  - ``GET  /monitor/tareas``                   tareas agrupadas por estado (kanban).
  - ``GET  /monitor/alertas``                  alertas calculadas en vivo.
  - ``POST /monitor/cuadrillas/{id}/generar-ruta``  optimiza el orden de visita.

Todo el monitor exige ``CUADRILLA_DESPACHAR``. La lógica de datos vive en
``tarea_service``, ``ubicacion_service``, ``turno_service`` y ``ruteo``; aquí se
combinan y se calculan las alertas. El tenant SIEMPRE proviene del JWT. La
integración registra este router en ``main.py`` (no se toca aquí).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.dependencies import DB, Audit, require_permission
from app.core.permissions import Permission
from app.models.user import User
from app.schemas.campo import AlertaRead, KanbanRead, PosicionRead, TareaRead
from app.services import ruteo, tarea_service, turno_service, ubicacion_service

router = APIRouter(prefix="/monitor", tags=["monitor"])

DespachaUser = Annotated[
    User, Depends(require_permission(Permission.CUADRILLA_DESPACHAR))
]

# Umbrales de las alertas (en minutos). Razonables para un demo operativo.
_TAREA_VENCIDA_MIN = 4 * 60  # tarea abierta > 4 h
_SLA_RIESGO_MIN = 90  # tarea alta/crítica aún sin llegar a sitio > 90 min
_SIN_MOVIMIENTO_MIN = 30  # cuadrilla en turno sin GPS reciente > 30 min

_ABIERTAS = ("pendiente", "en_ruta", "en_sitio")


def _minutos_desde(ts: datetime | None, ahora: datetime) -> float | None:
    """Minutos transcurridos desde ``ts`` (None si no hay timestamp)."""
    if ts is None:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return (ahora - ts).total_seconds() / 60.0


@router.get("/posiciones", response_model=list[PosicionRead])
async def posiciones(user: DespachaUser, db: DB):
    """Última posición conocida por cuadrilla del tenant (pines del mapa)."""
    pines = await ubicacion_service.posiciones_actuales(user.tenant_id, db)
    return [PosicionRead.model_validate(p) for p in pines]


@router.get("/tareas", response_model=KanbanRead)
async def tareas_kanban(user: DespachaUser, db: DB, cuadrilla_id: str | None = None):
    """Tareas del tenant agrupadas por estado para el tablero kanban."""
    tareas = await tarea_service.list_tareas(user, db, cuadrilla_id=cuadrilla_id)
    # Carry-over: oculta la instancia anterior de una cadena arrastrada para que el
    # tablero muestre solo la tarea vigente (con su contador de intento).
    superseded = {t.carry_over_de for t in tareas if t.carry_over_de}
    columnas: dict[str, list[TareaRead]] = {
        "pendiente": [],
        "en_ruta": [],
        "en_sitio": [],
        "cerrada": [],
    }
    for t in tareas:
        if t.id in superseded:
            continue
        if t.estado in columnas:
            columnas[t.estado].append(TareaRead.model_validate(t))
    return KanbanRead(**columnas)


@router.get("/alertas", response_model=list[AlertaRead])
async def alertas(user: DespachaUser, db: DB):
    """Calcula alertas operativas en vivo (sin persistencia).

    Tres familias:
      - ``tarea_vencida``: tarea abierta con más de 4 h de antigüedad.
      - ``sla_en_riesgo``: tarea de prioridad alta/crítica que lleva > 90 min sin
        llegar a sitio (sigue en ``pendiente`` o ``en_ruta``).
      - ``cuadrilla_sin_movimiento``: cuadrilla con turno abierto sin pin GPS
        reciente (> 30 min) o sin ningún pin registrado.
    """
    ahora = datetime.now(UTC)
    resultado: list[AlertaRead] = []

    tareas = await tarea_service.list_tareas(user, db)
    abiertas = [t for t in tareas if t.estado in _ABIERTAS]

    for t in abiertas:
        edad = _minutos_desde(t.created_at, ahora)
        if edad is not None and edad > _TAREA_VENCIDA_MIN:
            resultado.append(
                AlertaRead(
                    tipo="tarea_vencida",
                    severidad="alta",
                    titulo=f"Tarea vencida: {t.titulo}",
                    detalle=(
                        f"Abierta hace {edad / 60:.1f} h en estado '{t.estado}'."
                    ),
                    cuadrilla_id=t.cuadrilla_id,
                    tarea_id=t.id,
                )
            )
        if (
            t.prioridad in ("alta", "critica")
            and t.estado in ("pendiente", "en_ruta")
            and edad is not None
            and edad > _SLA_RIESGO_MIN
        ):
            resultado.append(
                AlertaRead(
                    tipo="sla_en_riesgo",
                    severidad="alta" if t.prioridad == "critica" else "media",
                    titulo=f"SLA en riesgo: {t.titulo}",
                    detalle=(
                        f"Prioridad {t.prioridad}, {edad:.0f} min sin llegar a "
                        f"sitio (estado '{t.estado}')."
                    ),
                    cuadrilla_id=t.cuadrilla_id,
                    tarea_id=t.id,
                )
            )

    # Cuadrillas en turno sin movimiento GPS reciente.
    turnos = await turno_service.turnos_activos(user.tenant_id, db)
    pines = await ubicacion_service.posiciones_actuales(user.tenant_id, db)
    ultimo_pin = {p.cuadrilla_id: p.timestamp for p in pines}
    for turno in turnos:
        edad_pin = _minutos_desde(ultimo_pin.get(turno.cuadrilla_id), ahora)
        if edad_pin is None:
            resultado.append(
                AlertaRead(
                    tipo="cuadrilla_sin_movimiento",
                    severidad="media",
                    titulo=f"Cuadrilla {turno.cuadrilla_id} sin ubicación",
                    detalle="Turno abierto sin ningún pin GPS registrado.",
                    cuadrilla_id=turno.cuadrilla_id,
                )
            )
        elif edad_pin > _SIN_MOVIMIENTO_MIN:
            resultado.append(
                AlertaRead(
                    tipo="cuadrilla_sin_movimiento",
                    severidad="media",
                    titulo=f"Cuadrilla {turno.cuadrilla_id} sin movimiento",
                    detalle=f"Sin actualización GPS desde hace {edad_pin:.0f} min.",
                    cuadrilla_id=turno.cuadrilla_id,
                )
            )

    return resultado


@router.post("/cuadrillas/{cuadrilla_id}/generar-ruta", response_model=list[TareaRead])
async def generar_ruta(
    cuadrilla_id: str, user: DespachaUser, db: DB, audit: Audit
):
    """Optimiza y persiste el orden de visita de las tareas pendientes de la cuadrilla."""
    ordenadas = await ruteo.generar_ruta_dia(
        cuadrilla_id, db, tenant_id=user.tenant_id
    )
    if ordenadas:
        await audit.log(
            action="update",
            user_id=user.id,
            tenant_id=user.tenant_id,
            entity_type="cuadrilla",
            entity_id=cuadrilla_id,
            extra={"accion": "generar_ruta", "tareas": len(ordenadas)},
        )
    return [TareaRead.model_validate(t) for t in ordenadas]
