"""Schemas (request/response) del Agente Cívico."""

from typing import Literal

from pydantic import BaseModel, Field


# ─── Contexto del ciudadano ───────────────────────────────────────────────


class CiudadanoContexto(BaseModel):
    autenticado: bool = False
    usuario_id: str | None = None
    primera_visita: bool = False


# ─── Chat ─────────────────────────────────────────────────────────────────


class CivicoChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class CivicoChatRequest(BaseModel):
    mensaje: str = Field(min_length=1, max_length=4000)
    historial: list[CivicoChatMessage] = []
    contexto: CiudadanoContexto = CiudadanoContexto()


class CivicoFuente(BaseModel):
    """Referencia a documento oficial citado en la respuesta."""

    documento: str
    seccion: str | None = None


class CivicoChatResponse(BaseModel):
    respuesta: str
    fuentes: list[CivicoFuente] = []
    es_crisis: bool = False
    sin_informacion: bool = False


# ─── Clasificación ────────────────────────────────────────────────────────


class CivicoClassifyRequest(BaseModel):
    descripcion: str = Field(min_length=1, max_length=4000)


class CivicoClassifyResponse(BaseModel):
    categoria_sugerida: str
    prioridad_sugerida: Literal["baja", "media", "alta", "critica"]
    es_emergencia: bool = False
    justificacion: str
    requiere_confirmacion: bool = True


# ─── Pre-llenado de reportes ──────────────────────────────────────────────


class PrefillReporteRequest(BaseModel):
    """Datos extraídos de la conversación para pre-llenar un reporte."""

    descripcion: str = Field(min_length=1, max_length=4000)
    categoria_id: str | None = None
    colonia_id: str | None = None
    lng: float | None = None
    lat: float | None = None


class PrefillReporteResponse(BaseModel):
    """Borrador de reporte SIN enviar. Requiere confirmación del usuario."""

    descripcion: str
    categoria_id: str | None = None
    colonia_id: str | None = None
    lng: float | None = None
    lat: float | None = None
    requiere_confirmacion: bool = True


# ─── Health ───────────────────────────────────────────────────────────────


class CivicoHealth(BaseModel):
    status: Literal["ok", "degraded"]
    llm_provider: str
    llm_configurado: bool
    vector_store_ok: bool
