import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AgenteAccion(Base):
    """Acción preparada por el agente, pendiente de confirmación humana.

    El agente nunca ejecuta cambios sobre el sistema directamente: deja aquí una
    propuesta (`pendiente`) que un funcionario confirma explícitamente más tarde.
    """

    __tablename__ = "agente_acciones"
    __table_args__ = (Index("ix_agente_acc_user_estado", "user_id", "estado"),)

    id: Mapped[str] = mapped_column(
        String(40), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    tenant_id: Mapped[str] = mapped_column(String(50), ForeignKey("tenants.id"), index=True)
    tipo: Mapped[str] = mapped_column(String(20))  # turnar | asignar | cerrar | ...
    entity_type: Mapped[str] = mapped_column(String(20))  # reporte | obra
    entity_id: Mapped[str] = mapped_column(String(50))
    payload: Mapped[dict] = mapped_column(JSONB)
    estado: Mapped[str] = mapped_column(
        String(20), default="pendiente"
    )  # pendiente | confirmada | cancelada | expirada
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
