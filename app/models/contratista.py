from decimal import Decimal

from sqlalchemy import DECIMAL, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Contratista(Base):
    __tablename__ = "contratistas"

    id: Mapped[str] = mapped_column(String(10), primary_key=True)
    razon_social: Mapped[str] = mapped_column(String(200))
    rfc: Mapped[str] = mapped_column(String(13), unique=True)
    calificacion: Mapped[Decimal | None] = mapped_column(DECIMAL(3, 1))
