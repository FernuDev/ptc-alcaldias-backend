"""Schemas de Configuración operativa del tenant (módulo 13)."""

from pydantic import BaseModel, Field

# SLA por defecto (días) si el tenant no lo ha personalizado.
SLA_DIAS_DEFAULT: dict[str, int] = {"critica": 1, "alta": 3, "media": 7, "baja": 15}

# Parámetros por defecto del expediente de zona (clustering espacio-temporal).
ZONA_PARAMS_DEFAULT: dict[str, int] = {"umbral": 8, "ventana_dias": 365, "radio_m": 300}


class FlujoAtencion(BaseModel):
    nombre: str
    pasos: list[str] = []


class ZonaParams(BaseModel):
    """Parámetros del clustering del expediente de zona (REQ-09)."""

    umbral: int = Field(8, ge=2, le=50)  # mínimo de reportes por zona
    ventana_dias: int = Field(365, ge=7, le=730)  # ventana temporal
    radio_m: int = Field(300, ge=50, le=3000)  # radio de proximidad (metros)


# ── Almacenamiento documental (REQ-04) ───────────────────────────────────────
STORAGE_SCHEME_DEFAULT = "nube_gestionada"
_STORAGE_SCHEME_RE = r"^(nube_gestionada|conector_nas|subarrendamiento_dedicado)$"


class StorageNasConfig(BaseModel):
    """Conexión a un NAS/almacenamiento propio del cliente (esquema conector_nas).

    No contiene credenciales en claro: ``credencial_configurada`` sólo marca que
    el secreto fue capturado vía el mecanismo de secretos (la prueba de conexión
    recibe la credencial de forma transitoria, nunca se persiste)."""

    tipo: str = Field("s3", pattern=r"^(s3|smb|nfs)$")  # S3-compatible | SMB | NFS
    host: str | None = None
    endpoint: str | None = None
    estado: str = Field("sin_probar", pattern=r"^(sin_probar|ok|error)$")
    credencial_configurada: bool = False


class TestStorageInput(BaseModel):
    tipo: str = Field("s3", pattern=r"^(s3|smb|nfs)$")
    host: str | None = None
    endpoint: str | None = None
    # Credenciales transitorias: se usan SÓLO para la prueba, no se persisten.
    usuario: str | None = None
    secreto: str | None = None


class TestStorageResult(BaseModel):
    ok: bool
    latency_ms: int
    message: str


class ConfiguracionRead(BaseModel):
    tenant_id: str
    nombre: str
    nombre_corto: str
    acronimo: str
    titular_nombre: str | None = None
    titular_cargo: str | None = None
    contacto: str | None = None
    sla_dias: dict[str, int]
    flujos: list[FlujoAtencion]
    checklists: dict[str, list[str]]
    zona_params: ZonaParams
    storage_scheme: str
    storage_config: StorageNasConfig | None = None


class ConfiguracionUpdate(BaseModel):
    titular_nombre: str | None = None
    titular_cargo: str | None = None
    contacto: str | None = None
    sla_dias: dict[str, int] | None = None
    flujos: list[FlujoAtencion] | None = None
    checklists: dict[str, list[str]] | None = None
    zona_params: ZonaParams | None = None
    storage_scheme: str | None = Field(None, pattern=_STORAGE_SCHEME_RE)
    storage_config: StorageNasConfig | None = None
