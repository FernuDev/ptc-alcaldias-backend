"""Contexto de permisos del usuario para el Agente Institucional.

El `UsuarioContexto` NUNCA llega desde el body de la petición: se deriva del
usuario autenticado (claims reales del JWT, resueltos contra la BD por
`get_current_user`). Así, el principio "los permisos van antes del modelo" es
real y no falsificable.

El sistema real solo tiene dos roles (`admin`, `director_area`). Aquí se mapean
al modelo conceptual del agente (operador/supervisor/director/administrador).
Los roles operador/supervisor quedan modelados pero inactivos hasta que existan
en la plataforma.
"""

from typing import Literal

from pydantic import BaseModel

from app.models.user import User

RolConceptual = Literal["operador", "supervisor", "director", "administrador"]
AlcanceDatos = Literal["casos_propios", "cuadrilla", "direccion_completa", "global"]
NivelVisibilidad = Literal["publico", "interno", "ejecutivo", "reservado"]


class UsuarioContexto(BaseModel):
    """Alcance efectivo del usuario, derivado de su rol real."""

    id: str
    tenant_id: str
    rol: RolConceptual
    direccion: str | None = None
    alcance_datos: AlcanceDatos
    areas: list[str] = []
    niveles_visibles: list[NivelVisibilidad] = []
    seguridad_reservada: bool = False


# Niveles de conocimiento que cada rol conceptual puede recuperar (sin contar
# el nivel `reservado`, que depende del flag `seguridad_reservada`).
_NIVELES_POR_ROL: dict[RolConceptual, list[NivelVisibilidad]] = {
    "operador": ["publico", "interno"],
    "supervisor": ["publico", "interno"],
    "director": ["publico", "interno"],
    "administrador": ["publico", "interno", "ejecutivo"],
}


def derive_contexto(user: User) -> UsuarioContexto:
    """Construye el contexto de permisos a partir del usuario autenticado."""
    # Mapeo rol real -> rol conceptual + alcance.
    if user.role == "admin":
        rol: RolConceptual = "administrador"
        alcance: AlcanceDatos = "global"
    else:  # director_area (único otro rol existente hoy)
        rol = "director"
        alcance = "direccion_completa"

    # Flag de acceso a información reservada (columna añadida en migración del
    # agente; getattr por compatibilidad si aún no existe).
    seguridad_reservada = bool(getattr(user, "puede_ver_reservado", False))

    niveles: list[NivelVisibilidad] = list(_NIVELES_POR_ROL[rol])
    if seguridad_reservada:
        niveles.append("reservado")

    return UsuarioContexto(
        id=user.id,
        tenant_id=user.tenant_id,
        rol=rol,
        direccion=user.cargo,
        alcance_datos=alcance,
        areas=[a.id for a in user.areas],
        niveles_visibles=niveles,
        seguridad_reservada=seguridad_reservada,
    )
