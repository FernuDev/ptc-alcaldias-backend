"""Modelos del módulo de campo (monitor en vivo de cuadrillas).

Cubren la operación táctica de las cuadrillas en la calle: turnos de trabajo,
tareas despachadas (originadas en reportes / obras o creadas manualmente),
rastreo GPS en serie temporal y el canal de mensajería monitor ↔ campo.

Todas las entidades llevan ``tenant_id`` (multi-tenant: el tenant SIEMPRE
proviene del JWT y se filtra por WHERE tenant_id en los servicios).
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Turno(Base):
    """Jornada operativa de una cuadrilla (abierta o cerrada)."""

    __tablename__ = "turnos"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(50), ForeignKey("tenants.id"), index=True)
    cuadrilla_id: Mapped[str] = mapped_column(
        String(10), ForeignKey("cuadrillas.id", ondelete="CASCADE"), index=True
    )
    inicio: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )
    fin: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    estado: Mapped[str] = mapped_column(
        String(10), default="abierto", server_default="abierto"
    )  # abierto | cerrado


class Tarea(Base):
    """Trabajo despachado a una cuadrilla / integrante.

    Se origina en un reporte ciudadano, una obra, o se crea manualmente
    (``origen_tipo``). Lleva su propia geolocalización y un checklist editable.
    """

    __tablename__ = "tareas"
    __table_args__ = (
        Index("ix_tareas_tenant_estado", "tenant_id", "estado"),
        Index("ix_tareas_cuadrilla_estado", "cuadrilla_id", "estado"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(50), ForeignKey("tenants.id"), index=True)
    cuadrilla_id: Mapped[str | None] = mapped_column(
        String(10), ForeignKey("cuadrillas.id"), nullable=True, index=True
    )
    integrante_id: Mapped[str | None] = mapped_column(
        String(40), ForeignKey("integrantes.id"), nullable=True
    )
    origen_tipo: Mapped[str] = mapped_column(String(10))  # reporte | obra | manual
    reporte_id: Mapped[str | None] = mapped_column(
        String(20), ForeignKey("reportes.id"), nullable=True
    )
    obra_id: Mapped[str | None] = mapped_column(
        String(20), ForeignKey("obras.id"), nullable=True
    )
    titulo: Mapped[str] = mapped_column(String(200))
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    prioridad: Mapped[str] = mapped_column(String(10), default="media", server_default="media")
    estado: Mapped[str] = mapped_column(
        String(12), default="pendiente", server_default="pendiente"
    )  # pendiente | en_ruta | en_sitio | cerrada
    orden_ruta: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    colonia_id: Mapped[str | None] = mapped_column(String(60), nullable=True)
    instrucciones: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Lista de pasos {"paso": str, "hecho": bool}.
    checklist: Mapped[list] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
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
    fecha_cierre: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Ubicacion(Base):
    """Punto GPS en serie temporal de una cuadrilla / integrante (mapa en vivo)."""

    __tablename__ = "ubicaciones"
    __table_args__ = (
        Index("ix_ubicaciones_cuadrilla_ts", "cuadrilla_id", "timestamp"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(50), ForeignKey("tenants.id"), index=True)
    cuadrilla_id: Mapped[str] = mapped_column(
        String(10), ForeignKey("cuadrillas.id", ondelete="CASCADE"), index=True
    )
    integrante_id: Mapped[str | None] = mapped_column(
        String(40), ForeignKey("integrantes.id"), nullable=True
    )
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )


class Mensaje(Base):
    """Mensaje del canal monitor ↔ campo (texto o nota de voz)."""

    __tablename__ = "mensajes_campo"
    __table_args__ = (
        Index("ix_mensajes_campo_cuadrilla", "cuadrilla_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(50), ForeignKey("tenants.id"), index=True)
    cuadrilla_id: Mapped[str] = mapped_column(
        String(10), ForeignKey("cuadrillas.id", ondelete="CASCADE"), index=True
    )
    tarea_id: Mapped[str | None] = mapped_column(
        String(40), ForeignKey("tareas.id"), nullable=True
    )
    autor_tipo: Mapped[str] = mapped_column(String(10))  # monitor | campo
    autor_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    tipo: Mapped[str] = mapped_column(String(8))  # texto | voz
    texto: Mapped[str | None] = mapped_column(Text, nullable=True)
    nota_voz_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )
