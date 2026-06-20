"""Contrato de *design tokens* de marca por tenant (white-label, módulo Marca).

La marca de cada alcaldía es **dato**, no código: un documento de tokens
semánticos versionable. Estos tokens se proyectan en el frontend sobre las
variables CSS de ``:root`` (ver ``lib/brand/apply-brand.ts``), de modo que toda
la UI (shadcn, Tailwind, charts) hereda el branding sin tocar componentes.

Principios:
- Tokens **semánticos** (``primary``, ``critical``, ``surface``…), nunca
  "rojo/azul". Cada token mapea 1:1 a una variable CSS en el cliente.
- Los **defaults reproducen el tema actual de Magdalena Contreras (MC)**: si un
  tenant no configuró marca, la plataforma se ve idéntica a hoy.
- ``BrandUpdate`` es parcial: el panel de Configuración → Marca envía solo lo
  que cambió; el resto se resuelve desde los defaults + escalares del tenant.

Los valores hex se validan con ``HEX_RE`` (``#RGB`` o ``#RRGGBB``).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# Hex de 3 o 6 dígitos. Tolerante a mayúsculas/minúsculas.
HEX_RE = r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$"
# CSS length para el radio base (rem | px | em). Acepta "0", "0.5rem", "8px"…
RADIUS_RE = r"^(?:0|[0-9]*\.?[0-9]+(?:rem|px|em))$"

FontSource = str  # "google" | "custom_upload" | "system"


class BrandColors(BaseModel):
    """Paleta semántica completa. Defaults = identidad institucional MC.

    Incluye **marca** (primary/secondary/accent) y **semánticos**
    (critical/success/warning/genero) porque la decisión de producto es que el
    tenant pueda personalizar ambos (ver Reglas de entrega · alcance de color).
    """

    model_config = ConfigDict(extra="forbid")

    # ── Marca ────────────────────────────────────────────────────────────────
    primary: str = Field("#9F2241", pattern=HEX_RE)
    primary_foreground: str = Field("#FFFFFF", pattern=HEX_RE)
    secondary: str = Field("#2D7A4F", pattern=HEX_RE)
    secondary_foreground: str = Field("#FFFFFF", pattern=HEX_RE)
    accent: str = Field("#BC955C", pattern=HEX_RE)
    accent_foreground: str = Field("#FFFFFF", pattern=HEX_RE)
    # ── Semánticos de estado/criticidad ──────────────────────────────────────
    critical: str = Field("#C03A3A", pattern=HEX_RE)  # alertas / destructive
    critical_foreground: str = Field("#FFFFFF", pattern=HEX_RE)
    success: str = Field("#2D7A4F", pattern=HEX_RE)
    warning: str = Field("#B7791F", pattern=HEX_RE)
    genero: str = Field("#6B2D8E", pattern=HEX_RE)  # transversal de género
    genero_foreground: str = Field("#FFFFFF", pattern=HEX_RE)
    # ── Superficies y texto ──────────────────────────────────────────────────
    background: str = Field("#FAFAFA", pattern=HEX_RE)
    surface: str = Field("#FFFFFF", pattern=HEX_RE)  # card / popover
    foreground: str = Field("#1A1A1A", pattern=HEX_RE)  # texto principal
    muted: str = Field("#F3F3F3", pattern=HEX_RE)
    muted_foreground: str = Field("#555555", pattern=HEX_RE)
    border: str = Field("#E5E5E5", pattern=HEX_RE)


class BrandFont(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Solo letras/dígitos/espacios/guiones: evita inyección al interpolar el
    # nombre en una declaración CSS ``--font-sans: "<sans>", …``.
    sans: str = Field("Inter", pattern=r"^[A-Za-z0-9 _\-]{1,80}$")  # familia UI
    heading: str | None = Field(
        None, pattern=r"^[A-Za-z0-9 _\-]{1,80}$"
    )  # opcional para títulos
    source: FontSource = Field("google", pattern=r"^(google|custom_upload|system)$")
    # URL del woff2 cuando source == custom_upload (ruta en storage).
    custom_url: str | None = Field(None, max_length=300)


class BrandLogos(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full: str | None = Field(None, max_length=300)  # horizontal (login, header)
    mark: str | None = Field(None, max_length=300)  # isotipo / favicon grande
    login: str | None = Field(None, max_length=300)  # variante de acceso
    favicon: str | None = Field(None, max_length=300)


class BrandTokens(BaseModel):
    """Documento completo de tokens de marca (la unidad versionable)."""

    model_config = ConfigDict(extra="forbid")

    color: BrandColors = Field(default_factory=BrandColors)
    radius: str = Field("0.625rem", pattern=RADIUS_RE)
    font: BrandFont = Field(default_factory=BrandFont)
    logo: BrandLogos = Field(default_factory=BrandLogos)


# ── Documentos de API ────────────────────────────────────────────────────────


class BrandRead(BaseModel):
    """Marca **resuelta** del tenant (defaults + escalares + overrides)."""

    tenant_id: str
    version: int
    tokens: BrandTokens
    updated_at: datetime | None = None
    updated_by: str | None = None
    # True si el tenant aún usa el tema base (sin overrides explícitos).
    is_default: bool = False


class _PartialColors(BaseModel):
    """Subconjunto editable de colores (todos opcionales)."""

    model_config = ConfigDict(extra="forbid")

    primary: str | None = Field(None, pattern=HEX_RE)
    primary_foreground: str | None = Field(None, pattern=HEX_RE)
    secondary: str | None = Field(None, pattern=HEX_RE)
    secondary_foreground: str | None = Field(None, pattern=HEX_RE)
    accent: str | None = Field(None, pattern=HEX_RE)
    accent_foreground: str | None = Field(None, pattern=HEX_RE)
    critical: str | None = Field(None, pattern=HEX_RE)
    critical_foreground: str | None = Field(None, pattern=HEX_RE)
    success: str | None = Field(None, pattern=HEX_RE)
    warning: str | None = Field(None, pattern=HEX_RE)
    genero: str | None = Field(None, pattern=HEX_RE)
    genero_foreground: str | None = Field(None, pattern=HEX_RE)
    background: str | None = Field(None, pattern=HEX_RE)
    surface: str | None = Field(None, pattern=HEX_RE)
    foreground: str | None = Field(None, pattern=HEX_RE)
    muted: str | None = Field(None, pattern=HEX_RE)
    muted_foreground: str | None = Field(None, pattern=HEX_RE)
    border: str | None = Field(None, pattern=HEX_RE)


class BrandUpdate(BaseModel):
    """Actualización parcial de marca enviada por el panel (solo lo cambiado)."""

    model_config = ConfigDict(extra="forbid")

    color: _PartialColors | None = None
    radius: str | None = Field(None, pattern=RADIUS_RE)
    font: BrandFont | None = None
    logo: BrandLogos | None = None


class BrandHistoryEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    version: int
    snapshot: BrandTokens
    updated_by: str | None = None
    created_at: datetime


class BrandRevertInput(BaseModel):
    version: int = Field(..., ge=1)


# Token document por defecto (MC). Se usa como base de resolución y para
# "Restablecer al tema base".
DEFAULT_BRAND_TOKENS = BrandTokens()
