from decimal import Decimal

from sqlalchemy import ARRAY, DECIMAL, Float, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Tenant(TimestampMixin, Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120))
    nombre_corto: Mapped[str] = mapped_column(String(60))
    clave_geo: Mapped[str] = mapped_column(String(10), unique=True)
    acronimo: Mapped[str] = mapped_column(String(10))
    bbox: Mapped[list[float]] = mapped_column(ARRAY(Float), nullable=True)
    center: Mapped[list[float]] = mapped_column(ARRAY(Float), nullable=True)
    polygon_path: Mapped[str | None] = mapped_column(String(200))
    escudo_path: Mapped[str | None] = mapped_column(String(200))
    primario: Mapped[str] = mapped_column(String(7))
    secundario: Mapped[str | None] = mapped_column(String(7))
    dorado: Mapped[str | None] = mapped_column(String(7))
    poblacion: Mapped[int] = mapped_column(Integer, default=0)
    area_km2: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), default=0)

    # ── Configuración operativa (módulo 13, persistente por tenant) ──────────
    titular_nombre: Mapped[str | None] = mapped_column(String(160), nullable=True)
    titular_cargo: Mapped[str | None] = mapped_column(String(160), nullable=True)
    contacto: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # SLA en días por prioridad, p.ej. {"critica":1,"alta":3,"media":7,"baja":15}
    sla_dias: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Flujos de atención configurables (lista de objetos {nombre, pasos:[...]}).
    flujos: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # Checklists de cuadrillas por categoría: {"bacheo":["paso1",...], ...}
    checklists: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    users = relationship("User", back_populates="tenant", lazy="selectin")
    colonias = relationship("Colonia", back_populates="tenant", lazy="selectin")
