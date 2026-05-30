from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class PresupuestoItemRead(BaseModel):
    id: int
    concepto: str
    unidad: str | None = None
    cantidad: Decimal | None = None
    precio_unitario: Decimal | None = None
    importe: Decimal | None = None

    model_config = {"from_attributes": True}


class EquipoRead(BaseModel):
    id: str
    nombre: str | None = None
    iniciales: str | None = None
    rol: str | None = None
    contacto: str | None = None

    model_config = {"from_attributes": True}


class CalleAfectadaRead(BaseModel):
    id: str
    nombre: str | None = None
    estado: str | None = None
    coordenadas: Any | None = None
    fecha_inicio: datetime | None = None
    fecha_fin_estimada: datetime | None = None
    alternativas_viales: Any | None = None

    model_config = {"from_attributes": True}


class TimelineRead(BaseModel):
    id: str
    fecha: datetime
    tipo: str
    titulo: str
    descripcion: str | None = None
    autor_nombre: str | None = None
    autor_iniciales: str | None = None
    autor_rol: str | None = None

    model_config = {"from_attributes": True}


class DocumentoRead(BaseModel):
    id: str
    nombre: str
    tipo: str | None = None
    tamano_kb: int | None = None
    fecha_subida: datetime | None = None
    autor: str | None = None

    model_config = {"from_attributes": True}


class ObraEvidenciaRead(BaseModel):
    id: str
    url: str | None = None
    caption: str | None = None
    fecha: datetime | None = None
    autor: str | None = None
    tipo: str | None = None

    model_config = {"from_attributes": True}


class ObraRead(BaseModel):
    id: str
    tenant_id: str
    folio: str
    nombre: str
    descripcion: str | None = None
    categoria_id: str
    estado: str
    prioridad: str
    colonia_id: str
    colonia_nombre: str | None = None
    center_lng: float | None = None
    center_lat: float | None = None
    responsable_nombre: str | None = None
    responsable_iniciales: str | None = None
    responsable_cargo: str | None = None
    contratista_id: str | None = None
    fecha_inicio: datetime
    fecha_fin_estimada: datetime
    fecha_fin_real: datetime | None = None
    avance_pct: int
    presupuesto_autorizado: Decimal | None = None
    presupuesto_ejercido: Decimal | None = None
    presupuesto_items: list[PresupuestoItemRead] = []
    equipo: list[EquipoRead] = []
    calles_afectadas: list[CalleAfectadaRead] = []
    timeline: list[TimelineRead] = []
    documentos: list[DocumentoRead] = []
    evidencias: list[ObraEvidenciaRead] = []

    model_config = {"from_attributes": True}


class ObraCreate(BaseModel):
    nombre: str = Field(max_length=300)
    descripcion: str | None = None
    categoria_id: str = Field(max_length=30)
    prioridad: str = Field(pattern=r"^(baja|media|alta|estrategica)$")
    colonia_id: str = Field(max_length=60)
    center_lng: float | None = None
    center_lat: float | None = None
    contratista_id: str | None = Field(None, max_length=10)
    fecha_inicio: datetime
    fecha_fin_estimada: datetime
    presupuesto_autorizado: Decimal | None = None


class ObraUpdate(BaseModel):
    estado: str | None = Field(
        None,
        pattern=r"^(planeacion|licitacion|en_ejecucion|suspendida|en_cierre|concluida)$",
    )
    prioridad: str | None = Field(None, pattern=r"^(baja|media|alta|estrategica)$")
    avance_pct: int | None = Field(None, ge=0, le=100)
    presupuesto_ejercido: Decimal | None = None
    contratista_id: str | None = Field(None, max_length=10)
    fecha_fin_real: datetime | None = None


class EquipoCreate(BaseModel):
    nombre: str = Field(max_length=120)
    iniciales: str = Field(max_length=5)
    rol: str = Field(max_length=60)
    contacto: str | None = Field(None, max_length=120)


class CalleAfectadaCreate(BaseModel):
    nombre: str = Field(max_length=200)
    estado: str = Field(pattern=r"^(cerrada_total|cerrada_parcial|desvio)$")
    coordenadas: Any | None = None
    alternativas_viales: list[str] | None = None


class TimelineCreate(BaseModel):
    tipo: str = Field(max_length=20)
    titulo: str = Field(max_length=200)
    descripcion: str | None = None
    autor_nombre: str | None = Field(None, max_length=120)
    autor_iniciales: str | None = Field(None, max_length=5)
    autor_rol: str | None = Field(None, max_length=100)


class DocumentoCreate(BaseModel):
    nombre: str = Field(max_length=200)
    tipo: str | None = Field(None, max_length=30)
    tamano_kb: int | None = None
    autor: str | None = Field(None, max_length=120)


class ObraEvidenciaCreate(BaseModel):
    url: str = Field(max_length=500)
    caption: str | None = Field(None, max_length=200)
    tipo: str | None = Field(None, pattern=r"^(antes|durante|despues)$")
