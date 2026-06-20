"""Schemas de Plan.IA: portafolio de proyectos, tareas, expediente de zona."""

from datetime import datetime

from pydantic import BaseModel, Field


class TicketEspejoRead(BaseModel):
    """Ticket de cuadrilla (tarea de campo) espejo de una tarea de proyecto."""

    id: str
    estado: str  # pendiente | en_ruta | en_sitio | cerrada
    cuadrilla_id: str | None = None
    cierre_nota: str | None = None
    fecha_cierre: datetime | None = None

    model_config = {"from_attributes": True}


class ProyectoTareaRead(BaseModel):
    id: str
    nombre: str
    estado: str
    avance_pct: int
    fecha_inicio: datetime | None = None
    fecha_fin: datetime | None = None
    depende_de: str | None = None
    responsable: str | None = None
    orden: int
    # Ticket de cuadrilla generado desde esta tarea (puente REQ-07), si existe.
    ticket: TicketEspejoRead | None = None

    model_config = {"from_attributes": True}


class GenerarTicketInput(BaseModel):
    cuadrilla_id: str | None = Field(None, max_length=10)


class ProyectoListItem(BaseModel):
    id: str
    nombre: str
    tipo: str
    estado: str
    prioridad: str
    avance_pct: int
    area_id: str | None = None
    responsable_nombre: str | None = None
    presupuesto_estimado: float | None = None
    fecha_inicio: datetime | None = None
    fecha_fin_estimada: datetime | None = None

    model_config = {"from_attributes": True}


class ProyectoRead(ProyectoListItem):
    descripcion: str | None = None
    compromiso_id: str | None = None
    pdm_eje: str | None = None
    origen_zona: str | None = None
    num_reportes_vinculados: int = 0
    tareas: list[ProyectoTareaRead] = []


class ProyectoCreate(BaseModel):
    nombre: str = Field(min_length=3, max_length=200)
    tipo: str = Field("obra", pattern=r"^(obra|programa|evento|iniciativa)$")
    descripcion: str | None = None
    prioridad: str = Field("media", pattern=r"^(baja|media|alta|critica)$")
    responsable_nombre: str | None = None
    area_id: str | None = None
    compromiso_id: str | None = None
    pdm_eje: str | None = None
    presupuesto_estimado: float | None = None
    fecha_inicio: datetime | None = None
    fecha_fin_estimada: datetime | None = None


class ProyectoUpdate(BaseModel):
    nombre: str | None = None
    estado: str | None = Field(
        None, pattern=r"^(planeacion|en_ejecucion|en_pausa|concluido|cancelado)$"
    )
    prioridad: str | None = None
    avance_pct: int | None = Field(None, ge=0, le=100)
    descripcion: str | None = None
    responsable_nombre: str | None = None
    pdm_eje: str | None = None
    presupuesto_estimado: float | None = None
    fecha_inicio: datetime | None = None
    fecha_fin_estimada: datetime | None = None


class TareaCreate(BaseModel):
    nombre: str = Field(min_length=2, max_length=200)
    fecha_inicio: datetime | None = None
    fecha_fin: datetime | None = None
    depende_de: str | None = None
    responsable: str | None = None
    orden: int = 0


class TareaUpdate(BaseModel):
    nombre: str | None = None
    estado: str | None = Field(None, pattern=r"^(pendiente|en_progreso|completada)$")
    avance_pct: int | None = Field(None, ge=0, le=100)
    fecha_inicio: datetime | None = None
    fecha_fin: datetime | None = None
    depende_de: str | None = None
    responsable: str | None = None
    orden: int | None = None


class PortafolioBucket(BaseModel):
    clave: str
    total: int
    avance_promedio: float


class PortafolioResumen(BaseModel):
    total: int
    avance_global: float
    inversion_estimada: float
    por_tipo: list[PortafolioBucket]
    por_estado: list[PortafolioBucket]
    alineados_a_compromiso: int


class ExpedienteZona(BaseModel):
    zona_id: str
    categoria_id: str
    categoria_label: str | None = None
    colonia_id: str
    colonia_nombre: str | None = None
    total_reportes: int
    severidad: str
    lat: float | None = None
    lng: float | None = None
    diagnostico: str
    recomendacion: str
    costo_estimado: float
    direccion_lider: str | None = None
    # Coordenadas [lng, lat] de los reportes del cluster (para el mapa MapLibre).
    puntos: list[list[float]] = []
    # IDs de los reportes del cluster (para vincularlos al proyecto al convertir).
    reporte_ids: list[str] = []
    ya_es_proyecto: bool = False


class ConvertirZonaInput(BaseModel):
    categoria_id: str
    colonia_id: str
    colonia_nombre: str | None = None
    recomendacion: str
    costo_estimado: float
    total_reportes: int = 0
    reporte_ids: list[str] = []


class ConectorInterop(BaseModel):
    id: str
    nombre: str
    descripcion: str
    estado: str  # disponible | on-demand
    categoria: str


# ── Capa de Coordinación ────────────────────────────────────────────────────


class StakeholderRead(BaseModel):
    id: str
    nombre: str
    organizacion: str | None = None
    rol: str
    postura: str
    contacto: str | None = None
    notas: str | None = None

    model_config = {"from_attributes": True}


class StakeholderCreate(BaseModel):
    nombre: str = Field(min_length=2, max_length=160)
    organizacion: str | None = None
    rol: str = Field("interesado", pattern=r"^(interesado|responsable|aliado|afectado)$")
    postura: str = Field("neutral", pattern=r"^(a_favor|neutral|en_contra)$")
    contacto: str | None = None
    notas: str | None = None


class RiesgoRead(BaseModel):
    id: str
    descripcion: str
    probabilidad: str
    impacto: str
    mitigacion: str | None = None
    estado: str

    model_config = {"from_attributes": True}


class RiesgoCreate(BaseModel):
    descripcion: str = Field(min_length=3)
    probabilidad: str = Field("media", pattern=r"^(baja|media|alta)$")
    impacto: str = Field("medio", pattern=r"^(bajo|medio|alto)$")
    mitigacion: str | None = None


class RiesgoUpdate(BaseModel):
    descripcion: str | None = None
    probabilidad: str | None = Field(None, pattern=r"^(baja|media|alta)$")
    impacto: str | None = Field(None, pattern=r"^(bajo|medio|alto)$")
    mitigacion: str | None = None
    estado: str | None = Field(
        None, pattern=r"^(abierto|mitigado|materializado|cerrado)$"
    )


class AprobacionRead(BaseModel):
    id: str
    etapa: str
    responsable: str | None = None
    estado: str
    comentario: str | None = None
    orden: int
    fecha_resolucion: datetime | None = None

    model_config = {"from_attributes": True}


class AprobacionCreate(BaseModel):
    etapa: str = Field(min_length=2, max_length=120)
    responsable: str | None = None
    orden: int = 0


class AprobacionResolve(BaseModel):
    estado: str = Field(pattern=r"^(aprobado|rechazado)$")
    comentario: str | None = None
