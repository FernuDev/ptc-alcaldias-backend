from decimal import Decimal

from sqlalchemy import ARRAY, DECIMAL, Float, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Tenant(TimestampMixin, Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120))
    nombre_corto: Mapped[str] = mapped_column(String(60))
    clave_geo: Mapped[str] = mapped_column(String(10), unique=True)
    acronimo: Mapped[str] = mapped_column(String(10))
    bbox: Mapped[list[float]] = mapped_column(ARRAY(Float), nullable=True)
    center: Mapped[list[float]] = mapped_column(ARRAY(Float), nullable=True)
    polygon_path: Mapped[str | None] = mapped_column(String(200))
    escudo_path: Mapped[str | None] = mapped_column(String(200))
    primario: Mapped[str] = mapped_column(String(7))
    secundario: Mapped[str | None] = mapped_column(String(7))
    dorado: Mapped[str | None] = mapped_column(String(7))
    poblacion: Mapped[int] = mapped_column(Integer, default=0)
    area_km2: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), default=0)

    # ── Marca / White-label (módulo Marca) ───────────────────────────────────
    # Documento de design tokens (BrandTokens) con los *overrides* explícitos del
    # tenant. NULL ⇒ usa defaults MC + escalares (primario/secundario/dorado).
    # ``primario``/``secundario``/``dorado``/``escudo_path`` se mantienen
    # sincronizados como denormalización para consumidores legacy (PDF, público).
    brand: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Logo horizontal subido (clave de storage); para header/login/documentos.
    logo_path: Mapped[str | None] = mapped_column(String(200), nullable=True)
    favicon_path: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Versión de marca: incrementa en cada guardado; alimenta el historial.
    brand_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")

    # ── Configuración operativa (módulo 13, persistente por tenant) ──────────
    titular_nombre: Mapped[str | None] = mapped_column(String(160), nullable=True)
    titular_cargo: Mapped[str | None] = mapped_column(String(160), nullable=True)
    contacto: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # SLA en días por prioridad, p.ej. {"critica":1,"alta":3,"media":7,"baja":15}
    sla_dias: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Flujos de atención configurables (lista de objetos {nombre, pasos:[...]}).
    flujos: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # Checklists de cuadrillas por categoría: {"bacheo":["paso1",...], ...}
    checklists: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Parámetros del expediente de zona (clustering espacio-temporal, REQ-09):
    # {"umbral": 8, "ventana_dias": 365, "radio_m": 300}
    zona_params: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Esquema de almacenamiento documental (REQ-04): nube_gestionada (default) |
    # conector_nas (NAS del cliente) | subarrendamiento_dedicado.
    storage_scheme: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # Config del conector NAS: {tipo, host, endpoint, estado, credencial_configurada}.
    # NUNCA persiste credenciales en claro (sólo una marca de que existe el secreto).
    storage_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    users = relationship("User", back_populates="tenant", lazy="selectin")
    colonias = relationship("Colonia", back_populates="tenant", lazy="selectin")
