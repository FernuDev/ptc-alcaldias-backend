from sqlalchemy import Boolean, Column, ForeignKey, String, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

user_areas = Table(
    "user_areas",
    Base.metadata,
    Column("user_id", String(50), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column(
        "categoria_id",
        String(30),
        ForeignKey("categorias.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(50), ForeignKey("tenants.id"), index=True)
    email: Mapped[str] = mapped_column(String(120), unique=True)
    nombre: Mapped[str] = mapped_column(String(120))
    iniciales: Mapped[str] = mapped_column(String(5))
    cargo: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20))  # admin | director_area | ciudadano
    avatar_tone: Mapped[str | None] = mapped_column(String(7))
    password_hash: Mapped[str] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Habilita el acceso a conocimiento de nivel "reservado" en el Agente Institucional.
    puede_ver_reservado: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # R5 · REQ-17: posición del usuario en el árbol organizacional. El alcance
    # (sub-árbol visible) y rol_nivel se derivan de este nodo.
    nodo_id: Mapped[str | None] = mapped_column(
        String(40), ForeignKey("org_nodos.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # true => personal de campo (jefe de cuadrilla / integrante): solo app móvil,
    # se le niega el backoffice. false => backoffice (del JUD hacia arriba).
    es_campo: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    tenant = relationship("Tenant", back_populates="users", lazy="selectin")
    areas = relationship("Categoria", secondary=user_areas, lazy="selectin")
    nodo = relationship("OrgNodo", lazy="selectin", foreign_keys=[nodo_id])
