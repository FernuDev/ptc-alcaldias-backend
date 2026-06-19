import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, SmallInteger, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Compromiso(Base):
    """Compromiso de gobierno (meta pública con avance medible).

    Cada fila representa un compromiso/meta de la alcaldía, opcionalmente
    asociado a un área (categoría) y con una fecha objetivo. El avance se
    expresa en porcentaje y el estado refleja su salud frente a esa meta.
    """

    __tablename__ = "compromisos"

    id: Mapped[str] = mapped_column(
        String(40), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tenant_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("tenants.id"), index=True
    )
    titulo: Mapped[str] = mapped_column(String(200))
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    area_id: Mapped[str | None] = mapped_column(String(30), nullable=True)  # id de categoría/área
    meta: Mapped[str | None] = mapped_column(String(300), nullable=True)
    avance_pct: Mapped[int] = mapped_column(SmallInteger, default=0)
    # en_progreso | cumplido | en_riesgo | retrasado
    estado: Mapped[str] = mapped_column(String(12), default="en_progreso")
    fecha_objetivo: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )
