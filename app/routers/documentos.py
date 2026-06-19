"""Router de documentos versionados (REQ-04).

- ``GET  /documentos``              lista documentos vigentes del tenant (filtrable).
- ``GET  /documentos/{id}/historial`` cadena completa de versiones de un documento.
- ``POST /documentos``              sube un documento o una nueva versión (multipart).

Un "documento" es una fila ``Archivo`` con ``categoria='documento'`` (ver
:mod:`app.services.documento_service`). La descarga/servido del binario se delega
al router de uploads existente: cada documento expone su ``url``
(``/uploads/<key>``) y ``storage_key`` para usar ``GET /uploads/file/{key}``.

Todas las rutas están protegidas por ``CurrentUser``; el tenant se deriva del
JWT. La subida/versionado exige permiso de gestión (validado en el servicio). La
integración registra este router en ``main.py`` con::

    from app.routers import documentos
    app.include_router(documentos.router, prefix=PREFIX)
"""

from fastapi import APIRouter, File, Form, UploadFile

from app.core.dependencies import DB, Audit, CurrentUser
from app.schemas.documento import DocumentoHistorial, DocumentoRead
from app.services import documento_service

router = APIRouter(prefix="/documentos", tags=["documentos"])


@router.get("", response_model=list[DocumentoRead])
async def list_documentos(
    user: CurrentUser,
    db: DB,
    entity_type: str | None = None,
    entity_id: str | None = None,
    solo_actuales: bool = True,
):
    """Lista documentos del tenant (por defecto solo versiones vigentes).

    Filtros opcionales por entidad asociada (``entity_type`` / ``entity_id``).
    Con ``solo_actuales=false`` devuelve todas las versiones.
    """
    documentos = await documento_service.listar_documentos(
        user.tenant_id,
        db,
        entity_type=entity_type,
        entity_id=entity_id,
        solo_actuales=solo_actuales,
    )
    return [DocumentoRead.model_validate(d) for d in documentos]


@router.get("/{documento_id}/historial", response_model=DocumentoHistorial)
async def documento_historial(documento_id: str, user: CurrentUser, db: DB):
    """Devuelve la cadena de versiones de un documento (más reciente primero)."""
    versiones = await documento_service.historial(user.tenant_id, db, documento_id)
    return DocumentoHistorial(
        documento_id=documento_id,
        total_versiones=len(versiones),
        versiones=[DocumentoRead.model_validate(v) for v in versiones],
    )


@router.post("", response_model=DocumentoRead, status_code=201)
async def upload_documento(
    user: CurrentUser,
    db: DB,
    audit: Audit,
    file: UploadFile = File(...),
    nombre: str | None = Form(None),
    entity_type: str | None = Form(None),
    entity_id: str | None = Form(None),
    reemplaza_a: str | None = Form(None),
):
    """Sube un documento nuevo o una nueva versión (si ``reemplaza_a`` viene dado).

    Requiere permiso de gestión de documentos (validado en el servicio). El
    tenant se deriva del JWT.
    """
    documento = await documento_service.subir_version(
        db,
        user,
        file,
        nombre=nombre,
        entity_type=entity_type,
        entity_id=entity_id,
        reemplaza_a=reemplaza_a,
        audit=audit,
    )
    return DocumentoRead.model_validate(documento)
