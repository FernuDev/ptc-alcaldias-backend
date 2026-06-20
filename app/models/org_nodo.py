"""Núcleo organizacional (R5 · REQ-17): árbol jerárquico configurable + capacidades.

El organigrama deja de estar cableado en código y pasa a ser **dato**. Cada
alcaldía (tenant) carga su propio árbol; los permisos se heredan de la posición
en el árbol (el alcance de un usuario = su nodo + todos sus descendientes) y las
capacidades (módulos) se encienden por nodo.

Convenciones del repo respetadas:
- PK string-uuid ``String(40)`` con ``default=str(uuid4())`` (como Integrante/Proyecto).
- ``tenant_id`` ``String(50)`` FK a ``tenants.id``, indexado (aislamiento multi-tenant).
- Niveles/tipos como ``String`` + comentario (no se usan enums de BD en el repo).
- Tabla puente ``nodo_capacidades`` como ``sqlalchemy.Table`` (espejo de
  ``cuadrilla_especialidades``), con la columna extra ``nivel_uso``.
"""

import uuid

from sqlalchemy import (
    Boolean,
    Column,
    ForeignKey,
    SmallInteger,
    String,
    Table,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

# Niveles del árbol (de la raíz hacia abajo). Paleta alineada al Briefing R5
# (8 niveles de MC: Alcalde, Director General, Director de Área,
# Subdirector/Coordinador, JUD, LCP, Enlace, operativo) + niveles de cuadrilla
# para la operación de campo. Es una paleta: cada alcaldía arma su jerarquía con
# los niveles que use (config, no custom).
NIVELES = (
    "alcalde",
    "dir_general",
    "dir_area",
    "subdireccion",  # Subdirector / Coordinador
    "jud",
    "lcp",  # Líder Coordinador de Proyecto
    "enlace",
    "coordinacion",  # Coordinación de cuadrillas
    "jefe_cuadrilla",
    "integrante",
    "operativo",  # operativo de campo
)

# Niveles que operan exclusivamente en campo (app móvil, nunca backoffice).
NIVELES_CAMPO = ("jefe_cuadrilla", "integrante", "operativo")

# Tipos estructurales del nodo (para la UI del editor de organigrama).
TIPOS = ("direccion", "subdireccion", "unidad", "cuadrilla")


# Capacidades encendidas por nodo. ``nivel_uso``: central | usa | parcial
# (espejo exacto de cuadrilla_especialidades + columna de intensidad de uso).
nodo_capacidades = Table(
    "nodo_capacidades",
    Base.metadata,
    Column(
        "nodo_id",
        String(40),
        ForeignKey("org_nodos.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "capacidad",
        String(30),
        ForeignKey("capacidades.codigo", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("nivel_uso", String(10), nullable=False, server_default="usa"),
)


class Capacidad(Base):
    """Catálogo fijo de capacidades (módulos asignables a un nodo).

    Seed: proyectos, obras, cuadrillas, tramites, recaudacion.
    """

    __tablename__ = "capacidades"

    codigo: Mapped[str] = mapped_column(String(30), primary_key=True)
    nombre: Mapped[str] = mapped_column(String(80))
    orden: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")


class OrgNodo(TimestampMixin, Base):
    """Nodo del árbol organizacional de un tenant (raíz = Alcalde)."""

    __tablename__ = "org_nodos"

    id: Mapped[str] = mapped_column(
        String(40), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tenant_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("tenants.id"), index=True
    )
    parent_id: Mapped[str | None] = mapped_column(
        String(40),
        ForeignKey("org_nodos.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    nivel: Mapped[str] = mapped_column(String(20))  # ver NIVELES
    tipo: Mapped[str] = mapped_column(String(20))  # ver TIPOS
    nombre: Mapped[str] = mapped_column(String(160))
    orden: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")
    activo: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    # Enlace opcional a una cuadrilla real (cuando tipo='cuadrilla').
    cuadrilla_id: Mapped[str | None] = mapped_column(
        String(10), ForeignKey("cuadrillas.id", ondelete="SET NULL"), nullable=True
    )

    parent = relationship(
        "OrgNodo", remote_side=[id], back_populates="children"
    )
    children = relationship(
        "OrgNodo",
        back_populates="parent",
        cascade="all, delete-orphan",
        order_by="OrgNodo.orden",
    )
