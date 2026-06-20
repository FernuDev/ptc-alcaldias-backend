"""Schemas del núcleo organizacional (R5 · REQ-17)."""

from __future__ import annotations

from pydantic import BaseModel, Field

# Validación por patrón (el repo usa String + comentario, no enums de BD).
_NIVEL_PATTERN = (
    r"^(alcalde|dir_general|dir_area|subdireccion|jud|lcp|enlace|"
    r"coordinacion|jefe_cuadrilla|integrante|operativo)$"
)
_TIPO_PATTERN = r"^(direccion|subdireccion|unidad|cuadrilla)$"
_NIVEL_USO_PATTERN = r"^(central|usa|parcial)$"


class CapacidadRead(BaseModel):
    codigo: str
    nombre: str
    orden: int = 0
    model_config = {"from_attributes": True}


class NodoCapacidadRead(BaseModel):
    capacidad: str
    nombre: str
    nivel_uso: str  # central | usa | parcial


class NodoCapacidadInput(BaseModel):
    capacidad: str = Field(max_length=30)
    nivel_uso: str = Field(default="usa", pattern=_NIVEL_USO_PATTERN)


class SetCapacidadesInput(BaseModel):
    """Reemplaza el set de capacidades encendidas de un nodo."""

    capacidades: list[NodoCapacidadInput] = []


class OrgNodoRead(BaseModel):
    id: str
    tenant_id: str
    parent_id: str | None = None
    nivel: str
    tipo: str
    nombre: str
    orden: int = 0
    activo: bool = True
    cuadrilla_id: str | None = None
    capacidades: list[NodoCapacidadRead] = []
    model_config = {"from_attributes": True}


class OrgNodoTree(OrgNodoRead):
    children: list["OrgNodoTree"] = []


class OrgNodoCreate(BaseModel):
    parent_id: str | None = Field(None, max_length=40)
    nivel: str = Field(pattern=_NIVEL_PATTERN)
    tipo: str = Field(pattern=_TIPO_PATTERN)
    nombre: str = Field(min_length=1, max_length=160)
    orden: int = 0
    cuadrilla_id: str | None = Field(None, max_length=10)
    capacidades: list[NodoCapacidadInput] = []


class OrgNodoUpdate(BaseModel):
    nombre: str | None = Field(None, min_length=1, max_length=160)
    nivel: str | None = Field(None, pattern=_NIVEL_PATTERN)
    tipo: str | None = Field(None, pattern=_TIPO_PATTERN)
    orden: int | None = None
    activo: bool | None = None
    parent_id: str | None = Field(None, max_length=40)  # mover de padre
    cuadrilla_id: str | None = Field(None, max_length=10)


class AplicarPlantillaInput(BaseModel):
    plantilla: str = Field(pattern=r"^(cdmx_estandar|municipio_comun)$")
    # Si true, borra el árbol existente del tenant antes de aplicar.
    reset: bool = False


class PersonalUsuario(BaseModel):
    id: str
    nombre: str
    iniciales: str
    cargo: str
    role: str
    rol_nivel: str | None = None
    es_campo: bool = False
    avatar_tone: str | None = None


class PersonalIntegrante(BaseModel):
    id: str
    nombre: str
    rol_campo: str  # jefe | integrante
    telefono: str | None = None
    activo: bool = True


class PersonalCuadrilla(BaseModel):
    id: str
    nombre: str
    integrantes: list[PersonalIntegrante] = []


class OrgNodoPersonal(OrgNodoRead):
    """Nodo enriquecido para la vista de Personal (Fase 3)."""

    usuarios: list[PersonalUsuario] = []
    cuadrilla: PersonalCuadrilla | None = None
    children: list["OrgNodoPersonal"] = []


class MiNodoRead(BaseModel):
    """Contexto organizacional del usuario autenticado."""

    nodo_id: str | None = None
    nodo_nombre: str | None = None
    rol_nivel: str | None = None  # derivado del nivel del nodo
    es_campo: bool = False
    alcance_global: bool = False  # ve todo el tenant (admin/alcalde)
    sub_arbol_ids: list[str] = []  # nodos visibles (vacío si alcance global)
    capacidades: list[NodoCapacidadRead] = []  # capacidades efectivas


OrgNodoTree.model_rebuild()
OrgNodoPersonal.model_rebuild()
