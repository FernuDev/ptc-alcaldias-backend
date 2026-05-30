from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class EvidenciaRead(BaseModel):
    id: str
    url: str
    caption: str | None = None
    fecha: datetime | None = None
    autor: str | None = None
    tipo: str | None = None

    model_config = {"from_attributes": True}


class EvidenciaCreate(BaseModel):
    url: str = Field(max_length=500)
    caption: str | None = Field(None, max_length=200)
    tipo: str | None = Field(None, pattern=r"^(ciudadano|cuadrilla|inspeccion)$")


class EventoRead(BaseModel):
    id: str
    fecha: datetime
    tipo: str
    titulo: str
    descripcion: str | None = None
    autor_nombre: str | None = None
    autor_iniciales: str | None = None
    autor_rol: str | None = None

    model_config = {"from_attributes": True}


class EventoCreate(BaseModel):
    tipo: str = Field(max_length=20)
    titulo: str = Field(max_length=200)
    descripcion: str | None = None
    autor_nombre: str | None = Field(None, max_length=100)
    autor_iniciales: str | None = Field(None, max_length=5)
    autor_rol: str | None = Field(None, max_length=100)


class ReporteRead(BaseModel):
    id: str
    tenant_id: str
    folio: str
    categoria_id: str
    estado: str
    prioridad: str
    fuente: str
    cuadrilla_id: str | None = None
    colonia_id: str
    colonia_nombre: str | None = None
    lng: float
    lat: float
    peso: int | None = None
    titulo: str
    descripcion: str | None = None
    ciudadano_nombre: str | None = None
    ciudadano_iniciales: str | None = None
    fecha_creacion: datetime
    fecha_actualizacion: datetime
    fecha_cierre: datetime | None = None
    tiempo_atencion_horas: Decimal | None = None
    costo_estimado: Decimal | None = None
    gasto_real: Decimal | None = None
    evidencias: list[EvidenciaRead] = []
    eventos: list[EventoRead] = []
    obras_relacionadas_ids: list[str] = []

    model_config = {"from_attributes": True}


class ReporteCreate(BaseModel):
    categoria_id: str = Field(max_length=30)
    prioridad: str = Field(pattern=r"^(baja|media|alta|critica)$")
    fuente: str = Field(pattern=r"^(app|web|llamada|presencial)$")
    colonia_id: str = Field(max_length=60)
    lng: float
    lat: float
    titulo: str = Field(max_length=200)
    descripcion: str | None = None
    ciudadano_nombre: str | None = Field(None, max_length=100)
    ciudadano_iniciales: str | None = Field(None, max_length=5)


class ReporteUpdate(BaseModel):
    estado: str | None = Field(None, pattern=r"^(nuevo|asignado|en_proceso|resuelto|cerrado)$")
    prioridad: str | None = Field(None, pattern=r"^(baja|media|alta|critica)$")
    cuadrilla_id: str | None = Field(None, max_length=10)
    costo_estimado: Decimal | None = None
    gasto_real: Decimal | None = None
