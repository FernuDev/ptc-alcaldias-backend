from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DECIMAL,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Table,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

reporte_obra_relaciones = Table(
    "reporte_obra_relaciones",
    Base.metadata,
    Column(
        "reporte_id",
        String(20),
        ForeignKey("reportes.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "obra_id", String(20), ForeignKey("obras.id", ondelete="CASCADE"), primary_key=True
    ),
)


class Reporte(TimestampMixin, Base):
    __tablename__ = "reportes"
    __table_args__ = (
        Index("ix_reportes_tenant_fecha", "tenant_id", "fecha_creacion"),
        Index("ix_reportes_tenant_categoria", "tenant_id", "categoria_id"),
        Index("ix_reportes_tenant_estado", "tenant_id", "estado"),
    )

    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(50), ForeignKey("tenants.id"), index=True)
    folio: Mapped[str] = mapped_column(String(30), unique=True)
    categoria_id: Mapped[str] = mapped_column(String(30), ForeignKey("categorias.id"))
    estado: Mapped[str] = mapped_column(String(20))
    prioridad: Mapped[str] = mapped_column(String(10))
    fuente: Mapped[str] = mapped_column(String(20))
    cuadrilla_id: Mapped[str | None] = mapped_column(
        String(10), ForeignKey("cuadrillas.id"), nullable=True
    )
    colonia_id: Mapped[str] = mapped_column(String(60), ForeignKey("colonias.id"))
    colonia_nombre: Mapped[str | None] = mapped_column(String(120))
    lng: Mapped[float] = mapped_column(Float)
    lat: Mapped[float] = mapped_column(Float)
    peso: Mapped[int | None] = mapped_column(SmallInteger)
    titulo: Mapped[str] = mapped_column(String(200))
    descripcion: Mapped[str | None] = mapped_column(Text)
    ciudadano_nombre: Mapped[str | None] = mapped_column(String(100))
    ciudadano_iniciales: Mapped[str | None] = mapped_column(String(5))
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fecha_actualizacion: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fecha_cierre: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tiempo_atencion_horas: Mapped[Decimal | None] = mapped_column(DECIMAL(10, 1), nullable=True)
    costo_estimado: Mapped[Decimal | None] = mapped_column(DECIMAL(12, 2), nullable=True)
    gasto_real: Mapped[Decimal | None] = mapped_column(DECIMAL(12, 2), nullable=True)

    categoria = relationship("Categoria", lazy="selectin")
    cuadrilla = relationship("Cuadrilla", lazy="selectin")
    colonia = relationship("Colonia", lazy="selectin")
    evidencias = relationship(
        "ReporteEvidencia", back_populates="reporte", cascade="all, delete-orphan", lazy="selectin"
    )
    eventos = relationship(
        "ReporteEvento", back_populates="reporte", cascade="all, delete-orphan", lazy="selectin"
    )
    obras_relacionadas = relationship("Obra", secondary=reporte_obra_relaciones, lazy="selectin")


class ReporteEvidencia(Base):
    __tablename__ = "reporte_evidencias"

    id: Mapped[str] = mapped_column(String(30), primary_key=True)
    reporte_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("reportes.id", ondelete="CASCADE"), index=True
    )
    url: Mapped[str] = mapped_column(String(500))
    caption: Mapped[str | None] = mapped_column(String(200))
    fecha: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    autor: Mapped[str | None] = mapped_column(String(100))
    tipo: Mapped[str | None] = mapped_column(String(20))  # ciudadano | cuadrilla | inspeccion
    # Evidencia geoetiquetada (captura georreferenciada en campo).
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    timestamp_captura: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    momento: Mapped[str | None] = mapped_column(String(10), nullable=True)  # antes | despues

    reporte = relationship("Reporte", back_populates="evidencias")


class ReporteEvento(Base):
    __tablename__ = "reporte_eventos"

    id: Mapped[str] = mapped_column(String(30), primary_key=True)
    reporte_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("reportes.id", ondelete="CASCADE"), index=True
    )
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    tipo: Mapped[str] = mapped_column(String(20))
    titulo: Mapped[str] = mapped_column(String(200))
    descripcion: Mapped[str | None] = mapped_column(Text)
    autor_nombre: Mapped[str | None] = mapped_column(String(100))
    autor_iniciales: Mapped[str | None] = mapped_column(String(5))
    autor_rol: Mapped[str | None] = mapped_column(String(100))

    reporte = relationship("Reporte", back_populates="eventos")
