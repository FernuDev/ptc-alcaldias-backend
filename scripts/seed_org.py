"""Seed del núcleo organizacional (R5 · Fase 1).

Idempotente. Para cada tenant existente:
  1. Siembra el catálogo fijo de capacidades.
  2. Aplica la plantilla "Alcaldía CDMX estándar" si el tenant aún no tiene árbol.
  3. Asigna los usuarios demo a nodos del árbol y marca es_campo.

Ejecutable de forma autónoma:
    python scripts/seed_org.py
También se invoca desde scripts/seed.py (pipeline canónico).
"""

import asyncio
import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.audit import AuditLogger
from app.core.config import settings
from app.models.cuadrilla import Cuadrilla, Integrante, cuadrilla_especialidades
from app.models.org_nodo import NIVELES_CAMPO, OrgNodo
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.org import AplicarPlantillaInput
from app.services import org_service

# Mapeo (sufijo de id de usuario) -> (nombre de nodo destino) por tenant.
# Demuestra los criterios de aceptación de la Fase 1:
#   - un director de "Servicios Urbanos" ve sus JUDs (sub-árbol);
#   - un "JUD Agua y Drenaje" ve solo su rama (no ve Alumbrado ni Obras);
#   - el jefe de cuadrilla es es_campo=True (rechazado del backoffice).
ASIGNACIONES: dict[str, str] = {
    "admin": "Alcalde",
    "dir-obras": "Obras y Desarrollo Urbano",
    "dir-limpia": "Servicios Urbanos",
    "dir-agua": "JUD Agua y Drenaje",
    "dir-alumbrado": "JUD Alumbrado Público",
    "dir-parques": "JUD Áreas Verdes",
    "dir-seguridad": "Seguridad Ciudadana y Movilidad",
    "supervisor": "Administración y Finanzas",
    "inspector": "JUD Limpia",
    # "jefe-cuadrilla" se asigna a su cuadrilla real en link_cuadrillas().
}

# Fase 3: cada especialidad de cuadrilla cuelga de la JUD/dirección correcta.
# (categoria de servicio) -> (nombre de la dirección padre, nombre de la JUD)
ESPECIALIDAD_DESTINO: dict[str, tuple[str, str]] = {
    "bacheo": ("Obras y Desarrollo Urbano", "JUD Bacheo y Pavimentación"),
    "agua": ("Servicios Urbanos", "JUD Agua y Drenaje"),
    "drenaje": ("Servicios Urbanos", "JUD Agua y Drenaje"),
    "alumbrado": ("Servicios Urbanos", "JUD Alumbrado Público"),
    "semaforos": ("Servicios Urbanos", "JUD Alumbrado Público"),
    "limpia": ("Servicios Urbanos", "JUD Limpia"),
    "comercio_vp": ("Servicios Urbanos", "JUD Limpia"),
    "parques": ("Servicios Urbanos", "JUD Áreas Verdes"),
    "arboles": ("Servicios Urbanos", "JUD Áreas Verdes"),
    "seguridad": ("Seguridad Ciudadana y Movilidad", "JUD Operación de Campo"),
}


async def _nodos_por_nombre(db: AsyncSession, tenant_id: str) -> dict[str, OrgNodo]:
    rows = await db.execute(select(OrgNodo).where(OrgNodo.tenant_id == tenant_id))
    return {n.nombre: n for n in rows.scalars().all()}


async def _ensure_area(
    db: AsyncSession, tenant_id: str, direccion: OrgNodo,
    nodos: dict[str, OrgNodo],
) -> OrgNodo:
    """Dirección de Área que sostiene las JUD de una Dirección General.

    Regla de jerarquía: jud ∈ {dir_area, subdireccion}, por lo que una JUD no
    puede colgar directo de una Dirección General (ADQ-02). Reutiliza la
    Dirección de Área que sembró la plantilla (mismo nombre) o la crea.
    """
    area_nombre = f"Dirección de Área · {direccion.nombre}"
    existente = nodos.get(area_nombre)
    if existente is not None:
        return existente
    area = OrgNodo(
        id=str(uuid.uuid4()), tenant_id=tenant_id, parent_id=direccion.id,
        nivel="dir_area", tipo="direccion", nombre=area_nombre, orden=0,
    )
    db.add(area)
    await db.flush()
    nodos[area_nombre] = area
    return area


