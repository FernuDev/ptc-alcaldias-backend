"""Router del núcleo organizacional (R5 · REQ-17).

- Lectura del árbol **scopeada al sub-árbol del usuario** (un JUD solo ve su rama,
  verificado en servidor).
- Edición del árbol y de capacidades restringida a Alcalde / Administrador de
  plataforma (rol ``admin``).
- Aplicación de plantillas de onboarding (config, no custom).
"""

from fastapi import APIRouter

from app.core.dependencies import (
    DB,
    Audit,
    BackofficeUser,
    CurrentUser,
    OrgAdminUser,
)
from app.core.scoping import user_scope_node_ids
from app.schemas.org import (
    AplicarPlantillaInput,
    CapacidadRead,
    MiNodoRead,
    NodoCapacidadRead,
    OrgNodoCreate,
    OrgNodoPersonal,
    OrgNodoRead,
    OrgNodoTree,
    OrgNodoUpdate,
    SetCapacidadesInput,
)
from app.services import org_service

router = APIRouter(prefix="/org", tags=["org"])


@router.get("/capacidades", response_model=list[CapacidadRead])
async def list_capacidades(user: CurrentUser, db: DB):
    """Catálogo fijo de capacidades (módulos asignables)."""
    return await org_service.get_capacidades_catalog(db)


@router.get("/mi-nodo", response_model=MiNodoRead)
async def mi_nodo(user: CurrentUser, db: DB):
    """Contexto organizacional del usuario: nodo, nivel, alcance y capacidades."""
    return await org_service.mi_nodo_context(db, user)


@router.get("/arbol", response_model=list[OrgNodoTree])
async def get_arbol(user: BackofficeUser, db: DB):
    """Árbol visible para el usuario = su nodo + descendientes.

    El alcance se resuelve en servidor (cierre transitivo); un JUD no ve otra
    dirección aunque la pida directamente.
    """
    scope = await user_scope_node_ids(db, user)
    return await org_service.get_tree(db, user.tenant_id, scope)


@router.get("/arbol/completo", response_model=list[OrgNodoTree])
async def get_arbol_completo(user: OrgAdminUser, db: DB):
    """Árbol completo del tenant (para el editor de organigrama)."""
    return await org_service.get_tree(db, user.tenant_id, None)


@router.get("/personal", response_model=list[OrgNodoPersonal])
async def get_personal(user: BackofficeUser, db: DB):
    """Jerarquía real de Personal: árbol scopeado + usuarios y cuadrillas por nodo.

    Reemplaza el organigrama cableado de la sección Personal (Fase 3).
    """
    scope = await user_scope_node_ids(db, user)
    return await org_service.personal_tree(db, user.tenant_id, scope)


@router.post("/nodos", response_model=OrgNodoRead, status_code=201)
async def create_nodo(data: OrgNodoCreate, user: BackofficeUser, db: DB, audit: Audit):
    # RBAC heredado: cada usuario crea dentro de su sub-árbol (la raíz, solo admin).
    nodo = await org_service.create_nodo(db, user, data, audit)
    return await org_service.nodo_to_read(db, nodo)


@router.put("/nodos/{nodo_id}", response_model=OrgNodoRead)
async def update_nodo(
    nodo_id: str, data: OrgNodoUpdate, user: BackofficeUser, db: DB, audit: Audit
):
    nodo = await org_service.update_nodo(db, user, nodo_id, data, audit)
    return await org_service.nodo_to_read(db, nodo)


@router.delete("/nodos/{nodo_id}")
async def delete_nodo(nodo_id: str, user: BackofficeUser, db: DB, audit: Audit):
    await org_service.delete_nodo(db, user, nodo_id, audit)
    return {"detail": "Nodo eliminado"}


@router.put(
    "/nodos/{nodo_id}/capacidades", response_model=list[NodoCapacidadRead]
)
async def set_capacidades(
    nodo_id: str,
    data: SetCapacidadesInput,
    user: BackofficeUser,
    db: DB,
    audit: Audit,
):
    return await org_service.set_capacidades(
        db, user, nodo_id, data.capacidades, audit
    )


@router.post("/plantilla", response_model=list[OrgNodoTree])
async def aplicar_plantilla(
    data: AplicarPlantillaInput, user: OrgAdminUser, db: DB, audit: Audit
):
    """Onboarding de una alcaldía = aplicar plantilla + renombrar (cero código)."""
    return await org_service.apply_template(db, user.tenant_id, data, audit, user.id)
