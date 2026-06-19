"""Servicio de documentos versionados (REQ-04).

Un "documento" es una fila :class:`~app.models.archivo.Archivo` con
``categoria='documento'``. El versionado se apoya en las columnas de versionado
de ``Archivo`` (añadidas por Spine):

- ``version``      número de versión (1-based).
- ``reemplaza_a``  id del ``Archivo`` anterior que esta versión sustituye.
- ``es_actual``    ``True`` solo en la versión vigente de la cadena.

Reutiliza :func:`app.services.archivo_service.subir_archivo` (validación de
tipo/tamaño, persistencia en el backend de storage vía :mod:`app.core.storage`
y creación de la fila ``Archivo``). El servir/descargar binarios se delega al
router de uploads existente (``GET /uploads/file/{key}``): cada documento expone
su ``url`` (``/uploads/<key>``) y su ``storage_key``.

El tenant SIEMPRE se deriva de ``user.tenant_id`` (nunca del body), conforme a
la regla multi-tenant del proyecto. Cada documento se aísla por ``tenant_id`` en
todas las consultas, evitando fuga entre tenants.
"""

from __future__ import annotations

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditLogger
from app.core.exceptions import ForbiddenError, NotFoundError
from app.core.permissions import Permission, has_permission
from app.core.storage import StorageBackend
from app.models.archivo import Archivo
from app.models.user import User
from app.services import archivo_service

# Categoría funcional que distingue a un documento del resto de archivos.
CATEGORIA_DOCUMENTO = "documento"


def _puede_gestionar(user: User) -> bool:
    """Roles que pueden subir/versionar documentos.

    Capacidades de configuración o gestión de usuarios (admin/director), o el rol
    ``director_area`` por su gobierno del área. Razona sobre permisos de la matriz
    para no acoplar a la lista exacta de roles.
    """
    return (
        has_permission(user.role, Permission.CONFIG_GESTIONAR)
        or has_permission(user.role, Permission.USUARIO_GESTIONAR)
        or user.role == "director_area"
    )


async def _get_documento(
    db: AsyncSession, tenant_id: str, documento_id: str
) -> Archivo:
    """Carga un documento del tenant o lanza ``NotFoundError``.

    Acota a ``categoria='documento'`` para que ids de otras categorías de
    ``Archivo`` (evidencias, etc.) no se traten como documentos.
    """
    stmt = select(Archivo).where(
        Archivo.id == documento_id,
        Archivo.tenant_id == tenant_id,
        Archivo.categoria == CATEGORIA_DOCUMENTO,
    )
    documento = (await db.execute(stmt)).scalar_one_or_none()
    if documento is None:
        raise NotFoundError("Documento", documento_id)
    return documento


async def subir_version(
    db: AsyncSession,
    user: User,
    file: UploadFile,
    *,
    nombre: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    reemplaza_a: str | None = None,
    audit: AuditLogger | None = None,
    storage: StorageBackend | None = None,
) -> Archivo:
    """Sube un documento nuevo o una nueva versión de uno existente.

    - Sin ``reemplaza_a``: crea un documento nuevo (``version=1``, ``es_actual=True``).
    - Con ``reemplaza_a``: localiza el documento previo (mismo tenant), lo marca
      ``es_actual=False`` y crea uno nuevo con ``version = prev.version + 1``,
      ``reemplaza_a = prev.id`` y ``es_actual = True``. Si el previo no es la
      versión vigente, igualmente se versiona sobre él (cadena enlazada).

    Requiere permiso de gestión (:func:`_puede_gestionar`). El tenant se deriva
    de ``user.tenant_id``. Devuelve la fila ``Archivo`` ya *flushed* (el commit lo
    hace ``get_db``).
    """
    if not _puede_gestionar(user):
        raise ForbiddenError("No tiene permisos para gestionar documentos")

    previo: Archivo | None = None
    version = 1
    if reemplaza_a:
        previo = await _get_documento(db, user.tenant_id, reemplaza_a)
        version = previo.version + 1
        # Heredamos vinculación a entidad si la subida no la especifica.
        if entity_type is None and entity_id is None:
            entity_type = previo.entity_type
            entity_id = previo.entity_id
        if nombre is None:
            nombre = previo.nombre

    # Persistimos binario + fila Archivo reutilizando el servicio de archivos.
    documento = await archivo_service.subir_archivo(
        db,
        user,
        file,
        categoria=CATEGORIA_DOCUMENTO,
        entity_type=entity_type,
        entity_id=entity_id,
        audit=audit,
        storage=storage,
    )

    # Nombre legible: prioriza el provisto; si no, el del archivo subido.
    if nombre:
        documento.nombre = nombre

    documento.version = version
    documento.es_actual = True

    if previo is not None:
        documento.reemplaza_a = previo.id
        previo.es_actual = False

    await db.flush()

    if audit is not None:
        await audit.log(
            action="update" if previo is not None else "create",
            user_id=user.id,
            tenant_id=user.tenant_id,
            entity_type="documento",
            entity_id=documento.id,
            extra={
                "version": documento.version,
                "reemplaza_a": documento.reemplaza_a,
                "nombre": documento.nombre,
            },
        )

    return documento


