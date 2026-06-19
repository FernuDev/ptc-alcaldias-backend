"""Schemas (request/response) del Agente Ejecutivo (asistente del Alcalde).

A diferencia del Agente Institucional (acotado por dirección/área), el Ejecutivo
opera con visión CROSS-DIRECCIONES: lee desempeño global, cumplimiento de
compromisos y sentimiento ciudadano de todo el tenant.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

EstadoCompromiso = Literal["en_progreso", "cumplido", "en_riesgo", "retrasado"]


# ─── Chat ──────────────────────────────────────────────────────────────────


class EjecutivoChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)


class EjecutivoChatRequest(BaseModel):
    mensaje: str = Field(min_length=1, max_length=8000)
    historial: list[EjecutivoChatMessage] = []


class EjecutivoChatResponse(BaseModel):
    respuesta: str
    # Datos estructurados que respaldan la respuesta (KPIs, compromisos,
    # sentimiento) para que el frontend pueda renderizar tarjetas/visuales.
    datos: dict[str, Any] = {}
    sin_informacion: bool = False


# ─── Compromisos ─────────────────────────────────────────────────────────────


class CompromisoBase(BaseModel):
    titulo: str = Field(min_length=1, max_length=200)
    descripcion: str | None = None
    area_id: str | None = Field(default=None, max_length=30)
    meta: str | None = Field(default=None, max_length=300)
    avance_pct: int = Field(default=0, ge=0, le=100)
    estado: EstadoCompromiso = "en_progreso"
    fecha_objetivo: datetime | None = None


class CompromisoCreate(CompromisoBase):
    pass


class CompromisoUpdate(BaseModel):
    titulo: str | None = Field(default=None, min_length=1, max_length=200)
    descripcion: str | None = None
    area_id: str | None = Field(default=None, max_length=30)
    meta: str | None = Field(default=None, max_length=300)
    avance_pct: int | None = Field(default=None, ge=0, le=100)
    estado: EstadoCompromiso | None = None
    fecha_objetivo: datetime | None = None


class CompromisoOut(CompromisoBase):
    id: str
    area_label: str | None = None
    # Días restantes hasta la fecha objetivo (negativo si está vencido).
    dias_restantes: int | None = None
    en_riesgo: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


class CompromisosResumen(BaseModel):
    """Vista agregada del cumplimiento de compromisos."""

    total: int = 0
    cumplidos: int = 0
    en_progreso: int = 0
    en_riesgo: int = 0
    retrasados: int = 0
    avance_promedio: float = 0.0
    pct_cumplimiento: float = 0.0
    items: list[CompromisoOut] = []


# ─── Sentimiento ciudadano ───────────────────────────────────────────────────


class SentimientoArea(BaseModel):
    area_id: str
    label: str
    positivo: int = 0
    neutral: int = 0
    negativo: int = 0
    indice: float = 0.0  # -1.0 .. 1.0


class SentimientoResponse(BaseModel):
    indice_global: float = 0.0  # -1.0 (muy negativo) .. 1.0 (muy positivo)
    etiqueta: Literal["positivo", "neutral", "negativo"] = "neutral"
    positivo: int = 0
    neutral: int = 0
    negativo: int = 0
    muestra: int = 0
    por_area: list[SentimientoArea] = []
    resumen: str | None = None


# ─── Resumen ejecutivo (síntesis cross-direcciones) ──────────────────────────


class DesempenoArea(BaseModel):
    area_id: str
    label: str
    activos: int = 0
    resueltos: int = 0
    en_riesgo_sla: int = 0
    pct_resueltos: float = 0.0
    tiempo_promedio_dias: float = 0.0


class ResumenEjecutivo(BaseModel):
    sintesis: str
    kpis_globales: dict[str, Any] = {}
    desempeno_por_area: list[DesempenoArea] = []
    compromisos: CompromisosResumen | None = None
    sentimiento: SentimientoResponse | None = None
    generado_en: datetime
