from decimal import Decimal

from sqlalchemy import DECIMAL, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Categoria(Base):
    __tablename__ = "categorias"

    id: Mapped[str] = mapped_column(String(30), primary_key=True)
    label: Mapped[str] = mapped_column(String(60))
    color: Mapped[str] = mapped_column(String(7))
    icono: Mapped[str | None] = mapped_column(String(30))
    peso: Mapped[Decimal] = mapped_column(DECIMAL(4, 2), default=0)


class ObraCategoria(Base):
    __tablename__ = "obra_categorias"

    id: Mapped[str] = mapped_column(String(30), primary_key=True)
    label: Mapped[str] = mapped_column(String(60))
    color: Mapped[str] = mapped_column(String(7))
    peso: Mapped[Decimal] = mapped_column(DECIMAL(4, 2), default=0)
