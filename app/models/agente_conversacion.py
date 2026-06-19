import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AgenteConversacion(Base):
    """Conversación persistida del agente institucional.

    Cada registro representa un hilo de chat completo. El campo `mensajes`
    almacena el historial serializado [{role, content, fuentes?, navegacion?}].
    """

    __tablename__ = "agente_conversaciones"
    __table_args__ = (
        Index("ix_agente_conv_user_updated", "user_id", "updated_at"),
    )

    id: Mapped[str] = mapped_column(
        String(40), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    tenant_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("tenants.id"), index=True
    )
    titulo: Mapped[str] = mapped_column(String(200))
    mensajes: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        onupdate=lambda: datetime.now(UTC),
    )
