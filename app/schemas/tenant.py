from decimal import Decimal

from pydantic import BaseModel, Field


class TenantRead(BaseModel):
    id: str
    nombre: str
    nombre_corto: str
    clave_geo: str
    acronimo: str
    bbox: list[float] | None = None
    center: list[float] | None = None
    polygon_path: str | None = None
    escudo_path: str | None = None
    primario: str
    secundario: str | None = None
    dorado: str | None = None
    poblacion: int
    area_km2: Decimal

    model_config = {"from_attributes": True}


class TenantPublic(BaseModel):
    """Public-facing tenant info (no auth required)."""

    id: str
    nombre: str
    nombre_corto: str
    escudo_path: str | None = None
    primario: str

    model_config = {"from_attributes": True}


class TenantUpdate(BaseModel):
    nombre: str | None = Field(None, max_length=120)
    nombre_corto: str | None = Field(None, max_length=60)
    primario: str | None = Field(None, max_length=7)
    secundario: str | None = Field(None, max_length=7)
    dorado: str | None = Field(None, max_length=7)
