from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Notificacion(Base):
    __tablename__ = "notificaciones"
    __table_args__ = (
        Index("ix_notif_user_fecha", "user_id", "fecha"),
        Index("ix_notif_user_leida", "user_id", "leida"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(50), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    tenant_id: Mapped[str] = mapped_column(String(50), ForeignKey("tenants.id"), index=True)
    tipo: Mapped[str] = mapped_column(String(20))  # alerta | reporte | obra | cierre
    titulo: Mapped[str] = mapped_column(String(200))
    cuerpo: Mapped[str] = mapped_column(Text)
    href: Mapped[str | None] = mapped_column(String(300), nullable=True)
    entity_type: Mapped[str | None] = mapped_column(String(20), nullable=True)  # reporte | obra
    entity_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    leida: Mapped[bool] = mapped_column(Boolean, default=False)
    fecha: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
