from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class TenantBrandHistory(Base):
    """Snapshot inmutable de la marca de un tenant en una versión dada.

    Cada guardado en Configuración → Marca escribe una fila aquí con el
    documento de tokens **resuelto** que quedó vigente, permitiendo revertir a
    una versión anterior desde el historial.
    """

    __tablename__ = "tenant_brand_history"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    # Documento de tokens (BrandTokens serializado) vigente en esta versión.
    snapshot: Mapped[dict] = mapped_column(JSONB)
    updated_by: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )
