import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AgenteInteraccion(Base):
    """Bitácora de cada turno de conversación con el Agente Institucional."""

    __tablename__ = "agente_interacciones"
    __table_args__ = (Index("ix_agente_int_user_ts", "user_id", "created_at"),)

    id: Mapped[str] = mapped_column(
        String(40), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    tenant_id: Mapped[str] = mapped_column(String(50), ForeignKey("tenants.id"), index=True)
    rol: Mapped[str] = mapped_column(String(20))  # rol conceptual del usuario
    canal: Mapped[str] = mapped_column(String(20), default="chat")  # chat | classify
    pregunta: Mapped[str] = mapped_column(Text)
    respuesta: Mapped[str] = mapped_column(Text)
    fuentes: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    sin_informacion: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )
