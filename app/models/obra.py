from datetime import datetime
from decimal import Decimal

from sqlalchemy import DECIMAL, DateTime, Float, ForeignKey, Integer, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Obra(TimestampMixin, Base):
    __tablename__ = "obras"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(50), ForeignKey("tenants.id"), index=True)
    folio: Mapped[str] = mapped_column(String(30), unique=True)
    nombre: Mapped[str] = mapped_column(String(300))
    descripcion: Mapped[str | None] = mapped_column(Text)
    categoria_id: Mapped[str] = mapped_column(String(30), ForeignKey("obra_categorias.id"))
    estado: Mapped[str] = mapped_column(String(20))
    prioridad: Mapped[str] = mapped_column(String(15))
    colonia_id: Mapped[str] = mapped_column(String(60), ForeignKey("colonias.id"))
    colonia_nombre: Mapped[str | None] = mapped_column(String(120))
    center_lng: Mapped[float | None] = mapped_column(Float)
    center_lat: Mapped[float | None] = mapped_column(Float)
    responsable_nombre: Mapped[str | None] = mapped_column(String(120))
    responsable_iniciales: Mapped[str | None] = mapped_column(String(5))
    responsable_cargo: Mapped[str | None] = mapped_column(String(200))
    contratista_id: Mapped[str | None] = mapped_column(
        String(10), ForeignKey("contratistas.id"), nullable=True
    )
    fecha_inicio: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fecha_fin_estimada: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fecha_fin_real: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    avance_pct: Mapped[int] = mapped_column(SmallInteger, default=0)
    presupuesto_autorizado: Mapped[Decimal | None] = mapped_column(DECIMAL(14, 2))
    presupuesto_ejercido: Mapped[Decimal | None] = mapped_column(DECIMAL(14, 2))

    categoria = relationship("ObraCategoria", lazy="selectin")
    contratista = relationship("Contratista", lazy="selectin")
    colonia = relationship("Colonia", lazy="selectin")
    presupuesto_items = relationship(
        "ObraPresupuestoItem", back_populates="obra", cascade="all, delete-orphan", lazy="selectin"
    )
    equipo = relationship(
        "ObraEquipo", back_populates="obra", cascade="all, delete-orphan", lazy="selectin"
    )
    calles_afectadas = relationship(
        "ObraCalleAfectada", back_populates="obra", cascade="all, delete-orphan", lazy="selectin"
    )
    timeline = relationship(
        "ObraTimeline", back_populates="obra", cascade="all, delete-orphan", lazy="selectin"
    )
    documentos = relationship(
        "ObraDocumento", back_populates="obra", cascade="all, delete-orphan", lazy="selectin"
    )
    evidencias = relationship(
        "ObraEvidencia", back_populates="obra", cascade="all, delete-orphan", lazy="selectin"
    )


class ObraPresupuestoItem(Base):
    __tablename__ = "obra_presupuesto_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    obra_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("obras.id", ondelete="CASCADE"), index=True
    )
    concepto: Mapped[str] = mapped_column(String(200))
    unidad: Mapped[str | None] = mapped_column(String(20))
    cantidad: Mapped[Decimal | None] = mapped_column(DECIMAL(12, 2))
    precio_unitario: Mapped[Decimal | None] = mapped_column(DECIMAL(12, 2))
    importe: Mapped[Decimal | None] = mapped_column(DECIMAL(14, 2))

    obra = relationship("Obra", back_populates="presupuesto_items")


class ObraEquipo(Base):
    __tablename__ = "obra_equipo"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    obra_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("obras.id", ondelete="CASCADE"), index=True
    )
    nombre: Mapped[str | None] = mapped_column(String(120))
    iniciales: Mapped[str | None] = mapped_column(String(5))
    rol: Mapped[str | None] = mapped_column(String(60))
    contacto: Mapped[str | None] = mapped_column(String(120))

    obra = relationship("Obra", back_populates="equipo")


class ObraCalleAfectada(Base):
    __tablename__ = "obra_calles_afectadas"

    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    obra_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("obras.id", ondelete="CASCADE"), index=True
    )
    nombre: Mapped[str | None] = mapped_column(String(200))
    estado: Mapped[str | None] = mapped_column(String(20))
    coordenadas: Mapped[dict | None] = mapped_column(JSONB)
    fecha_inicio: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fecha_fin_estimada: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    alternativas_viales: Mapped[dict | None] = mapped_column(JSONB)
    tipo_afectacion: Mapped[str | None] = mapped_column(
        String(10), nullable=True
    )  # total | parcial | desvio

    obra = relationship("Obra", back_populates="calles_afectadas")


class ObraTimeline(Base):
    __tablename__ = "obra_timeline"

    id: Mapped[str] = mapped_column(String(30), primary_key=True)
    obra_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("obras.id", ondelete="CASCADE"), index=True
    )
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    tipo: Mapped[str] = mapped_column(String(20))
    titulo: Mapped[str] = mapped_column(String(200))
    descripcion: Mapped[str | None] = mapped_column(Text)
    autor_nombre: Mapped[str | None] = mapped_column(String(120))
    autor_iniciales: Mapped[str | None] = mapped_column(String(5))
    autor_rol: Mapped[str | None] = mapped_column(String(100))

    obra = relationship("Obra", back_populates="timeline")


class ObraDocumento(Base):
    __tablename__ = "obra_documentos"

    id: Mapped[str] = mapped_column(String(30), primary_key=True)
    obra_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("obras.id", ondelete="CASCADE"), index=True
    )
    nombre: Mapped[str] = mapped_column(String(200))
    tipo: Mapped[str | None] = mapped_column(String(30))
    tamano_kb: Mapped[int | None] = mapped_column(Integer)
    fecha_subida: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    autor: Mapped[str | None] = mapped_column(String(120))

    obra = relationship("Obra", back_populates="documentos")


class ObraEvidencia(Base):
    __tablename__ = "obra_evidencias"

    id: Mapped[str] = mapped_column(String(30), primary_key=True)
    obra_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("obras.id", ondelete="CASCADE"), index=True
    )
    url: Mapped[str | None] = mapped_column(String(500))
    caption: Mapped[str | None] = mapped_column(String(200))
    fecha: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    autor: Mapped[str | None] = mapped_column(String(120))
    tipo: Mapped[str | None] = mapped_column(String(10))  # antes | durante | despues

    obra = relationship("Obra", back_populates="evidencias")
