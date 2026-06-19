import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    Column,
    ForeignKey,
    SmallInteger,
    String,
    Table,
    func,
)
from sqlalchemy import (
    DateTime as SADateTime,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

cuadrilla_especialidades = Table(
    "cuadrilla_especialidades",
    Base.metadata,
    Column(
        "cuadrilla_id",
        String(10),
        ForeignKey("cuadrillas.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "categoria_id",
        String(30),
        ForeignKey("categorias.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Cuadrilla(Base):
    __tablename__ = "cuadrillas"

    id: Mapped[str] = mapped_column(String(10), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(50), ForeignKey("tenants.id"), index=True)
    nombre: Mapped[str] = mapped_column(String(80))
    # Contador denormalizado (lo leen stats / frontend). NO confundir con la
    # relación `miembros`, que es la lista real de personas de la cuadrilla.
    integrantes: Mapped[int | None] = mapped_column(SmallInteger)

    especialidades = relationship("Categoria", secondary=cuadrilla_especialidades, lazy="selectin")
    miembros = relationship(
        "Integrante",
        back_populates="cuadrilla",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class Integrante(Base):
    """Persona que forma parte de una cuadrilla de campo.

    Un integrante puede tener ``rol_campo`` 'jefe' (típicamente vinculado a una
    cuenta de usuario con rol jefe_cuadrilla vía ``user_id``) o 'integrante'.
    Es la nómina operativa real de la cuadrilla, distinta del contador
    denormalizado ``Cuadrilla.integrantes``.
    """

    __tablename__ = "integrantes"

    id: Mapped[str] = mapped_column(
        String(40), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    cuadrilla_id: Mapped[str] = mapped_column(
        String(10), ForeignKey("cuadrillas.id", ondelete="CASCADE"), index=True
    )
    tenant_id: Mapped[str] = mapped_column(String(50), ForeignKey("tenants.id"), index=True)
    user_id: Mapped[str | None] = mapped_column(
        String(50), ForeignKey("users.id"), nullable=True
    )
    nombre: Mapped[str] = mapped_column(String(120))
    rol_campo: Mapped[str] = mapped_column(String(15))  # jefe | integrante
    telefono: Mapped[str | None] = mapped_column(String(20), nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        SADateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )

    cuadrilla = relationship("Cuadrilla", back_populates="miembros", lazy="selectin")
