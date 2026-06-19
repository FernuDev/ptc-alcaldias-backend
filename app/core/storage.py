"""Abstracción de almacenamiento de archivos (storage backend).

Define una interfaz ``StorageBackend`` mínima y una implementación local
(``LocalStorage``) que persiste los bytes en disco bajo ``data/uploads/<tenant>/``
y expone una URL servible (ruta ``/uploads/...``) que el router de uploads sirve
con ``FileResponse``.

Swappable a la nube
-------------------
La interfaz está diseñada para que un backend GCS/S3 sea intercambiable sin
tocar el servicio ni el router. Para añadir uno:

1. Implementa una subclase de ``StorageBackend`` (p. ej. ``GCSStorage``) cuyo
   ``save()`` haga ``blob.upload_from_string(file_bytes, content_type=...)`` y
   devuelva la URL pública o firmada del objeto. ``get_path()`` no aplica a la
   nube: devuelve ``None`` (el servir se delega a la URL del proveedor).
2. Cablea la selección en ``get_storage()`` leyendo ``STORAGE_BACKEND`` del
   entorno (``local`` | ``gcs`` | ``s3``).

La clave (``key``) generada es estable y opaca: ``<tenant>/<uuid>.<ext>``. El
mismo esquema de clave funciona como ruta local y como nombre de objeto en un
bucket, por lo que migrar de proveedor no requiere recalcular claves.

Configuración (vía ``os.getenv`` para no tocar ``config.py``):

- ``STORAGE_BACKEND``   backend activo (default ``local``).
- ``UPLOADS_DIR``       directorio base local (default ``<repo>/data/uploads``).
- ``UPLOADS_URL_PREFIX``prefijo de URL servible (default ``/uploads``).
"""

from __future__ import annotations

import os
import uuid
from abc import ABC, abstractmethod
from pathlib import Path

# Raíz del repo: este archivo vive en app/core/storage.py -> subir 3 niveles.
_REPO_ROOT = Path(__file__).resolve().parents[2]

# Defaults sensatos; configurables por entorno sin tocar config.py.
DEFAULT_UPLOADS_DIR = _REPO_ROOT / "data" / "uploads"
DEFAULT_URL_PREFIX = "/uploads"


class StorageBackend(ABC):
    """Contrato mínimo de un backend de almacenamiento de objetos.

    Toda implementación recibe ya los bytes en memoria y una ``key`` opaca
    generada por :meth:`build_key`. No conoce nada del dominio (tenant, entidad):
    la lógica de negocio vive en el servicio.
    """

    @abstractmethod
    async def save(self, file_bytes: bytes, key: str, content_type: str) -> str:
        """Persiste ``file_bytes`` bajo ``key`` y devuelve una URL servible."""

    @abstractmethod
    def get_path(self, key: str) -> Path | None:
        """Ruta local del objeto, o ``None`` si el backend no es local."""

    @staticmethod
    def build_key(tenant_id: str, filename: str) -> str:
        """Genera una clave opaca y estable ``<tenant>/<uuid>.<ext>``.

        Conserva la extensión original (saneada) para que el ``content_type`` se
        infiera correctamente al servir y para legibilidad humana.
        """
        ext = Path(filename).suffix.lower().lstrip(".")
        # Saneamos: solo alfanumérico, máx 8 chars (jpg, jpeg, png, webp, pdf...).
        ext = "".join(c for c in ext if c.isalnum())[:8]
        name = uuid.uuid4().hex
        if ext:
            name = f"{name}.{ext}"
        # tenant saneado para que no escape del directorio base.
        safe_tenant = "".join(c for c in tenant_id if c.isalnum() or c in "-_") or "default"
        return f"{safe_tenant}/{name}"


class LocalStorage(StorageBackend):
    """Backend de disco local para desarrollo/demo.

    Guarda en ``<base_dir>/<tenant>/<uuid>.<ext>`` y devuelve una URL relativa
    ``<url_prefix>/<key>`` que el router de uploads sirve con ``FileResponse``.
    """

    def __init__(
        self,
        base_dir: Path | str | None = None,
        url_prefix: str | None = None,
    ) -> None:
        self.base_dir = Path(
            base_dir or os.getenv("UPLOADS_DIR", str(DEFAULT_UPLOADS_DIR))
        ).resolve()
        self.url_prefix = (
            url_prefix or os.getenv("UPLOADS_URL_PREFIX", DEFAULT_URL_PREFIX)
        ).rstrip("/")
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        """Resuelve ``key`` a una ruta absoluta dentro de ``base_dir``.

        Protege contra path traversal: el destino debe quedar bajo ``base_dir``.
        """
        target = (self.base_dir / key).resolve()
        if not target.is_relative_to(self.base_dir):
            raise ValueError(f"Clave de storage inválida: {key!r}")
        return target

    async def save(self, file_bytes: bytes, key: str, content_type: str) -> str:
        target = self._resolve(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        # Escritura síncrona (demo). Para alto throughput, delegar a un thread
        # pool (anyio.to_thread.run_sync) o usar aiofiles.
        target.write_bytes(file_bytes)
        return f"{self.url_prefix}/{key}"

    def get_path(self, key: str) -> Path | None:
        target = self._resolve(key)
        if not target.is_file():
            return None
        return target


def get_storage() -> StorageBackend:
    """Devuelve el backend de storage activo según ``STORAGE_BACKEND``.

    Punto único de selección para que el servicio y el router no conozcan la
    implementación concreta. Hoy solo ``local``; añadir ``gcs``/``s3`` aquí.
    """
    backend = os.getenv("STORAGE_BACKEND", "local").lower()
    if backend == "local":
        return LocalStorage()
    raise ValueError(
        f"STORAGE_BACKEND={backend!r} no soportado. "
        "Implementa una subclase de StorageBackend y cablea su selección aquí."
    )
