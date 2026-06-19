"""Esquemas de la API de documentos versionados (REQ-04).

Un "documento" es una fila ``Archivo`` con ``categoria='documento'``. El
versionado se modela sobre las columnas de ``Archivo`` (``version``,
``reemplaza_a``, ``es_actual``): cada nueva versión es un ``Archivo`` nuevo que
apunta al anterior vía ``reemplaza_a`` y desactiva su ``es_actual``.

Las subidas llegan como ``multipart/form-data`` (binario + campos de
formulario), por lo que el router declara los campos con ``Form(...)``. El
modelo ``DocumentoUploadForm`` documenta/valida los valores admitidos.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class DocumentoRead(BaseModel):
    """Representación pública de un documento (fila ``Archivo`` versionada)."""

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
    version: int
    reemplaza_a: str | None = None
    es_actual: bool
    created_at: datetime
    created_by: str | None = None

    model_config = {"from_attributes": True}


class DocumentoHistorial(BaseModel):
    """Cadena de versiones de un documento, de la más reciente a la más antigua."""

    documento_id: str
    total_versiones: int
    versiones: list[DocumentoRead]


class DocumentoUploadForm(BaseModel):
    """Campos de formulario aceptados en ``POST /documentos``.

    Si ``reemplaza_a`` viene informado, la subida crea una NUEVA versión del
    documento indicado (incrementa ``version``, marca el anterior como no
    actual). En caso contrario crea un documento nuevo en su ``version`` 1.
    """

    nombre: str | None = Field(
        default=None,
        max_length=255,
        description="Nombre legible del documento. Si se omite, usa el nombre del archivo.",
    )
    entity_type: str | None = Field(
        default=None,
        max_length=20,
        description="Tipo de entidad asociada (p. ej. 'obra', 'reporte').",
    )
    entity_id: str | None = Field(
        default=None,
        max_length=40,
        description="Id de la entidad asociada.",
    )
    reemplaza_a: str | None = Field(
        default=None,
        max_length=40,
        description="Id del documento (Archivo) que esta subida reemplaza/versiona.",
    )
