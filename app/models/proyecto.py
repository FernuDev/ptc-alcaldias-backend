"""Modelos de Plan.IA — gestión de proyectos institucionales.

Plan.IA planea/ejecuta/demuestra obras, programas, eventos e iniciativas con
trazabilidad de gobierno. Aquí viven el portafolio (Proyecto) y el plan de
trabajo con dependencias para cronograma/Gantt (ProyectoTarea).
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    DECIMAL,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Proyecto(Base):
    """Elemento del portafolio institucional.

    ``tipo`` distingue obra / programa social / evento / iniciativa estratégica.
    Puede alinearse a un compromiso de gobierno (``compromiso_id``) y al Plan de
    Desarrollo / POA (``pdm_eje``). Si nace de un expediente de zona, conserva la
    huella en ``origen_zona``.
    """

    __tablename__ = "proyectos"

    id: Mapped[str] = mapped_column(
        String(40), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tenant_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("tenants.id"), index=True
    )
    nombre: Mapped[str] = mapped_column(String(200))
    tipo: Mapped[str] = mapped_column(
        String(12), default="obra"
    )  # obra | programa | evento | iniciativa
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    estado: Mapped[str] = mapped_column(
        String(15), default="planeacion"
    )  # planeacion | en_ejecucion | en_pausa | concluido | cancelado
    prioridad: Mapped[str] = mapped_column(String(10), default="media")
    avance_pct: Mapped[int] = mapped_column(SmallInteger, default=0)
    responsable_nombre: Mapped[str | None] = mapped_column(String(120), nullable=True)
    area_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    compromiso_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    pdm_eje: Mapped[str | None] = mapped_column(String(160), nullable=True)
    presupuesto_estimado: Mapped[float | None] = mapped_column(
        DECIMAL(14, 2), nullable=True
    )
    fecha_inicio: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    fecha_fin_estimada: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    origen_zona: Mapped[str | None] = mapped_column(String(160), nullable=True)
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

    tareas: Mapped[list["ProyectoTarea"]] = relationship(
        back_populates="proyecto",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class ProyectoTarea(Base):
    """Tarea del plan de trabajo con dependencias (insumo de cronograma/Gantt)."""

    __tablename__ = "proyecto_tareas"

    id: Mapped[str] = mapped_column(
        String(40), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    proyecto_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("proyectos.id", ondelete="CASCADE"), index=True
    )
    tenant_id: Mapped[str] = mapped_column(String(50), index=True)
    nombre: Mapped[str] = mapped_column(String(200))
    estado: Mapped[str] = mapped_column(
        String(12), default="pendiente"
    )  # pendiente | en_progreso | completada
    avance_pct: Mapped[int] = mapped_column(SmallInteger, default=0)
    fecha_inicio: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    fecha_fin: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    depende_de: Mapped[str | None] = mapped_column(String(40), nullable=True)
    responsable: Mapped[str | None] = mapped_column(String(120), nullable=True)
    orden: Mapped[int] = mapped_column(Integer, default=0)

    proyecto: Mapped["Proyecto"] = relationship(back_populates="tareas")


class ProyectoStakeholder(Base):
    """Actor/involucrado de un proyecto (capa de Coordinación)."""

    __tablename__ = "proyecto_stakeholders"

    id: Mapped[str] = mapped_column(
        String(40), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    proyecto_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("proyectos.id", ondelete="CASCADE"), index=True
    )
    tenant_id: Mapped[str] = mapped_column(String(50), index=True)
    nombre: Mapped[str] = mapped_column(String(160))
    organizacion: Mapped[str | None] = mapped_column(String(160), nullable=True)
    rol: Mapped[str] = mapped_column(
        String(15), default="interesado"
    )  # interesado | responsable | aliado | afectado
    postura: Mapped[str] = mapped_column(
        String(10), default="neutral"
    )  # a_favor | neutral | en_contra
    contacto: Mapped[str | None] = mapped_column(String(160), nullable=True)
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)


class ProyectoRiesgo(Base):
    """Riesgo registrado de un proyecto (capa de Coordinación)."""

    __tablename__ = "proyecto_riesgos"

    id: Mapped[str] = mapped_column(
        String(40), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    proyecto_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("proyectos.id", ondelete="CASCADE"), index=True
    )
    tenant_id: Mapped[str] = mapped_column(String(50), index=True)
    descripcion: Mapped[str] = mapped_column(Text)
    probabilidad: Mapped[str] = mapped_column(String(6), default="media")  # baja|media|alta
    impacto: Mapped[str] = mapped_column(String(6), default="medio")  # bajo|medio|alto
    mitigacion: Mapped[str | None] = mapped_column(Text, nullable=True)
    estado: Mapped[str] = mapped_column(
        String(14), default="abierto"
    )  # abierto | mitigado | materializado | cerrado


class ProyectoAprobacion(Base):
    """Paso de un flujo de aprobación configurable (capa de Coordinación)."""

    __tablename__ = "proyecto_aprobaciones"

    id: Mapped[str] = mapped_column(
        String(40), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    proyecto_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("proyectos.id", ondelete="CASCADE"), index=True
    )
    tenant_id: Mapped[str] = mapped_column(String(50), index=True)
    etapa: Mapped[str] = mapped_column(String(120))
    responsable: Mapped[str | None] = mapped_column(String(120), nullable=True)
    estado: Mapped[str] = mapped_column(
        String(10), default="pendiente"
    )  # pendiente | aprobado | rechazado
    comentario: Mapped[str | None] = mapped_column(Text, nullable=True)
    orden: Mapped[int] = mapped_column(Integer, default=0)
    fecha_resolucion: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
