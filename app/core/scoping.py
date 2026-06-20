"""Motor de alcance heredado (RBAC por posición en el árbol) · R5 · REQ-17.

El alcance de un usuario = su nodo + **todos sus descendientes**. Se resuelve en
una sola consulta con ``WITH RECURSIVE`` (cierre transitivo on-the-fly), evitando
mantener una closure table en cada edición del árbol.

Tres dimensiones, ortogonales (como ya hace el repo):
  - **nivel** (rol)      → qué puede hacer    → ``app.core.permissions``
  - **nodo** (posición)  → qué ve (sub-árbol) → este módulo
  - **capacidad**        → qué módulos tiene encendidos → ``app.services.org_service``

El aislamiento es a nivel de aplicación (filtros ``WHERE``), igual que el resto
del sistema (no hay RLS de Postgres en este repo). ``admin`` y ``alcalde`` ven
todo su tenant (bypass), consistente con el patrón ``user.role != 'admin'``
usado en los ~14 servicios existentes.
"""

from __future__ import annotations

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.cuadrilla import cuadrilla_especialidades
from app.models.org_nodo import OrgNodo
from app.models.user import User

# Roles que ven todo su tenant (sin restricción de sub-árbol).
_ROLES_GLOBALES = {"admin"}
_NIVELES_GLOBALES = {"alcalde", "dir_general"}

# Nombre del nodo transversal que aloja el desempeño global (REQ-18).
NODO_TRANSVERSAL_GLOBAL = "Administración y Finanzas"


def rbac_heredado_activo() -> bool:
    """¿Está encendida la propagación del RBAC heredado a los módulos (Fase 4)?"""
    return bool(settings.FEATURE_ORGTREE and settings.FEATURE_ORGTREE_RBAC)


async def descendant_node_ids(
    db: AsyncSession, tenant_id: str, root_id: str
) -> list[str]:
    """Ids del sub-árbol que cuelga de ``root_id`` (incluye ``root_id``).

    Cierre transitivo con ``WITH RECURSIVE``; acotado por ``tenant_id`` en cada
    paso para que un árbol nunca cruce tenants.
    """
    sql = text(
        """
        WITH RECURSIVE sub AS (
            SELECT id FROM org_nodos
             WHERE id = :root AND tenant_id = :tenant
            UNION ALL
            SELECT n.id FROM org_nodos n
              JOIN sub ON n.parent_id = sub.id
             WHERE n.tenant_id = :tenant
        )
        SELECT id FROM sub
        """
    )
    result = await db.execute(sql, {"root": root_id, "tenant": tenant_id})
    return [row[0] for row in result.fetchall()]


async def ancestor_node_ids(
    db: AsyncSession, tenant_id: str, node_id: str
) -> list[str]:
    """Ids de ``node_id`` y todos sus ancestros hasta la raíz (Alcalde)."""
    sql = text(
        """
        WITH RECURSIVE anc AS (
            SELECT id, parent_id FROM org_nodos
             WHERE id = :node AND tenant_id = :tenant
            UNION ALL
            SELECT n.id, n.parent_id FROM org_nodos n
              JOIN anc ON n.id = anc.parent_id
             WHERE n.tenant_id = :tenant
        )
        SELECT id FROM anc
        """
    )
    result = await db.execute(sql, {"node": node_id, "tenant": tenant_id})
    return [row[0] for row in result.fetchall()]


def is_global_scope(user: User) -> bool:
    """¿El usuario ve todo su tenant (sin restricción de sub-árbol)?"""
    if user.role in _ROLES_GLOBALES:
        return True
    nodo = getattr(user, "nodo", None)
    return bool(nodo and nodo.nivel in _NIVELES_GLOBALES)


async def user_scope_node_ids(db: AsyncSession, user: User) -> list[str] | None:
    """Alcance del usuario como lista de ids de nodo.

    Devuelve ``None`` cuando el alcance es **todo el tenant** (admin/alcalde/
    director general): el caller no debe filtrar por nodo.
    Devuelve ``[]`` (fail-closed) si un usuario scopeado no tiene nodo asignado:
    no ve nada, en lugar de ver todo.
    """
    if is_global_scope(user):
        return None
    if not user.nodo_id:
        return []
    return await descendant_node_ids(db, user.tenant_id, user.nodo_id)


async def user_scope_cuadrilla_ids(
    db: AsyncSession, user: User
) -> list[str] | None:
    """Cuadrillas reales dentro del sub-árbol del usuario (Fase 4).

    ``None`` => todas las del tenant (alcance global). ``[]`` => ninguna
    (fail-closed). Habilita "un JUD ve solo sus cuadrillas".
    """
    scope = await user_scope_node_ids(db, user)
    if scope is None:
        return None
    if not scope:
        return []
    rows = await db.execute(
        select(OrgNodo.cuadrilla_id).where(
            OrgNodo.id.in_(scope), OrgNodo.cuadrilla_id.is_not(None)
        )
    )
    return [r[0] for r in rows.fetchall() if r[0]]


async def user_scope_categoria_ids(
    db: AsyncSession, user: User
) -> list[str] | None:
    """Categorías (áreas de servicio) alcanzables desde el sub-árbol del usuario.

    Derivadas de las especialidades de las cuadrillas del sub-árbol. ``None`` =>
    todas (alcance global). ``[]`` => ninguna (fail-closed).
    """
    cuadrilla_ids = await user_scope_cuadrilla_ids(db, user)
    if cuadrilla_ids is None:
        return None
    if not cuadrilla_ids:
        return []
    rows = await db.execute(
        select(cuadrilla_especialidades.c.categoria_id)
        .where(cuadrilla_especialidades.c.cuadrilla_id.in_(cuadrilla_ids))
        .distinct()
    )
    return [r[0] for r in rows.fetchall()]


def es_nodo_transversal_global(user: User) -> bool:
    """¿El usuario pertenece al nodo transversal (A&F) que ve el desempeño global?"""
    nodo = getattr(user, "nodo", None)
    return bool(nodo and nodo.nombre == NODO_TRANSVERSAL_GLOBAL)