async def _ensure_jud(
    db: AsyncSession, tenant_id: str, direccion: OrgNodo, jud_nombre: str,
    nodos: dict[str, OrgNodo],
) -> OrgNodo:
    """Devuelve la JUD ``jud_nombre`` bajo ``direccion``, creándola si falta."""
    existente = nodos.get(jud_nombre)
    if existente is not None:
        return existente
    # Si la dirección es una Dirección General, intercalar una Dirección de Área
    # como padre válido de la JUD (jud ∈ {dir_area, subdireccion}); si ya es
    # dir_area/subdireccion, la JUD cuelga directo de ella.
    padre = direccion
    if direccion.nivel == "dir_general":
        padre = await _ensure_area(db, tenant_id, direccion, nodos)
    jud = OrgNodo(
        id=str(uuid.uuid4()), tenant_id=tenant_id, parent_id=padre.id,
        nivel="jud", tipo="unidad", nombre=jud_nombre, orden=50,
    )
    db.add(jud)
    await db.flush()
    nodos[jud_nombre] = jud
    return jud


async def link_cuadrillas(db: AsyncSession, tenant_id: str) -> None:
    """Fase 3: recuelga las cuadrillas reales (y sus integrantes) del nodo correcto.

    Cada cuadrilla se ata a la JUD que corresponde a su especialidad principal;
    el jefe de cuadrilla (integrante con user_id) queda como personal de campo
    de ese nodo. Idempotente: no duplica nodos ya enlazados.
    """
    nodos = await _nodos_por_nombre(db, tenant_id)

    # Eliminar las cuadrillas placeholder de la plantilla (cuadrilla_id NULL):
    # las cuadrillas reales las sustituyen.
    await db.execute(
        delete(OrgNodo).where(
            OrgNodo.tenant_id == tenant_id,
            OrgNodo.nivel == "jefe_cuadrilla",
            OrgNodo.cuadrilla_id.is_(None),
        )
    )
    await db.flush()
    nodos = await _nodos_por_nombre(db, tenant_id)

    # Nodos ya enlazados (idempotencia).
    enlazadas = {
        n.cuadrilla_id: n
        for n in nodos.values()
        if n.cuadrilla_id is not None
    }

    cuadrillas = (
        await db.execute(select(Cuadrilla).where(Cuadrilla.tenant_id == tenant_id))
    ).scalars().all()

    for c in cuadrillas:
        # Especialidad principal de la cuadrilla.
        esp_rows = await db.execute(
            select(cuadrilla_especialidades.c.categoria_id).where(
                cuadrilla_especialidades.c.cuadrilla_id == c.id
            )
        )
        especialidades = [r[0] for r in esp_rows.fetchall()]
        destino = None
        for esp in especialidades:
            if esp in ESPECIALIDAD_DESTINO:
                destino = ESPECIALIDAD_DESTINO[esp]
                break
        if destino is None:
            # Sin mapeo claro: cuelga de Servicios Urbanos / Mantenimiento.
            destino = ("Servicios Urbanos", "JUD Mantenimiento General")

        dir_nombre, jud_nombre = destino
        direccion = nodos.get(dir_nombre)
        if direccion is None:
            continue  # plantilla sin esa dirección (no debería pasar en CDMX)
        jud = await _ensure_jud(db, tenant_id, direccion, jud_nombre, nodos)

        nodo_cuadrilla = enlazadas.get(c.id)
        if nodo_cuadrilla is None:
            nodo_cuadrilla = OrgNodo(
                id=str(uuid.uuid4()), tenant_id=tenant_id, parent_id=jud.id,
                nivel="jefe_cuadrilla", tipo="cuadrilla", nombre=c.nombre,
                orden=0, cuadrilla_id=c.id,
            )
            db.add(nodo_cuadrilla)
            await db.flush()
            enlazadas[c.id] = nodo_cuadrilla
        else:
            nodo_cuadrilla.parent_id = jud.id
            nodo_cuadrilla.nombre = c.nombre

        # Asignar el jefe de la cuadrilla a este nodo (personal de campo).
        jefe = (
            await db.execute(
                select(Integrante).where(
                    Integrante.cuadrilla_id == c.id,
                    Integrante.rol_campo == "jefe",
                    Integrante.user_id.is_not(None),
                )
            )
        ).scalars().first()
        if jefe and jefe.user_id:
            user = (
                await db.execute(select(User).where(User.id == jefe.user_id))
            ).scalar_one_or_none()
            if user:
                user.nodo_id = nodo_cuadrilla.id
                user.es_campo = True

    # Cualquier usuario con rol jefe_cuadrilla sigue siendo personal de campo,
    # aunque no tenga (todavía) integrante vinculado.
    jefes = (
        await db.execute(
            select(User).where(
                User.tenant_id == tenant_id, User.role == "jefe_cuadrilla"
            )
        )
    ).scalars().all()
    for u in jefes:
        u.es_campo = True


