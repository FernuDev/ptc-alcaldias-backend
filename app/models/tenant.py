from decimal import Decimal

from sqlalchemy import ARRAY, DECIMAL, Float, Integer, String
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

    users = relationship("User", back_populates="tenant", lazy="selectin")
    colonias = relationship("Colonia", back_populates="tenant", lazy="selectin")
