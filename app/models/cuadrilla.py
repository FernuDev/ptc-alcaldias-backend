from sqlalchemy import Column, ForeignKey, SmallInteger, String, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

cuadrilla_especialidades = Table(
    "cuadrilla_especialidades",
    Base.metadata,
    Column(
        "cuadrilla_id",
        String(10),
        ForeignKey("cuadrillas.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "categoria_id",
        String(30),
        ForeignKey("categorias.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Cuadrilla(Base):
    __tablename__ = "cuadrillas"

    id: Mapped[str] = mapped_column(String(10), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(50), ForeignKey("tenants.id"), index=True)
    nombre: Mapped[str] = mapped_column(String(80))
    integrantes: Mapped[int | None] = mapped_column(SmallInteger)

    especialidades = relationship("Categoria", secondary=cuadrilla_especialidades, lazy="selectin")
