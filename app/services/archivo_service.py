"""Servicio de subida y registro de archivos.

Valida tipo/tamaño, persiste los bytes vía el backend de storage activo
(:mod:`app.core.storage`), crea la fila ``Archivo`` (índice consultable y
auditable por tenant) y, opcionalmente, una ``ReporteEvidencia`` geoetiquetada
ligada a un reporte.

El tenant SIEMPRE se deriva de ``user.tenant_id`` (nunca del body), conforme a
la regla multi-tenant del proyecto.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditLogger
from app.core.exceptions import ConflictError, NotFoundError
from app.core.storage import StorageBackend, get_storage
from app.models.archivo import Archivo
from app.models.reporte import Reporte, ReporteEvidencia

# Límites y tipos admitidos (imágenes y PDF para la demo).
MAX_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
ALLOWED_CONTENT_TYPES: frozenset[str] = frozenset(
    {
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/gif",
        "application/pdf",
    }
)


def _validate(file: UploadFile, raw: bytes) -> None:
    """Valida tipo MIME y tamaño. Lanza ``ConflictError`` (422-ish) si falla."""
    if not raw:
        raise ConflictError("El archivo está vacío.")
    if len(raw) > MAX_SIZE_BYTES:
        mb = MAX_SIZE_BYTES // (1024 * 1024)
        raise ConflictError(f"El archivo excede el límite de {mb} MB.")
    content_type = (file.content_type or "").lower()
    if content_type not in ALLOWED_CONTENT_TYPES:
        permitidos = ", ".join(sorted(ALLOWED_CONTENT_TYPES))
        raise ConflictError(
            f"Tipo de archivo no permitido ({content_type or 'desconocido'}). "
            f"Permitidos: {permitidos}."
        )


async def subir_archivo(
    db: AsyncSession,
    user,
    file: UploadFile,
    *,
    categoria: str = "otro",
    entity_type: str | None = None,
    entity_id: str | None = None,
    lat: float | None = None,
    lng: float | None = None,
    audit: AuditLogger | None = None,
    storage: StorageBackend | None = None,
) -> Archivo:
    """Sube un archivo, lo persiste en storage y registra una fila ``Archivo``.

    El tenant se deriva de ``user.tenant_id``. Devuelve la instancia ``Archivo``
    ya añadida y *flushed* en la sesión (el commit lo hace ``get_db``).
    """
    storage = storage or get_storage()

    raw = await file.read()
    _validate(file, raw)

    key = StorageBackend.build_key(user.tenant_id, file.filename or "archivo")
    url = await storage.save(raw, key, file.content_type or "application/octet-stream")

    archivo = Archivo(
        id=str(uuid.uuid4()),
        tenant_id=user.tenant_id,
        nombre=file.filename or key.rsplit("/", 1)[-1],
        content_type=file.content_type or "application/octet-stream",
        size_bytes=len(raw),
        storage_key=key,
        url=url,
        categoria=categoria,
        entity_type=entity_type,
        entity_id=entity_id,
        lat=lat,
        lng=lng,
        created_by=user.id,
    )
    db.add(archivo)
    await db.flush()

    if audit is not None:
        await audit.log(
            action="create",
            user_id=user.id,
            tenant_id=user.tenant_id,
            entity_type="archivo",
            entity_id=archivo.id,
            extra={
                "categoria": categoria,
                "content_type": archivo.content_type,
                "size_bytes": archivo.size_bytes,
                "linked_entity_type": entity_type,
                "linked_entity_id": entity_id,
            },
        )

    return archivo


async def subir_evidencia_reporte(
    db: AsyncSession,
    user,
    reporte_id: str,
    file: UploadFile,
    *,
    caption: str | None = None,
    tipo: str | None = None,
    momento: str | None = None,
    lat: float | None = None,
    lng: float | None = None,
    audit: AuditLogger | None = None,
    storage: StorageBackend | None = None,
) -> tuple[Archivo, ReporteEvidencia]:
    """Sube una imagen y crea una ``ReporteEvidencia`` geoetiquetada.

    Verifica que el reporte exista y pertenezca al tenant del usuario, registra
    el ``Archivo`` (categoría ``evidencia``, ligado al reporte) y crea la fila
    ``ReporteEvidencia`` con lat/lng, ``timestamp_captura`` y ``momento``.
    """
    # WHERE tenant_id: el reporte debe ser del tenant del usuario.
    stmt = select(Reporte).where(
        Reporte.id == reporte_id, Reporte.tenant_id == user.tenant_id
    )
    if (await db.execute(stmt)).scalar_one_or_none() is None:
        raise NotFoundError("Reporte", reporte_id)

    archivo = await subir_archivo(
        db,
        user,
        file,
        categoria="evidencia",
        entity_type="reporte",
        entity_id=reporte_id,
        lat=lat,
        lng=lng,
        audit=audit,
        storage=storage,
    )

    now = datetime.now(UTC)
    evidencia = ReporteEvidencia(
        id=f"{reporte_id}-ev-{uuid.uuid4().hex[:8]}",
        reporte_id=reporte_id,
        url=archivo.url,
        caption=caption,
        fecha=now,
        autor=user.nombre,
        tipo=tipo,
        lat=lat,
        lng=lng,
        timestamp_captura=now,
        momento=momento,
    )
    db.add(evidencia)
    await db.flush()

    if audit is not None:
        await audit.log(
            action="create",
            user_id=user.id,
            tenant_id=user.tenant_id,
            entity_type="reporte_evidencia",
            entity_id=evidencia.id,
            extra={"archivo_id": archivo.id, "reporte_id": reporte_id},
        )

    return archivo, evidencia


async def get_archivo_by_key(
    db: AsyncSession, tenant_id: str, storage_key: str
) -> Archivo | None:
    """Busca un ``Archivo`` por su clave de storage dentro del tenant."""
    stmt = select(Archivo).where(
        Archivo.tenant_id == tenant_id, Archivo.storage_key == storage_key
    )
    return (await db.execute(stmt)).scalar_one_or_none()
