"""Modelo de permisos basado en roles (RBAC) para Tu Alcald.IA.

Seis roles operan sobre la plataforma. Cada uno tiene asociado un conjunto de
permisos atómicos (verbo + recurso). Los servicios y routers consultan la matriz
vía :func:`has_permission` o protegen endpoints con la dependency
:func:`require_permission`.

El tenant SIEMPRE se deriva del JWT; los permisos describen QUÉ puede hacer un rol,
no SOBRE QUÉ tenant (eso lo garantiza el filtrado por ``tenant_id`` en cada servicio).
"""

from __future__ import annotations

from enum import StrEnum


class Permission(StrEnum):
    """Permisos atómicos del sistema."""

    REPORTE_VER = "reporte:ver"
    REPORTE_GESTIONAR = "reporte:gestionar"
    OBRA_GESTIONAR = "obra:gestionar"
    USUARIO_GESTIONAR = "usuario:gestionar"
    CONFIG_GESTIONAR = "config:gestionar"
    CUADRILLA_DESPACHAR = "cuadrilla:despachar"
    CAMPO_EJECUTAR = "campo:ejecutar"
    EJECUTIVO_VER = "ejecutivo:ver"


# Roles soportados por la plataforma.
ROLES: tuple[str, ...] = (
    "admin",
    "director_area",
    "supervisor",
    "jefe_cuadrilla",
    "inspector",
    "ciudadano",
)


# ─────────────────────────────────────────────────────────────────────────────
# Matriz rol -> conjunto de permisos.
#
#   admin           Control total de la alcaldía (su tenant).
#   director_area    Gobierna su área: reportes, obras, tablero ejecutivo.
#   supervisor       Coordina la operación: gestiona reportes y despacha cuadrillas.
#   jefe_cuadrilla   Despacha a su cuadrilla y ejecuta/registra trabajo en campo.
#   inspector        Verifica en campo y actualiza el estado de los reportes.
#   ciudadano        Solo consulta sus propios reportes (lectura).
# ─────────────────────────────────────────────────────────────────────────────
ROLE_PERMISSIONS: dict[str, frozenset[Permission]] = {
    "admin": frozenset(
        {
            Permission.REPORTE_VER,
            Permission.REPORTE_GESTIONAR,
            Permission.OBRA_GESTIONAR,
            Permission.USUARIO_GESTIONAR,
            Permission.CONFIG_GESTIONAR,
            Permission.CUADRILLA_DESPACHAR,
            Permission.CAMPO_EJECUTAR,
            Permission.EJECUTIVO_VER,
        }
    ),
    "director_area": frozenset(
        {
            Permission.REPORTE_VER,
            Permission.REPORTE_GESTIONAR,
            Permission.OBRA_GESTIONAR,
            Permission.CUADRILLA_DESPACHAR,
            Permission.EJECUTIVO_VER,
        }
    ),
    "supervisor": frozenset(
        {
            Permission.REPORTE_VER,
            Permission.REPORTE_GESTIONAR,
            Permission.CUADRILLA_DESPACHAR,
            Permission.EJECUTIVO_VER,
        }
    ),
    "jefe_cuadrilla": frozenset(
        {
            Permission.REPORTE_VER,
            Permission.CUADRILLA_DESPACHAR,
            Permission.CAMPO_EJECUTAR,
        }
    ),
    "inspector": frozenset(
        {
            Permission.REPORTE_VER,
            Permission.CAMPO_EJECUTAR,
        }
    ),
    "ciudadano": frozenset(
        {
            Permission.REPORTE_VER,
        }
    ),
}


def has_permission(role: str, perm: Permission | str) -> bool:
    """Devuelve ``True`` si ``role`` tiene el permiso ``perm`` en la matriz."""
    return Permission(perm) in ROLE_PERMISSIONS.get(role, frozenset())


def permissions_for(role: str) -> frozenset[Permission]:
    """Conjunto de permisos asociados a ``role`` (vacío si el rol es desconocido)."""
    return ROLE_PERMISSIONS.get(role, frozenset())
