import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Archivo(Base):
    """Registro central de archivos subidos al backend de storage.

    Cada fila describe un objeto almacenado (su clave/ruta en el storage, su URL
    pública o firmada, tamaño y tipo MIME) y opcionalmente lo vincula a una entidad
    del dominio (reporte, obra, etc.) vía ``entity_type`` + ``entity_id``. Sirve de
    índice consultable y auditable de todo lo cargado por tenant.
    """

    __tablename__ = "archivos"
    __table_args__ = (
        Index("ix_archivos_tenant_categoria", "tenant_id", "categoria"),
        Index("ix_archivos_entity", "entity_type", "entity_id"),
    )

    id: Mapped[str] = mapped_column(
        String(40), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tenant_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("tenants.id"), index=True
    )
    nombre: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(500))  # ruta/clave en el storage
    url: Mapped[str] = mapped_column(String(500))
    categoria: Mapped[str] = mapped_column(String(30))  # evidencia | documento | otro
    entity_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    # ── Versionado de archivos ──────────────────────────────────────────────
    version: Mapped[int] = mapped_column(
        SmallInteger, default=1, server_default="1"
    )
    reemplaza_a: Mapped[str | None] = mapped_column(
        String(40), nullable=True
    )  # id del Archivo anterior que esta versión reemplaza
    es_actual: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )
    created_by: Mapped[str | None] = mapped_column(String(50), nullable=True)
