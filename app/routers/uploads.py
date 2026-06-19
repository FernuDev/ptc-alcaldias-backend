"""Router de subida y servido de archivos.

- ``POST /uploads``                         sube un archivo genérico (multipart).
- ``POST /uploads/evidencia/{reporte_id}``  sube imagen + crea evidencia geoetiquetada.
- ``GET  /uploads/file/{key}``              sirve el archivo local (demo).

Todas las rutas de escritura están protegidas por ``CurrentUser``; el tenant se
deriva del JWT. La integración registra este router en ``main.py`` (no se toca
aquí) con::

    from app.routers import uploads
    app.include_router(uploads.router, prefix=PREFIX)
"""

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse

from app.core.dependencies import DB, Audit, CurrentUser
from app.core.exceptions import NotFoundError
from app.core.storage import get_storage
from app.schemas.archivo import ArchivoRead
from app.schemas.reporte import EvidenciaRead
from app.services import archivo_service

router = APIRouter(prefix="/uploads", tags=["uploads"])


@router.post("", response_model=ArchivoRead, status_code=201)
async def upload_archivo(
    user: CurrentUser,
    db: DB,
    audit: Audit,
    file: UploadFile = File(...),
    categoria: str = Form("otro"),
    entity_type: str | None = Form(None),
    entity_id: str | None = Form(None),
    lat: float | None = Form(None),
    lng: float | None = Form(None),
):
    """Sube un archivo (imagen o PDF, máx 10 MB) y registra su fila ``Archivo``."""
    archivo = await archivo_service.subir_archivo(
        db,
        user,
        file,
        categoria=categoria,
        entity_type=entity_type,
        entity_id=entity_id,
        lat=lat,
        lng=lng,
        audit=audit,
    )
    return ArchivoRead.model_validate(archivo)


@router.post(
    "/evidencia/{reporte_id}",
    response_model=EvidenciaRead,
    status_code=201,
)
async def upload_evidencia(
    reporte_id: str,
    user: CurrentUser,
    db: DB,
    audit: Audit,
    file: UploadFile = File(...),
    caption: str | None = Form(None),
    tipo: str | None = Form(None),
    momento: str | None = Form(None),
    lat: float | None = Form(None),
    lng: float | None = Form(None),
):
    """Sube una imagen y crea una ``ReporteEvidencia`` geoetiquetada en el reporte."""
    _, evidencia = await archivo_service.subir_evidencia_reporte(
        db,
        user,
        reporte_id,
        file,
        caption=caption,
        tipo=tipo,
        momento=momento,
        lat=lat,
        lng=lng,
        audit=audit,
    )
    return EvidenciaRead.model_validate(evidencia)


@router.get("/file/{key:path}")
async def serve_archivo(key: str, user: CurrentUser, db: DB):
    """Sirve un archivo local por su ``storage_key`` (demo).

    Solo entrega archivos del tenant del usuario: la fila ``Archivo`` debe existir
    bajo ``user.tenant_id`` y el objeto debe residir en disco. Devuelve 404 si
    cualquiera de las dos condiciones falla, evitando fuga entre tenants.
    """
    archivo = await archivo_service.get_archivo_by_key(db, user.tenant_id, key)
    if archivo is None:
        raise NotFoundError("Archivo", key)

    path = get_storage().get_path(key)
    if path is None:
        raise NotFoundError("Archivo", key)

    return FileResponse(
        path,
        media_type=archivo.content_type,
        filename=archivo.nombre,
    )