async def seed_org(db: AsyncSession) -> None:
    audit = AuditLogger(db=db, ip_address=None, user_agent=None)
    await org_service.ensure_capacidades_catalog(db)

    tenants = (await db.execute(select(Tenant))).scalars().all()
    for tenant in tenants:
        # ¿Ya tiene árbol? Si no, aplicar plantilla CDMX estándar.
        existing = await db.execute(
            select(OrgNodo.id).where(OrgNodo.tenant_id == tenant.id).limit(1)
        )
        if existing.first() is None:
            await org_service.apply_template(
                db,
                tenant.id,
                AplicarPlantillaInput(plantilla="cdmx_estandar", reset=False),
                audit,
                actor_id=None,  # seed: sin actor (FK users.id permite NULL)
            )
            print(f"  · Árbol CDMX estándar creado para {tenant.id}")
        else:
            print(f"  · {tenant.id} ya tiene árbol — solo reasigno usuarios")

        nodos = await _nodos_por_nombre(db, tenant.id)

        # Prefijo de los ids de usuario del tenant (mc- / tl-).
        prefijo = f"{tenant.acronimo.lower()}-" if tenant.acronimo else None
        # Fallback robusto: derivar prefijo de un usuario admin del tenant.
        if not prefijo:
            admin = (
                await db.execute(
                    select(User).where(
                        User.tenant_id == tenant.id, User.role == "admin"
                    )
                )
            ).scalars().first()
            prefijo = admin.id.split("admin")[0] if admin else ""

        for sufijo, nombre_nodo in ASIGNACIONES.items():
            user_id = f"{prefijo}{sufijo}"
            user = (
                await db.execute(select(User).where(User.id == user_id))
            ).scalar_one_or_none()
            nodo = nodos.get(nombre_nodo)
            if user is None or nodo is None:
                continue
            user.nodo_id = nodo.id
            user.es_campo = nodo.nivel in NIVELES_CAMPO

        print(f"  · Usuarios de {tenant.id} asignados a nodos")

        await link_cuadrillas(db, tenant.id)
        print(f"  · Cuadrillas de {tenant.id} recolgadas a sus JUDs")

    await db.commit()


async def main() -> None:
    print(
        f"Connecting to: "
        f"{settings.DATABASE_URL.split('@')[-1] if '@' in settings.DATABASE_URL else settings.DATABASE_URL}"
    )
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as db:
        await seed_org(db)
    await engine.dispose()
    print("✓ Seed del núcleo organizacional completado")


if __name__ == "__main__":
    asyncio.run(main())
