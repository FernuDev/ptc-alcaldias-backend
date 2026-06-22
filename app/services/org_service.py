"""Servicio del núcleo organizacional (R5 · REQ-17).

Árbol configurable como dato + capacidades por nodo + alcance heredado. Sigue las
convenciones del repo: filtrado por ``tenant_id`` (derivado del JWT, nunca del
body), auditoría vía ``AuditLogger`` (como ``tenant_service``), ids string-uuid.
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditLogger
from app.core.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.core.scoping import (
    ancestor_node_ids,
    descendant_node_ids,
    is_global_scope,
    user_scope_node_ids,
)
from app.models.cuadrilla import Cuadrilla
from app.models.org_nodo import (
    NIVELES_CAMPO,
    Capacidad,
    OrgNodo,
    nodo_capacidades,
)
from app.models.user import User
from app.schemas.org import (
    AplicarPlantillaInput,
    MiNodoRead,
    NodoCapacidadInput,
    NodoCapacidadRead,
    OrgNodoCreate,
    OrgNodoPersonal,
    OrgNodoRead,
    OrgNodoTree,
    OrgNodoUpdate,
    PersonalCuadrilla,
    PersonalIntegrante,
    PersonalUsuario,
)

# ── Catálogo fijo de capacidades ─────────────────────────────────────────────
CAPACIDADES_SEED: list[tuple[str, str]] = [
    ("proyectos", "Proyectos"),
    ("obras", "Obras"),
    ("cuadrillas", "Cuadrillas"),
    ("tramites", "Trámites"),
    ("recaudacion", "Recaudación"),
]

# ── Reglas de jerarquía (qué nivel puede colgar de qué nivel) ────────────────
# Impide estructuras imposibles (p.ej. una cuadrilla colgando del Alcalde).
NIVEL_PADRES_VALIDOS: dict[str, set[str]] = {
    "alcalde": set(),  # raíz
    "dir_general": {"alcalde"},
    "dir_area": {"alcalde", "dir_general"},
    "subdireccion": {"dir_area", "dir_general"},
    "jud": {"dir_area", "subdireccion"},
    "lcp": {"jud", "subdireccion", "coordinacion"},
    "enlace": {"lcp", "jud", "subdireccion", "coordinacion"},
    "coordinacion": {"jud", "subdireccion", "dir_area", "lcp"},
    "jefe_cuadrilla": {"coordinacion", "jud", "lcp"},
    "integrante": {"jefe_cuadrilla", "coordinacion"},
    "operativo": {"enlace", "jefe_cuadrilla", "coordinacion", "lcp"},
}


# ─────────────────────────────────────────────────────────────────────────────
# Capacidades
# ─────────────────────────────────────────────────────────────────────────────
async def ensure_capacidades_catalog(db: AsyncSession) -> None:
    """Siembra el catálogo fijo de capacidades de forma idempotente."""
    existing = {c.codigo for c in (await db.execute(select(Capacidad))).scalars()}
    for orden, (codigo, nombre) in enumerate(CAPACIDADES_SEED):
        if codigo not in existing:
            db.add(Capacidad(codigo=codigo, nombre=nombre, orden=orden))
    await db.flush()


async def get_capacidades_catalog(db: AsyncSession) -> list[Capacidad]:
    result = await db.execute(select(Capacidad).order_by(Capacidad.orden))
    return list(result.scalars().all())


async def _caps_by_nodo(
    db: AsyncSession, nodo_ids: list[str]
) -> dict[str, list[NodoCapacidadRead]]:
    """Mapa nodo_id -> capacidades encendidas (con nombre y nivel_uso)."""
    if not nodo_ids:
        return {}
    nombres = {c.codigo: c.nombre for c in await get_capacidades_catalog(db)}
    rows = await db.execute(
        select(
            nodo_capacidades.c.nodo_id,
            nodo_capacidades.c.capacidad,
            nodo_capacidades.c.nivel_uso,
        ).where(nodo_capacidades.c.nodo_id.in_(nodo_ids))
    )
    out: dict[str, list[NodoCapacidadRead]] = {}
    for nodo_id, capacidad, nivel_uso in rows.fetchall():
        out.setdefault(nodo_id, []).append(
            NodoCapacidadRead(
                capacidad=capacidad,
                nombre=nombres.get(capacidad, capacidad),
                nivel_uso=nivel_uso,
            )
        )
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Lectura del árbol (con alcance)
# ─────────────────────────────────────────────────────────────────────────────
async def get_nodo(db: AsyncSession, nodo_id: str, tenant_id: str) -> OrgNodo:
    result = await db.execute(
        select(OrgNodo).where(
            OrgNodo.id == nodo_id, OrgNodo.tenant_id == tenant_id
        )
    )
    nodo = result.scalar_one_or_none()
    if nodo is None:
        raise NotFoundError("Nodo", nodo_id)
    return nodo


async def list_nodos(
    db: AsyncSession, tenant_id: str, scope_ids: list[str] | None
) -> list[OrgNodo]:
    stmt = select(OrgNodo).where(OrgNodo.tenant_id == tenant_id)
    if scope_ids is not None:
        # Fail-closed: scope vacío => sin nodos.
        stmt = stmt.where(OrgNodo.id.in_(scope_ids))
    stmt = stmt.order_by(OrgNodo.orden, OrgNodo.nombre)
    result = await db.execute(stmt)
    return list(result.scalars().all())


def _to_read(nodo: OrgNodo, caps: list[NodoCapacidadRead]) -> OrgNodoRead:
    return OrgNodoRead(
        id=nodo.id,
        tenant_id=nodo.tenant_id,
        parent_id=nodo.parent_id,
        nivel=nodo.nivel,
        tipo=nodo.tipo,
        nombre=nodo.nombre,
        orden=nodo.orden,
        activo=nodo.activo,
        cuadrilla_id=nodo.cuadrilla_id,
        capacidades=caps,
    )


async def nodo_to_read(db: AsyncSession, nodo: OrgNodo) -> OrgNodoRead:
    """Serializa un nodo incluyendo sus capacidades encendidas."""
    caps = (await _caps_by_nodo(db, [nodo.id])).get(nodo.id, [])
    return _to_read(nodo, caps)


async def get_tree(
    db: AsyncSession, tenant_id: str, scope_ids: list[str] | None
) -> list[OrgNodoTree]:
    """Árbol (lista de raíces visibles). ``scope_ids=None`` => todo el tenant.

    Cuando hay alcance, la(s) raíz(es) del árbol devuelto son los nodos del set
    cuyo padre NO está en el set (el sub-árbol del usuario), garantizando que un
    JUD solo ve su rama — verificable en servidor, no por filtro de cliente.
    """
    nodos = await list_nodos(db, tenant_id, scope_ids)
    ids = [n.id for n in nodos]
    caps_map = await _caps_by_nodo(db, ids)
    id_set = set(ids)

    by_id: dict[str, OrgNodoTree] = {}
    for n in nodos:
        read = _to_read(n, caps_map.get(n.id, []))
        by_id[n.id] = OrgNodoTree(**read.model_dump(), children=[])

    roots: list[OrgNodoTree] = []
    for n in nodos:
        node_t = by_id[n.id]
        if n.parent_id and n.parent_id in id_set:
            by_id[n.parent_id].children.append(node_t)
        else:
            roots.append(node_t)
    return roots


# ─────────────────────────────────────────────────────────────────────────────
# Vista de Personal (Fase 3): árbol enriquecido con usuarios y cuadrillas
# ─────────────────────────────────────────────────────────────────────────────
async def personal_tree(
    db: AsyncSession, tenant_id: str, scope_ids: list[str] | None
) -> list[OrgNodoPersonal]:
    """Árbol scopeado con el personal (usuarios por nodo) y las cuadrillas
    reales (con integrantes) recolgadas de su nodo correcto.

    Reemplaza el organigrama 'cableado' por la jerarquía real: Dirección →
    Subdirección/JUD → Coordinación → Cuadrilla → Integrantes.
    """
    nodos = await list_nodos(db, tenant_id, scope_ids)
    ids = [n.id for n in nodos]
    id_set = set(ids)
    caps_map = await _caps_by_nodo(db, ids)

    # Usuarios por nodo (reales, mismo tenant).
    users_rows = (
        await db.execute(
            select(User).where(
                User.tenant_id == tenant_id, User.nodo_id.in_(ids or [""])
            )
        )
    ).scalars().all()
    users_by_nodo: dict[str, list[PersonalUsuario]] = {}
    for u in users_rows:
        nodo = getattr(u, "nodo", None)
        users_by_nodo.setdefault(u.nodo_id, []).append(
            PersonalUsuario(
                id=u.id,
                nombre=u.nombre,
                iniciales=u.iniciales,
                cargo=u.cargo,
                role=u.role,
                rol_nivel=nodo.nivel if nodo else None,
                es_campo=bool(getattr(u, "es_campo", False)),
                avatar_tone=u.avatar_tone,
            )
        )

    # Cuadrillas reales enlazadas a nodos del árbol (cuadrilla_id).
    cuadrilla_ids = [n.cuadrilla_id for n in nodos if n.cuadrilla_id]
    cuadrillas_by_id: dict[str, PersonalCuadrilla] = {}
    if cuadrilla_ids:
        crows = (
            await db.execute(
                select(Cuadrilla).where(Cuadrilla.id.in_(cuadrilla_ids))
            )
        ).scalars().all()
        for c in crows:
            cuadrillas_by_id[c.id] = PersonalCuadrilla(
                id=c.id,
                nombre=c.nombre,
                integrantes=[
                    PersonalIntegrante(
                        id=m.id,
                        nombre=m.nombre,
                        rol_campo=m.rol_campo,
                        telefono=m.telefono,
                        activo=m.activo,
                    )
                    for m in sorted(
                        c.miembros, key=lambda m: (m.rol_campo != "jefe", m.nombre)
                    )
                ],
            )

    by_id: dict[str, OrgNodoPersonal] = {}
    for n in nodos:
        read = _to_read(n, caps_map.get(n.id, []))
        by_id[n.id] = OrgNodoPersonal(
            **read.model_dump(),
            usuarios=users_by_nodo.get(n.id, []),
            cuadrilla=cuadrillas_by_id.get(n.cuadrilla_id) if n.cuadrilla_id else None,
            children=[],
        )

    roots: list[OrgNodoPersonal] = []
    for n in nodos:
        node_t = by_id[n.id]
        if n.parent_id and n.parent_id in id_set:
            by_id[n.parent_id].children.append(node_t)
        else:
            roots.append(node_t)
    return roots


# ─────────────────────────────────────────────────────────────────────────────
# Validaciones de jerarquía
# ─────────────────────────────────────────────────────────────────────────────
async def _validate_parent(
    db: AsyncSession,
    tenant_id: str,
    nivel: str,
    parent_id: str | None,
    *,
    moving_node_id: str | None = None,
) -> None:
    padres_validos = NIVEL_PADRES_VALIDOS.get(nivel, set())

    if parent_id is None:
        # Solo el Alcalde (raíz) puede no tener padre, y solo puede haber una raíz.
        if nivel != "alcalde":
            raise ValidationError(
                f"Un nodo de nivel '{nivel}' debe colgar de un nodo padre"
            )
        existing_root = await db.execute(
            select(OrgNodo.id).where(
                OrgNodo.tenant_id == tenant_id, OrgNodo.parent_id.is_(None)
            )
        )
        root_ids = [r[0] for r in existing_root.fetchall() if r[0] != moving_node_id]
        if root_ids:
            raise ConflictError("Ya existe una raíz (Alcalde) en este tenant")
        return

    # parent_id presente: debe existir en el tenant y respetar la jerarquía.
    parent = await get_nodo(db, parent_id, tenant_id)
    if padres_validos and parent.nivel not in padres_validos:
        raise ValidationError(
            f"Un nodo '{nivel}' no puede colgar de un '{parent.nivel}' "
            f"(padres válidos: {', '.join(sorted(padres_validos)) or 'ninguno'})"
        )

    # Evitar ciclos: el nuevo padre no puede ser el propio nodo ni un descendiente.
    if moving_node_id is not None:
        descendientes = await descendant_node_ids(db, tenant_id, moving_node_id)
        if parent_id in descendientes:
            raise ValidationError(
                "No se puede mover un nodo dentro de su propio sub-árbol (ciclo)"
            )


# ─────────────────────────────────────────────────────────────────────────────
# Alcance de edición (RBAC heredado): cada usuario edita su sub-árbol.
# ─────────────────────────────────────────────────────────────────────────────
async def _assert_scope(
    db: AsyncSession, user: User, nodo_id: str, *, scope: set[str] | None = None
) -> None:
    """Falla si ``nodo_id`` no está dentro del alcance (sub-árbol) del usuario.

    El Alcalde / Administrador de plataforma (alcance global) edita todo el
    tenant; un director edita su dirección y lo que cuelga de ella; etc.
    """
    if is_global_scope(user):
        return
    if scope is None:
        scope = set(await user_scope_node_ids(db, user) or [])
    if nodo_id not in scope:
        raise ForbiddenError("Ese nodo está fuera de tu alcance en el organigrama")


# ─────────────────────────────────────────────────────────────────────────────
# CRUD del árbol
# ─────────────────────────────────────────────────────────────────────────────
async def create_nodo(
    db: AsyncSession,
    user: User,
    data: OrgNodoCreate,
    audit: AuditLogger,
) -> OrgNodo:
    tenant_id = user.tenant_id
    if data.parent_id is None:
        # Crear la raíz (Alcalde) solo el Alcalde / Administrador de plataforma.
        if not is_global_scope(user):
            raise ForbiddenError(
                "Solo el Alcalde / Administrador de plataforma puede crear la raíz"
            )
    else:
        await _assert_scope(db, user, data.parent_id)
    await _validate_parent(db, tenant_id, data.nivel, data.parent_id)

    nodo = OrgNodo(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        parent_id=data.parent_id,
        nivel=data.nivel,
        tipo=data.tipo,
        nombre=data.nombre.strip(),
        orden=data.orden,
        cuadrilla_id=data.cuadrilla_id,
    )
    db.add(nodo)
    await db.flush()

    if data.capacidades:
        await _set_capacidades(db, nodo.id, data.capacidades)

    await audit.log(
        action="create",
        user_id=user.id,
        tenant_id=tenant_id,
        entity_type="org_nodo",
        entity_id=nodo.id,
        extra={"nivel": nodo.nivel, "nombre": nodo.nombre},
    )
    return nodo


async def update_nodo(
    db: AsyncSession,
    user: User,
    nodo_id: str,
    data: OrgNodoUpdate,
    audit: AuditLogger,
) -> OrgNodo:
    tenant_id = user.tenant_id
    await _assert_scope(db, user, nodo_id)
    if data.parent_id is not None:
        # Mover dentro del alcance: el nuevo padre también debe estar en alcance.
        await _assert_scope(db, user, data.parent_id)
    nodo = await get_nodo(db, nodo_id, tenant_id)
    old = {
        "nombre": nodo.nombre,
        "nivel": nodo.nivel,
        "tipo": nodo.tipo,
        "parent_id": nodo.parent_id,
        "orden": nodo.orden,
        "activo": nodo.activo,
    }

    nuevo_nivel = data.nivel if data.nivel is not None else nodo.nivel
    # Si cambia el padre o el nivel, revalidar la jerarquía.
    if data.parent_id is not None or data.nivel is not None:
        nuevo_parent = data.parent_id if data.parent_id is not None else nodo.parent_id
        await _validate_parent(
            db, tenant_id, nuevo_nivel, nuevo_parent, moving_node_id=nodo.id
        )
        nodo.parent_id = nuevo_parent

    if data.nombre is not None:
        nodo.nombre = data.nombre.strip()
    if data.nivel is not None:
        nodo.nivel = data.nivel
    if data.tipo is not None:
        nodo.tipo = data.tipo
    if data.orden is not None:
        nodo.orden = data.orden
    if data.activo is not None:
        nodo.activo = data.activo
    if data.cuadrilla_id is not None:
        nodo.cuadrilla_id = data.cuadrilla_id or None

    new = {
        "nombre": nodo.nombre,
        "nivel": nodo.nivel,
        "tipo": nodo.tipo,
        "parent_id": nodo.parent_id,
        "orden": nodo.orden,
        "activo": nodo.activo,
    }
    from app.core.audit import compute_changes

    await audit.log(
        action="update",
        user_id=user.id,
        tenant_id=tenant_id,
        entity_type="org_nodo",
        entity_id=nodo.id,
        changes=compute_changes(old, new),
    )
    return nodo


async def delete_nodo(
    db: AsyncSession,
    user: User,
    nodo_id: str,
    audit: AuditLogger,
) -> None:
    tenant_id = user.tenant_id
    await _assert_scope(db, user, nodo_id)
    nodo = await get_nodo(db, nodo_id, tenant_id)  # noqa: F841 (valida tenant)
    # Desvincular usuarios del sub-árbol (FK ON DELETE SET NULL ya lo hace en BD,
    # pero lo registramos para trazabilidad y para que la sesión cargada quede limpia).
    descendientes = await descendant_node_ids(db, tenant_id, nodo_id)
    await db.execute(delete(OrgNodo).where(OrgNodo.id == nodo_id))  # cascada por FK
    await audit.log(
        action="delete",
        user_id=user.id,
        tenant_id=tenant_id,
        entity_type="org_nodo",
        entity_id=nodo_id,
        extra={"sub_arbol": len(descendientes)},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Capacidades por nodo
# ─────────────────────────────────────────────────────────────────────────────
async def _set_capacidades(
    db: AsyncSession, nodo_id: str, caps: list[NodoCapacidadInput]
) -> None:
    """Reemplaza el set de capacidades del nodo (valida contra el catálogo)."""
    validas = {c.codigo for c in await get_capacidades_catalog(db)}
    for c in caps:
        if c.capacidad not in validas:
            raise ValidationError(f"Capacidad desconocida: {c.capacidad}")
    await db.execute(
        delete(nodo_capacidades).where(nodo_capacidades.c.nodo_id == nodo_id)
    )
    if caps:
        await db.execute(
            insert(nodo_capacidades),
            [
                {"nodo_id": nodo_id, "capacidad": c.capacidad, "nivel_uso": c.nivel_uso}
                for c in caps
            ],
        )


async def set_capacidades(
    db: AsyncSession,
    user: User,
    nodo_id: str,
    caps: list[NodoCapacidadInput],
    audit: AuditLogger,
) -> list[NodoCapacidadRead]:
    tenant_id = user.tenant_id
    await _assert_scope(db, user, nodo_id)
    await get_nodo(db, nodo_id, tenant_id)  # valida tenant
    await _set_capacidades(db, nodo_id, caps)
    await db.flush()
    await audit.log(
        action="update",
        user_id=user.id,
        tenant_id=tenant_id,
        entity_type="nodo_capacidad",
        entity_id=nodo_id,
        extra={"capacidades": [c.capacidad for c in caps]},
    )
    return (await _caps_by_nodo(db, [nodo_id])).get(nodo_id, [])


# ─────────────────────────────────────────────────────────────────────────────
# Contexto organizacional del usuario
# ─────────────────────────────────────────────────────────────────────────────
async def mi_nodo_context(db: AsyncSession, user: User) -> MiNodoRead:
    scope = await user_scope_node_ids(db, user)
    nodo = getattr(user, "nodo", None)
    caps: list[NodoCapacidadRead] = []
    if user.nodo_id:
        caps = (await _caps_by_nodo(db, [user.nodo_id])).get(user.nodo_id, [])
    return MiNodoRead(
        nodo_id=user.nodo_id,
        nodo_nombre=nodo.nombre if nodo else None,
        rol_nivel=nodo.nivel if nodo else None,
        es_campo=bool(getattr(user, "es_campo", False)),
        alcance_global=is_global_scope(user),
        sub_arbol_ids=scope or [],
        capacidades=caps,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Plantillas de onboarding (config, no custom)
# ─────────────────────────────────────────────────────────────────────────────
# Matriz de capacidades por defecto (Briefing R5 · Fase 2).
_DIRECCIONES_CDMX: list[dict] = [
    {
        "nombre": "Jurídico y de Gobierno",
        "caps": {"proyectos": "usa", "cuadrillas": "central", "tramites": "usa"},
    },
    {
        "nombre": "Obras y Desarrollo Urbano",
        "caps": {
            "proyectos": "usa",
            "obras": "central",
            "cuadrillas": "usa",
            "tramites": "usa",
        },
    },
    {
        "nombre": "Servicios Urbanos",
        "caps": {"proyectos": "usa", "cuadrillas": "central"},
        "juds": [
            "Agua y Drenaje",
            "Alumbrado Público",
            "Limpia",
            "Áreas Verdes",
        ],
    },
    {
        "nombre": "Desarrollo y Fomento Económico",
        "caps": {"proyectos": "usa", "tramites": "usa", "recaudacion": "parcial"},
    },
    {
        "nombre": "Seguridad Ciudadana y Movilidad",
        "caps": {"proyectos": "usa", "cuadrillas": "usa"},
    },
    {
        "nombre": "Igualdad, Salud y Poblaciones",
        "caps": {"proyectos": "usa", "cuadrillas": "usa"},
    },
    {
        "nombre": "Bienestar Social",
        "caps": {"proyectos": "central", "cuadrillas": "usa", "recaudacion": "parcial"},
    },
    {
        "nombre": "Administración y Finanzas",
        "caps": {"proyectos": "usa", "recaudacion": "central"},
    },
]


async def _insert_template_nodo(
    db: AsyncSession,
    tenant_id: str,
    *,
    parent_id: str | None,
    nivel: str,
    tipo: str,
    nombre: str,
    orden: int,
    caps: dict[str, str] | None = None,
) -> OrgNodo:
    nodo = OrgNodo(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        parent_id=parent_id,
        nivel=nivel,
        tipo=tipo,
        nombre=nombre,
        orden=orden,
    )
    db.add(nodo)
    await db.flush()
    if caps:
        await db.execute(
            insert(nodo_capacidades),
            [
                {"nodo_id": nodo.id, "capacidad": cod, "nivel_uso": niv}
                for cod, niv in caps.items()
            ],
        )
    return nodo


async def apply_template(
    db: AsyncSession,
    tenant_id: str,
    data: AplicarPlantillaInput,
    audit: AuditLogger,
    actor_id: str,
) -> list[OrgNodoTree]:
    """Aplica una plantilla de onboarding. Onboarding = plantilla + renombrar."""
    await ensure_capacidades_catalog(db)

    existing = await db.execute(
        select(OrgNodo.id).where(OrgNodo.tenant_id == tenant_id).limit(1)
    )
    if existing.first() is not None:
        if not data.reset:
            raise ConflictError(
                "El tenant ya tiene un organigrama. Usa reset=true para reemplazarlo."
            )
        await db.execute(delete(OrgNodo).where(OrgNodo.tenant_id == tenant_id))
        await db.flush()

    con_dir_general = data.plantilla == "cdmx_estandar"

    alcalde = await _insert_template_nodo(
        db, tenant_id, parent_id=None, nivel="alcalde", tipo="direccion",
        nombre="Alcalde", orden=0,
    )

    # ADQ-02 · REQ-17: las 8 grandes SON Direcciones Generales y cuelgan directo
    # del Alcalde. No hay un nodo contenedor "Dirección General" intermedio. En
    # la plantilla genérica de municipio se usa dir_area como raíz operativa.
    nivel_direccion = "dir_general" if con_dir_general else "dir_area"
    rama_demo_hecha = False

    for i, d in enumerate(_DIRECCIONES_CDMX):
        direccion = await _insert_template_nodo(
            db, tenant_id, parent_id=alcalde.id, nivel=nivel_direccion,
            tipo="direccion", nombre=d["nombre"], orden=i, caps=d.get("caps"),
        )
        juds = d.get("juds", [])
        if not juds:
            continue

        # Regla de jerarquía: jud ∈ {dir_area, subdireccion}. En cdmx_estandar la
        # dirección es una Dirección General, así que las JUD cuelgan de una
        # Dirección de Área intermedia (ADQ-02). En municipio_comun la dirección
        # ya es dir_area: las JUD cuelgan directo de ella (sin intermedio, para
        # no anidar dir_area dentro de dir_area).
        if con_dir_general:
            area = await _insert_template_nodo(
                db, tenant_id, parent_id=direccion.id, nivel="dir_area",
                tipo="direccion", nombre=f"Dirección de Área · {d['nombre']}", orden=0,
            )
            base_parent = area.id
        else:
            base_parent = direccion.id
        for j, jud_nombre in enumerate(juds):
            jud_parent = base_parent
            # En la primera JUD de la plantilla CDMX se intercala además una
            # Subdirección, para demostrar la cadena completa de 8 niveles:
            # Alcalde → DG → Dir. de Área → Subdirección → JUD → Coordinación →
            # Cuadrilla.
            if j == 0 and con_dir_general and not rama_demo_hecha:
                sub = await _insert_template_nodo(
                    db, tenant_id, parent_id=base_parent, nivel="subdireccion",
                    tipo="subdireccion", nombre="Subdirección Operativa", orden=0,
                )
                jud_parent = sub.id
                rama_demo_hecha = True
            jud = await _insert_template_nodo(
                db, tenant_id, parent_id=jud_parent, nivel="jud", tipo="unidad",
                nombre=f"JUD {jud_nombre}", orden=j, caps={"cuadrillas": "usa"},
            )
            # La primera JUD instancia la rama hasta cuadrilla.
            if j == 0:
                coord = await _insert_template_nodo(
                    db, tenant_id, parent_id=jud.id, nivel="coordinacion",
                    tipo="unidad", nombre="Coordinación de Cuadrillas", orden=0,
                )
                await _insert_template_nodo(
                    db, tenant_id, parent_id=coord.id, nivel="jefe_cuadrilla",
                    tipo="cuadrilla", nombre=f"Cuadrilla {jud_nombre} 1", orden=0,
                )

    await db.flush()
    await audit.log(
        action="apply_template",
        user_id=actor_id,
        tenant_id=tenant_id,
        entity_type="org_arbol",
        entity_id=tenant_id,
        extra={"plantilla": data.plantilla, "reset": data.reset},
    )
    return await get_tree(db, tenant_id, None)
