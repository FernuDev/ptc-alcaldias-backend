import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AgenteDocumento(Base):
    """Metadatos de un documento ingestado en la base de conocimiento (RAG).

    Espejo gestionable de lo que vive en ChromaDB: permite listar, auditar y
    re-ingestar. `tenant_id` puede ser "global" (visible a todas las alcaldías),
    por eso NO es FK a tenants.
    """

    __tablename__ = "agente_documentos"
    __table_args__ = (Index("ix_agente_doc_tenant_nivel", "tenant_id", "nivel_visibilidad"),)

    id: Mapped[str] = mapped_column(
        String(40), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tenant_id: Mapped[str] = mapped_column(String(50), default="global")
    titulo: Mapped[str] = mapped_column(String(300))
    nivel_visibilidad: Mapped[str] = mapped_column(
        String(20)
    )  # publico | interno | ejecutivo | reservado
    area_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    fuente: Mapped[str | None] = mapped_column(String(300), nullable=True)
    fragmentos: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )
