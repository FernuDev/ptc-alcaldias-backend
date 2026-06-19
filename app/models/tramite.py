import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Tramite(Base):
    """Trámite o servicio que ofrece la alcaldía a la ciudadanía.

    Ficha pública con todo lo necesario para realizar un trámite presencial o
    en línea: requisitos, costo, tiempo estimado, documentos descargables, dónde
    acudir y horarios de atención. El ``tenant_id`` identifica a la alcaldía.
    """

    __tablename__ = "tramites"

    id: Mapped[str] = mapped_column(
        String(40), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tenant_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("tenants.id"), index=True
    )
    nombre: Mapped[str] = mapped_column(String(200))
    dependencia: Mapped[str] = mapped_column(String(160))
    area_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Lista de strings con los requisitos del trámite.
    requisitos: Mapped[list] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    costo: Mapped[str | None] = mapped_column(String(120), nullable=True)
    tiempo_estimado: Mapped[str | None] = mapped_column(String(120), nullable=True)
    vigencia: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Lista de objetos {"nombre": str, "url": str} con formatos descargables.
    documentos: Mapped[list] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    donde_acudir: Mapped[str | None] = mapped_column(String(300), nullable=True)
    horarios: Mapped[str | None] = mapped_column(String(160), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )


class Aviso(Base):
    """Aviso o campaña institucional difundida a la ciudadanía.

    Comunicados de la alcaldía (cortes de servicio, convocatorias, jornadas) y
    campañas (vacunación, descacharrización, etc.). El ``tipo`` distingue entre
    un ``aviso`` puntual y una ``campania`` con difusión sostenida.
    """

    __tablename__ = "avisos"

    id: Mapped[str] = mapped_column(
        String(40), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tenant_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("tenants.id"), index=True
    )
    titulo: Mapped[str] = mapped_column(String(200))
    cuerpo: Mapped[str] = mapped_column(Text)
    tipo: Mapped[str] = mapped_column(
        String(12), default="aviso", server_default="aviso"
    )  # aviso | campania
    area_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    segmento: Mapped[str | None] = mapped_column(String(120), nullable=True)
    fecha: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )
    activo: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=func.true()
    )
