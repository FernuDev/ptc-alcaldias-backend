"""Schemas (request/response) del Agente Institucional."""

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.agente.context import NivelVisibilidad

# ─── Chat ────────────────────────────────────────────────────────────────


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)


class ChatRequest(BaseModel):
    mensaje: str = Field(min_length=1, max_length=8000)
    historial: list[ChatMessage] = []


class Fuente(BaseModel):
    """Cita de un fragmento recuperado de la base de conocimiento."""

    documento_id: str
    titulo: str
    seccion: str | None = None
    nivel: NivelVisibilidad
    score: float | None = None


class Navegacion(BaseModel):
    """Enlace a una pantalla del sistema que el agente sugiere abrir."""

    href: str
    titulo: str


class AccionPendiente(BaseModel):
    """Acción preparada por el agente, pendiente de confirmación humana."""

    accion_id: str
    descripcion: str
    payload: dict
    requiere_confirmacion: bool = True


class ChatResponse(BaseModel):
    respuesta: str
    fuentes: list[Fuente] = []
    sin_informacion: bool = False
    navegacion: list[Navegacion] = []
    acciones: list[dict] = []


# ─── Clasificación de reportes ─────────────────────────────────────────────


class ClassifyRequest(BaseModel):
    descripcion: str = Field(min_length=1, max_length=8000)


class ClassifyResponse(BaseModel):
    categoria_sugerida: str
    prioridad_sugerida: Literal["baja", "media", "alta", "critica"]
    es_sensible: bool = False
    es_emergencia: bool = False
    canal_recomendado: str | None = None
    justificacion: str
    requiere_confirmacion: bool = True


# ─── Acciones (human-in-the-loop) ──────────────────────────────────────────

TipoAccion = Literal["turnar", "asignar", "cerrar", "cambiar_estado", "borrador"]


class PrepareActionRequest(BaseModel):
    tipo: TipoAccion
    entity_type: Literal["reporte", "obra"]
    entity_id: str
    params: dict = {}


class PreparedAction(BaseModel):
    accion_id: str
    tipo: TipoAccion
    entity_type: str
    entity_id: str
    descripcion: str
    payload: dict
    requiere_confirmacion: bool = True


class ConfirmActionRequest(BaseModel):
    accion_id: str


class ConfirmActionResponse(BaseModel):
    accion_id: str
    estado: Literal["confirmada", "expirada", "no_encontrada", "error"]
    detalle: str


# ─── Ingesta de conocimiento ───────────────────────────────────────────────


class IngestDocRequest(BaseModel):
    titulo: str = Field(min_length=1, max_length=300)
    contenido: str = Field(min_length=1)
    nivel_visibilidad: NivelVisibilidad = "interno"
    # tenant_id == "global" hace el documento visible a todas las alcaldías.
    tenant_id: str = "global"
    area_id: str | None = None
    fuente: str | None = None


class IngestResponse(BaseModel):
    documento_id: str
    fragmentos: int


# ─── Analítica ─────────────────────────────────────────────────────────────


class AnalyticsRequest(BaseModel):
    # Se puede pasar un intent explícito o una consulta en lenguaje natural.
    intent: str | None = None
    consulta: str | None = None
    params: dict = {}


class AnalyticsResponse(BaseModel):
    intent: str | None
    datos: Any | None = None
    resumen: str | None = None
    disponibles: dict[str, str] = {}


# ─── Conversaciones (historial de chats) ──────────────────────────────────


class ConversacionResumen(BaseModel):
    id: str
    titulo: str
    created_at: Any
    updated_at: Any


class ConversacionDetalle(ConversacionResumen):
    mensajes: list[dict]


class ConversacionSaveRequest(BaseModel):
    conversacion_id: str | None = None
    titulo: str | None = None
    mensajes: list[dict]


# ─── Health ────────────────────────────────────────────────────────────────


class AgenteHealth(BaseModel):
    status: Literal["ok", "degraded"]
    llm_provider: str
    llm_configurado: bool
    vector_store_ok: bool
    documentos_indexados: int | None = None
