"""Schemas de Configuración operativa del tenant (módulo 13)."""

from pydantic import BaseModel

# SLA por defecto (días) si el tenant no lo ha personalizado.
SLA_DIAS_DEFAULT: dict[str, int] = {"critica": 1, "alta": 3, "media": 7, "baja": 15}


class FlujoAtencion(BaseModel):
    nombre: str
    pasos: list[str] = []


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


class ConfiguracionUpdate(BaseModel):
    titular_nombre: str | None = None
    titular_cargo: str | None = None
    contacto: str | None = None
    sla_dias: dict[str, int] | None = None
    flujos: list[FlujoAtencion] | None = None
    checklists: dict[str, list[str]] | None = None
