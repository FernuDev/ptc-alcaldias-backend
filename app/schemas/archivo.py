from datetime import datetime

from pydantic import BaseModel, Field


class ArchivoRead(BaseModel):
    """Representación pública de una fila ``Archivo``."""

    id: str
    tenant_id: str
    nombre: str
    content_type: str
    size_bytes: int
    storage_key: str
    url: str
    categoria: str
    entity_type: str | None = None
    entity_id: str | None = None
    lat: float | None = None
    lng: float | None = None
    created_at: datetime
    created_by: str | None = None

    model_config = {"from_attributes": True}


# Las subidas llegan como ``multipart/form-data`` (archivo binario + campos de
# formulario), por lo que el router declara los campos con ``Form(...)`` en lugar
# de un body JSON. Estos modelos documentan/validan los valores admitidos y se
# reutilizan para tipar los parámetros del servicio.


class ArchivoUploadForm(BaseModel):
    """Campos de formulario aceptados en ``POST /uploads``."""

    categoria: str = Field(
        default="otro",
        pattern=r"^(evidencia|documento|otro)$",
        description="Clasificación funcional del archivo.",
    )
    entity_type: str | None = Field(
        default=None,
        max_length=20,
        description="Tipo de entidad asociada (p. ej. 'reporte', 'obra').",
    )
    entity_id: str | None = Field(
        default=None,
        max_length=40,
        description="Id de la entidad asociada.",
    )
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)


class EvidenciaUploadForm(BaseModel):
    """Campos de formulario para ``POST /uploads/evidencia/{reporte_id}``."""

    caption: str | None = Field(default=None, max_length=200)
    tipo: str | None = Field(
        default=None,
        pattern=r"^(ciudadano|cuadrilla|inspeccion)$",
    )
    momento: str | None = Field(default=None, pattern=r"^(antes|despues)$")
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