async def listar_documentos(
    tenant_id: str,
    db: AsyncSession,
    *,
    entity_type: str | None = None,
    entity_id: str | None = None,
    solo_actuales: bool = True,
) -> list[Archivo]:
    """Lista documentos del tenant, por defecto solo las versiones vigentes.

    Filtros opcionales por entidad asociada (``entity_type`` / ``entity_id``).
    Con ``solo_actuales=False`` devuelve todas las versiones de todos los
    documentos. Orden: más recientes primero.
    """
    stmt = select(Archivo).where(
        Archivo.tenant_id == tenant_id,
        Archivo.categoria == CATEGORIA_DOCUMENTO,
    )
    if solo_actuales:
        stmt = stmt.where(Archivo.es_actual.is_(True))
    if entity_type is not None:
        stmt = stmt.where(Archivo.entity_type == entity_type)
    if entity_id is not None:
        stmt = stmt.where(Archivo.entity_id == entity_id)
    stmt = stmt.order_by(Archivo.created_at.desc())
    return list((await db.execute(stmt)).scalars().all())


async def historial(
    tenant_id: str, db: AsyncSession, documento_id: str
) -> list[Archivo]:
    """Devuelve la cadena de versiones de un documento, de la más nueva a la más antigua.

    Reconstruye la cadena ``reemplaza_a`` hacia atrás partiendo del documento
    indicado y, si éste no es la versión vigente, avanza hacia adelante hasta la
    cabeza actual para incluir versiones posteriores. Todas acotadas al tenant.
    """
    inicio = await _get_documento(db, tenant_id, documento_id)

    # Hacia adelante: documentos que reemplazan (directa o transitivamente) a éste.
    adelante: list[Archivo] = []
    cursor_id = inicio.id
    while True:
        stmt = select(Archivo).where(
            Archivo.tenant_id == tenant_id,
            Archivo.categoria == CATEGORIA_DOCUMENTO,
            Archivo.reemplaza_a == cursor_id,
        )
        siguiente = (await db.execute(stmt)).scalar_one_or_none()
        if siguiente is None:
            break
        adelante.append(siguiente)
        cursor_id = siguiente.id

    # Hacia atrás: cadena de versiones previas vía reemplaza_a.
    atras: list[Archivo] = []
    cursor = inicio
    while cursor.reemplaza_a:
        stmt = select(Archivo).where(
            Archivo.id == cursor.reemplaza_a,
            Archivo.tenant_id == tenant_id,
            Archivo.categoria == CATEGORIA_DOCUMENTO,
        )
        anterior = (await db.execute(stmt)).scalar_one_or_none()
        if anterior is None:
            break
        atras.append(anterior)
        cursor = anterior

    # De la más nueva a la más antigua: posteriores (reversa) + inicio + previas.
    cadena = list(reversed(adelante)) + [inicio] + atras
    cadena.sort(key=lambda a: a.version, reverse=True)
    return cadena
