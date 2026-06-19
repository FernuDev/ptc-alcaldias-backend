import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SolicitudARCO(Base):
    """Solicitud de derechos ARCO (Acceso, Rectificación, Cancelación, Oposición).

    Canal de privacidad para que cualquier persona ejerza sus derechos sobre los
    datos personales tratados por la alcaldía. El ``tenant_id`` identifica a la
    alcaldía destinataria; el solicitante se identifica por su correo.
    """

    __tablename__ = "solicitudes_arco"

    id: Mapped[str] = mapped_column(
        String(40), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tenant_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("tenants.id"), index=True
    )
    tipo: Mapped[str] = mapped_column(
        String(15)
    )  # acceso | rectificacion | cancelacion | oposicion
    email_solicitante: Mapped[str] = mapped_column(String(120))
    descripcion: Mapped[str] = mapped_column(Text)
    estado: Mapped[str] = mapped_column(
        String(20), default="recibida", server_default="recibida"
    )  # recibida | en_tramite | atendida | rechazada
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )
