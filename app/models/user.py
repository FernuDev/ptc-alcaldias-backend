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
    role: Mapped[str] = mapped_column(String(20))  # admin | director_area
    avatar_tone: Mapped[str | None] = mapped_column(String(7))
    password_hash: Mapped[str] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    tenant = relationship("Tenant", back_populates="users", lazy="selectin")
    areas = relationship("Categoria", secondary=user_areas, lazy="selectin")
