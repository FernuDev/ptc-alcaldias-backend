"""Schemas Pydantic del módulo de campo (monitor en vivo de cuadrillas).

Cubren las tareas despachadas, los turnos de jornada, el rastreo GPS, el canal de
mensajería monitor ↔ campo y las vistas agregadas del monitor (posiciones,
kanban y alertas). El tenant SIEMPRE proviene del JWT; estos schemas nunca lo
aceptan como entrada de escritura.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

# ─────────────────────────────────────────────────────────────────────────────
# Tareas
# ─────────────────────────────────────────────────────────────────────────────


class ChecklistItem(BaseModel):
    paso: str = Field(max_length=300)
    hecho: bool = False


class TareaRead(BaseModel):
    id: str
    tenant_id: str
    cuadrilla_id: str | None = None
    integrante_id: str | None = None
    origen_tipo: str
    reporte_id: str | None = None
    obra_id: str | None = None
    proyecto_id: str | None = None
    proyecto_tarea_id: str | None = None
    titulo: str
    descripcion: str | None = None
    prioridad: str
    estado: str
    orden_ruta: int | None = None
    lat: float | None = None
    lng: float | None = None
    colonia_id: str | None = None
    instrucciones: str | None = None
    checklist: list[ChecklistItem] = []
    created_at: datetime
    updated_at: datetime
    fecha_cierre: datetime | None = None
    cierre_nota: str | None = None
    carry_over_de: str | None = None
    intento_n: int = 1

    model_config = {"from_attributes": True}


class TareaCreate(BaseModel):
    """Crea una tarea desde un reporte, una obra o de forma manual.

    El ``origen_tipo`` decide qué campos son obligatorios:
      - ``reporte``: requiere ``reporte_id`` (copia título/geo del reporte).
      - ``obra``:    requiere ``obra_id`` (copia centro/colonia de la obra).
      - ``manual``:  requiere ``titulo``.
    """

    origen_tipo: str = Field(pattern=r"^(reporte|obra|manual)$")
    reporte_id: str | None = Field(None, max_length=20)
    obra_id: str | None = Field(None, max_length=20)
    titulo: str | None = Field(None, max_length=200)
    descripcion: str | None = None
    prioridad: str = Field("media", pattern=r"^(baja|media|alta|critica)$")
    cuadrilla_id: str | None = Field(None, max_length=10)
    integrante_id: str | None = Field(None, max_length=40)
    lat: float | None = None
    lng: float | None = None
    colonia_id: str | None = Field(None, max_length=60)
    instrucciones: str | None = None
    checklist: list[ChecklistItem] | None = None


class AsignarInput(BaseModel):
    cuadrilla_id: str = Field(max_length=10)
    integrante_id: str | None = Field(None, max_length=40)


class EstadoInput(BaseModel):
    estado: str = Field(pattern=r"^(pendiente|en_ruta|en_sitio|cerrada)$")


class ChecklistInput(BaseModel):
    checklist: list[ChecklistItem]


# ─────────────────────────────────────────────────────────────────────────────
# Turnos
# ─────────────────────────────────────────────────────────────────────────────


class TurnoRead(BaseModel):
    id: str
    tenant_id: str
    cuadrilla_id: str
    inicio: datetime
    fin: datetime | None = None
    estado: str

    model_config = {"from_attributes": True}


class TurnoAbrirInput(BaseModel):
    cuadrilla_id: str = Field(max_length=10)


# ─────────────────────────────────────────────────────────────────────────────
# Ubicación (rastreo GPS)
# ─────────────────────────────────────────────────────────────────────────────


class UbicacionRead(BaseModel):
    id: str
    tenant_id: str
    cuadrilla_id: str
    integrante_id: str | None = None
    lat: float
    lng: float
    timestamp: datetime

    model_config = {"from_attributes": True}


class UbicacionCreate(BaseModel):
    cuadrilla_id: str = Field(max_length=10)
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    integrante_id: str | None = Field(None, max_length=40)


# ─────────────────────────────────────────────────────────────────────────────
# Mensajería monitor ↔ campo
# ─────────────────────────────────────────────────────────────────────────────


class MensajeRead(BaseModel):
    id: str
    tenant_id: str
    cuadrilla_id: str
    tarea_id: str | None = None
    autor_tipo: str
    autor_id: str | None = None
    tipo: str
    texto: str | None = None
    nota_voz_url: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class MensajeCreate(BaseModel):
    cuadrilla_id: str = Field(max_length=10)
    autor_tipo: str = Field("monitor", pattern=r"^(monitor|campo)$")
    tipo: str = Field("texto", pattern=r"^(texto|voz)$")
    texto: str | None = None
    nota_voz_url: str | None = Field(None, max_length=500)
    tarea_id: str | None = Field(None, max_length=40)


# ─────────────────────────────────────────────────────────────────────────────
# Vistas del monitor (posiciones, kanban, alertas)
# ─────────────────────────────────────────────────────────────────────────────


class PosicionRead(BaseModel):
    """Última posición conocida de una cuadrilla (pin del mapa en vivo)."""

    cuadrilla_id: str
    integrante_id: str | None = None
    lat: float
    lng: float
    timestamp: datetime

    model_config = {"from_attributes": True}


class KanbanRead(BaseModel):
    """Tareas agrupadas por estado para el tablero kanban del monitor."""

    pendiente: list[TareaRead] = []
    en_ruta: list[TareaRead] = []
    en_sitio: list[TareaRead] = []
    cerrada: list[TareaRead] = []


class AlertaRead(BaseModel):
    """Alerta operativa del monitor (cálculo en vivo, sin persistencia)."""

    tipo: str  # tarea_vencida | cuadrilla_sin_movimiento | sla_en_riesgo
    severidad: str  # alta | media
    titulo: str
    detalle: str
    cuadrilla_id: str | None = None
    tarea_id: str | None = None
