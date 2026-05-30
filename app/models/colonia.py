from decimal import Decimal

from sqlalchemy import DECIMAL, Float, ForeignKey, Integer, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Colonia(Base):
    __tablename__ = "colonias"

    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(50), ForeignKey("tenants.id"), index=True)
    nombre: Mapped[str] = mapped_column(String(120))
    tipo: Mapped[str] = mapped_column(String(30))  # pueblo | barrio | colonia | unidad_habitacional
    center_lng: Mapped[float] = mapped_column(Float)
    center_lat: Mapped[float] = mapped_column(Float)
    area_ha: Mapped[Decimal | None] = mapped_column(DECIMAL(10, 2))
    poblacion: Mapped[int | None] = mapped_column(Integer)
    viviendas: Mapped[int | None] = mapped_column(Integer)
    densidad: Mapped[Decimal | None] = mapped_column(DECIMAL(10, 2))
    codigos_postales: Mapped[str | None] = mapped_column(String(100))
    servicio_agua: Mapped[int | None] = mapped_column(SmallInteger)
    servicio_drenaje: Mapped[int | None] = mapped_column(SmallInteger)
    servicio_luz: Mapped[int | None] = mapped_column(SmallInteger)
    servicio_internet: Mapped[int | None] = mapped_column(SmallInteger)
    factor_reportes: Mapped[Decimal | None] = mapped_column(DECIMAL(4, 2))

    tenant = relationship("Tenant", back_populates="colonias", lazy="selectin")
