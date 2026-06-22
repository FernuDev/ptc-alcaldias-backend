"""Servicio de Plan.IA: portafolio de proyectos, plan de trabajo y el
expediente de zona (clustering de reportes -> diagnóstico -> proyecto).

Todo se aísla por ``user.tenant_id`` (derivado del JWT). El expediente de zona
es la capacidad premium: detecta problemas estructurales a partir de reportes
recurrentes y permite convertirlos en proyectos con un clic.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditLogger
from app.core.exceptions import NotFoundError
from app.models.campo import Tarea
from app.models.categoria import Categoria
from app.models.colonia import Colonia
from app.models.proyecto import (
    Proyecto,
    ProyectoAprobacion,
    ProyectoRiesgo,
    ProyectoStakeholder,
    ProyectoTarea,
)
from app.models.reporte import Reporte
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.config import ZONA_PARAMS_DEFAULT

# ── Heurísticas del expediente de zona ──────────────────────────────────────
# Recomendación y costo unitario estimado por palabra clave de la categoría.
_RECOMENDACIONES: list[tuple[tuple[str, ...], str, float]] = [
    (("bache", "pavimento", "vial"), "Repavimentación del tramo afectado", 85_000),
    (("agua", "fuga", "drenaje", "tuberia"), "Sustitución de tubería / reparación de red", 120_000),
    (("alumbrado", "luminaria", "luz"), "Sustitución de luminarias del cuadrante", 18_000),
    (("basura", "limpia", "residuo"), "Operativo de limpia y descacharrización", 12_000),
    (("arbol", "poda", "parque", "jardin", "area verde"), "Programa de poda y rehabilitación de áreas verdes", 22_000),
    (("banqueta", "guarnicion"), "Reconstrucción de banquetas y guarniciones", 45_000),
]
_COSTO_DEFAULT = 30_000.0


def _recomendar(label: str | None, categoria_id: str, total: int) -> tuple[str, float]:
    texto = f"{label or ''} {categoria_id}".lower()
    for claves, reco, unit in _RECOMENDACIONES:
        if any(k in texto for k in claves):
            return reco, round(unit * max(total, 1), 2)
    return "Intervención integral de la zona", round(_COSTO_DEFAULT * max(total, 1), 2)


def _severidad(total: int) -> str:
    if total >= 12:
        return "alta"
    if total >= 7:
        return "media"
    return "baja"


# Dirección/área líder sugerida por categoría del reporte (REQ-09: el proyecto
# generado declara una dirección líder, no la categoría cruda ni el usuario).
_DIRECCION_LIDER: dict[str, tuple[str, str]] = {
    "bacheo": ("obras", "Dirección de Obras y Servicios Urbanos"),
    "agua": ("agua", "Dirección de Agua y Drenaje"),
    "drenaje": ("agua", "Dirección de Agua y Drenaje"),
    "alumbrado": ("alumbrado", "Dirección de Alumbrado Público"),
    "semaforos": ("alumbrado", "Dirección de Alumbrado y Semáforos"),
    "limpia": ("limpia", "Dirección de Limpia"),
    "comercio_vp": ("limpia", "Dirección de Vía Pública y Comercio"),
    "parques": ("parques", "Dirección de Áreas Verdes y Arbolado"),
    "arboles": ("parques", "Dirección de Áreas Verdes y Arbolado"),
    "seguridad": ("seguridad", "Dirección de Seguridad Ciudadana"),
}
_DIRECCION_DEFAULT = ("obras", "Dirección de Obras y Servicios Urbanos")


def _direccion_lider(categoria_id: str) -> tuple[str, str]:
    """Devuelve (area_id, nombre_dirección) líder para una categoría."""
    return _DIRECCION_LIDER.get(categoria_id, _DIRECCION_DEFAULT)


# Clustering espacio-temporal con PostGIS: ST_ClusterDBSCAN sobre los reportes de
# la ventana temporal, particionado por categoría, con eps=radio (metros) y
# minpoints=umbral. ``geom`` es una columna generada (SRID 4326) que se proyecta a
# EPSG:6372 (métrico, válido para México) para medir distancias en metros.
_CLUSTER_SQL = text(
    """
    WITH base AS (
        SELECT
            id, categoria_id, colonia_id, colonia_nombre, lat, lng,
            ST_ClusterDBSCAN(
                ST_Transform(geom, 6372),
                eps := :radio,
                minpoints := :umbral
            ) OVER (PARTITION BY categoria_id) AS cid
        FROM reportes
        WHERE tenant_id = :tenant
          AND fecha_creacion >= :desde
    )
    SELECT
        categoria_id,
        cid,
        count(*) AS total,
        mode() WITHIN GROUP (ORDER BY colonia_id) AS colonia_id,
        mode() WITHIN GROUP (ORDER BY colonia_nombre) AS colonia_nombre,
        avg(lat) AS lat,
        avg(lng) AS lng,
        array_agg(id ORDER BY id) AS reporte_ids,
        array_agg(lng ORDER BY id) AS lngs,
        array_agg(lat ORDER BY id) AS lats
    FROM base
    WHERE cid IS NOT NULL
    GROUP BY categoria_id, cid
    HAVING count(*) >= :umbral
    ORDER BY total DESC
    """
)

# Fallback sin PostGIS (Postgres plano, p. ej. producción): agrupa por
# (categoría, colonia). Devuelve las MISMAS columnas que ``_CLUSTER_SQL`` para
# reutilizar el mismo procesamiento. Ignora ``:radio`` (no hay proximidad real).
_CLUSTER_SQL_FALLBACK = text(
    """
    SELECT
        categoria_id,
        mode() WITHIN GROUP (ORDER BY colonia_id) AS colonia_id,
        mode() WITHIN GROUP (ORDER BY colonia_nombre) AS colonia_nombre,
        count(*) AS total,
        avg(lat) AS lat,
        avg(lng) AS lng,
        array_agg(id ORDER BY id) AS reporte_ids,
        array_agg(lng ORDER BY id) AS lngs,
        array_agg(lat ORDER BY id) AS lats
    FROM reportes
    WHERE tenant_id = :tenant
      AND fecha_creacion >= :desde
    GROUP BY categoria_id, colonia_id
    HAVING count(*) >= :umbral
    ORDER BY total DESC
    """
)

# Detección perezosa (cacheada) de si existe la columna ``geom`` (= PostGIS
# habilitado por la migración). Si no, se usa el fallback no-espacial.
_geom_disponible_cache: bool | None = None


async def _geom_disponible(db: AsyncSession) -> bool:
    global _geom_disponible_cache
    if _geom_disponible_cache is None:
        _geom_disponible_cache = bool(
            (
                await db.execute(
                    text(
                        "SELECT 1 FROM information_schema.columns "
                        "WHERE table_name = 'reportes' AND column_name = 'geom'"
                    )
                )
            ).scalar()
        )
    return _geom_disponible_cache


# ── Portafolio / Proyectos ──────────────────────────────────────────────────


async def listar_proyectos(
    user: User,
    db: AsyncSession,
    *,
    tipo: str | None = None,
    estado: str | None = None,
) -> list[Proyecto]:
    q = select(Proyecto).where(Proyecto.tenant_id == user.tenant_id)
    if tipo:
        q = q.where(Proyecto.tipo == tipo)
    if estado:
        q = q.where(Proyecto.estado == estado)
    q = q.order_by(Proyecto.created_at.desc())
    return list((await db.execute(q)).scalars().all())


async def _adjuntar_tickets(p: Proyecto, user: User, db: AsyncSession) -> None:
    """Adjunta a cada tarea de proyecto su ticket de cuadrilla espejo (REQ-07)."""
    tareas = list(p.tareas)
    if not tareas:
        return
    tickets = (
        (
            await db.execute(
                select(Tarea)
                .where(
                    Tarea.tenant_id == user.tenant_id,
                    Tarea.proyecto_id == p.id,
                    Tarea.proyecto_tarea_id.is_not(None),
                )
                .order_by(Tarea.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    # Último ticket por tarea de proyecto (el más reciente «gana»).
    por_pt: dict[str, Tarea] = {}
    for t in tickets:
        if t.proyecto_tarea_id is not None:
            por_pt.setdefault(t.proyecto_tarea_id, t)
    for pt in tareas:
        pt.ticket = por_pt.get(pt.id)


async def get_proyecto(proyecto_id: str, user: User, db: AsyncSession) -> Proyecto:
    p = (
        await db.execute(
            select(Proyecto).where(
                Proyecto.id == proyecto_id, Proyecto.tenant_id == user.tenant_id
            )
        )
    ).scalar_one_or_none()
    if p is None:
        raise NotFoundError("Proyecto", proyecto_id)
    await _adjuntar_tickets(p, user, db)
    return p


async def crear_proyecto(data: dict, user: User, db: AsyncSession) -> Proyecto:
    p = Proyecto(
        id=str(uuid.uuid4()),
        tenant_id=user.tenant_id,
        **{k: v for k, v in data.items() if v is not None},
    )
    db.add(p)
    await db.flush()
    return p


async def actualizar_proyecto(
    proyecto_id: str, data: dict, user: User, db: AsyncSession
) -> Proyecto:
    p = await get_proyecto(proyecto_id, user, db)
    for k, v in data.items():
        if v is not None:
            setattr(p, k, v)
    await db.flush()
    return p


async def crear_tarea(
    proyecto_id: str, data: dict, user: User, db: AsyncSession
) -> ProyectoTarea:
    await get_proyecto(proyecto_id, user, db)  # valida tenant/existencia
    t = ProyectoTarea(
        id=str(uuid.uuid4()),
        proyecto_id=proyecto_id,
        tenant_id=user.tenant_id,
        **{k: v for k, v in data.items() if v is not None},
    )
    db.add(t)
    await db.flush()
    return t


async def actualizar_tarea(
    tarea_id: str, data: dict, user: User, db: AsyncSession
) -> ProyectoTarea:
    t = (
        await db.execute(
            select(ProyectoTarea).where(
                ProyectoTarea.id == tarea_id,
                ProyectoTarea.tenant_id == user.tenant_id,
            )
        )
    ).scalar_one_or_none()
    if t is None:
        raise NotFoundError("Tarea de proyecto", tarea_id)
    for k, v in data.items():
        if v is not None:
            setattr(t, k, v)
    await db.flush()
    return t


async def portafolio(user: User, db: AsyncSession) -> dict:
    proyectos = await listar_proyectos(user, db)
    total = len(proyectos)
    avance_global = (
        round(sum(p.avance_pct for p in proyectos) / total, 1) if total else 0.0
    )
    inversion = float(sum(float(p.presupuesto_estimado or 0) for p in proyectos))
    alineados = sum(1 for p in proyectos if p.compromiso_id)

    def _bucket(key_fn) -> list[dict]:
        grupos: dict[str, list[Proyecto]] = {}
        for p in proyectos:
            grupos.setdefault(key_fn(p), []).append(p)
        return [
            {
                "clave": k,
                "total": len(v),
                "avance_promedio": round(
                    sum(x.avance_pct for x in v) / len(v), 1
                ),
            }
            for k, v in sorted(grupos.items())
        ]

    return {
        "total": total,
        "avance_global": avance_global,
        "inversion_estimada": inversion,
        "por_tipo": _bucket(lambda p: p.tipo),
        "por_estado": _bucket(lambda p: p.estado),
        "alineados_a_compromiso": alineados,
    }


# ── Expediente de zona (clustering espacio-temporal) ────────────────────────


async def _resolver_zona_params(
    user: User,
    db: AsyncSession,
    umbral: int | None,
    dias: int | None,
    radio: int | None,
) -> tuple[int, int, int]:
    """Resuelve los parámetros de clustering: override del query > config del
    tenant > default global."""
    tenant = await db.get(Tenant, user.tenant_id)
    params = {**ZONA_PARAMS_DEFAULT, **((tenant.zona_params if tenant else None) or {})}
    return (
        int(umbral if umbral is not None else params["umbral"]),
        int(dias if dias is not None else params["ventana_dias"]),
        int(radio if radio is not None else params["radio_m"]),
    )


async def expediente_zona(
    user: User,
    db: AsyncSession,
    *,
    umbral: int | None = None,
    dias: int | None = None,
    radio: int | None = None,
) -> list[dict]:
    """Detecta zonas problemáticas con clustering espacio-temporal (PostGIS
    ST_ClusterDBSCAN: proximidad ``radio`` m + ventana ``dias`` + densidad
    ``umbral``) y genera un expediente con diagnóstico, recomendación, costo
    estimado, dirección líder y los puntos del cluster para el mapa.

    Si ``umbral``/``dias``/``radio`` no se especifican, usa los parámetros
    configurados por tenant en Configuración.
    """
    umbral, dias, radio = await _resolver_zona_params(user, db, umbral, dias, radio)
    desde = datetime.now(UTC) - timedelta(days=dias)
    # PostGIS si está disponible (DBSCAN espacial); si no, fallback por colonia.
    sql = _CLUSTER_SQL if await _geom_disponible(db) else _CLUSTER_SQL_FALLBACK
    rows = (
        await db.execute(
            sql,
            {"tenant": user.tenant_id, "desde": desde, "umbral": umbral, "radio": radio},
        )
    ).all()

    cats = {
        c.id: c.label
        for c in (await db.execute(select(Categoria))).scalars().all()
    }
    cols = {
        c.id: c.nombre
        for c in (
            await db.execute(
                select(Colonia).where(Colonia.tenant_id == user.tenant_id)
            )
        ).scalars().all()
    }
    # Proyectos ya generados desde zona (para marcar ya_es_proyecto).
    ya = {
        p.origen_zona
        for p in (
            await db.execute(
                select(Proyecto).where(
                    Proyecto.tenant_id == user.tenant_id,
                    Proyecto.origen_zona.is_not(None),
                )
            )
        ).scalars().all()
    }

    out: list[dict] = []
    for r in rows:
        cat_id = r.categoria_id
        col_id = r.colonia_id
        total = int(r.total)
        label = cats.get(cat_id)
        col_nombre = r.colonia_nombre or cols.get(col_id)
        reco, costo = _recomendar(label, cat_id, total)
        _, direccion = _direccion_lider(cat_id)
        clave_zona = f"{cat_id}:{col_id}"
        puntos = [
            [float(lng), float(lat)]
            for lng, lat in zip(r.lngs, r.lats)
            if lng is not None and lat is not None
        ]
        out.append(
            {
                "zona_id": clave_zona,
                "categoria_id": cat_id,
                "categoria_label": label,
                "colonia_id": col_id,
                "colonia_nombre": col_nombre,
                "total_reportes": total,
                "severidad": _severidad(total),
                "lat": float(r.lat) if r.lat is not None else None,
                "lng": float(r.lng) if r.lng is not None else None,
                "diagnostico": (
                    f"Se detectó una concentración de {total} reportes de "
                    f"«{label or cat_id}» en {col_nombre or col_id} en los "
                    f"últimos {dias} días, lo que sugiere un problema "
                    f"estructural y no incidentes aislados."
                ),
                "recomendacion": reco,
                "costo_estimado": costo,
                "direccion_lider": direccion,
                "puntos": puntos,
                "reporte_ids": list(r.reporte_ids),
                "ya_es_proyecto": clave_zona in ya,
            }
        )
    return out


async def convertir_zona_en_proyecto(
    data: dict,
    user: User,
    db: AsyncSession,
    audit: AuditLogger | None = None,
) -> Proyecto:
    """Crea un Proyecto de Plan.IA a partir de un expediente de zona, hereda la
    dirección líder y el costo estimado, vincula los reportes del cluster y deja
    traza auditable (REQ-09)."""
    col_nombre = data.get("colonia_nombre") or data.get("colonia_id")
    cat_id = data["categoria_id"]
    clave_zona = f"{cat_id}:{data['colonia_id']}"
    area_id, direccion = _direccion_lider(cat_id)

    # Carga los reportes del cluster ANTES de construir el proyecto para asignar
    # la relación al instanciar (evita un lazy-load síncrono después del flush).
    reporte_ids = data.get("reporte_ids") or []
    reportes: list[Reporte] = []
    if reporte_ids:
        reportes = list(
            (
                await db.execute(
                    select(Reporte).where(
                        Reporte.tenant_id == user.tenant_id,
                        Reporte.id.in_(reporte_ids),
                    )
                )
            )
            .scalars()
            .all()
        )

    p = Proyecto(
        id=str(uuid.uuid4()),
        tenant_id=user.tenant_id,
        nombre=f"{data['recomendacion']} — {col_nombre}",
        tipo="obra",
        descripcion=(
            f"Proyecto generado desde el expediente de zona: "
            f"{data.get('total_reportes', 0)} reportes recurrentes en "
            f"{col_nombre}. Recomendación: {data['recomendacion']}. "
            f"Dirección líder sugerida: {direccion}."
        ),
        estado="planeacion",
        prioridad="alta",
        area_id=area_id,
        presupuesto_estimado=data.get("costo_estimado"),
        origen_zona=clave_zona,
        responsable_nombre=direccion,
        reportes_vinculados=reportes,  # trazabilidad reporte→proyecto
    )
    db.add(p)
    await db.flush()

    if audit is not None:
        await audit.log(
            action="crear",
            user_id=user.id,
            tenant_id=user.tenant_id,
            entity_type="proyecto",
            entity_id=p.id,
            extra={
                "origen": "expediente_zona",
                "zona_id": clave_zona,
                "reportes_vinculados": len(reporte_ids),
                "direccion_lider": direccion,
                "costo_estimado": data.get("costo_estimado"),
            },
        )
    return p


# ── Capa de Coordinación (stakeholders, riesgos, aprobaciones) ──────────────


async def listar_stakeholders(
    proyecto_id: str, user: User, db: AsyncSession
) -> list[ProyectoStakeholder]:
    await get_proyecto(proyecto_id, user, db)
    return list(
        (
            await db.execute(
                select(ProyectoStakeholder).where(
                    ProyectoStakeholder.proyecto_id == proyecto_id,
                    ProyectoStakeholder.tenant_id == user.tenant_id,
                )
            )
        ).scalars().all()
    )


async def crear_stakeholder(
    proyecto_id: str, data: dict, user: User, db: AsyncSession
) -> ProyectoStakeholder:
    await get_proyecto(proyecto_id, user, db)
    s = ProyectoStakeholder(
        id=str(uuid.uuid4()),
        proyecto_id=proyecto_id,
        tenant_id=user.tenant_id,
        **{k: v for k, v in data.items() if v is not None},
    )
    db.add(s)
    await db.flush()
    return s


async def eliminar_stakeholder(sid: str, user: User, db: AsyncSession) -> None:
    s = (
        await db.execute(
            select(ProyectoStakeholder).where(
                ProyectoStakeholder.id == sid,
                ProyectoStakeholder.tenant_id == user.tenant_id,
            )
        )
    ).scalar_one_or_none()
    if s is None:
        raise NotFoundError("Stakeholder", sid)
    await db.delete(s)


async def listar_riesgos(
    proyecto_id: str, user: User, db: AsyncSession
) -> list[ProyectoRiesgo]:
    await get_proyecto(proyecto_id, user, db)
    return list(
        (
            await db.execute(
                select(ProyectoRiesgo).where(
                    ProyectoRiesgo.proyecto_id == proyecto_id,
                    ProyectoRiesgo.tenant_id == user.tenant_id,
                )
            )
        ).scalars().all()
    )


async def crear_riesgo(
    proyecto_id: str, data: dict, user: User, db: AsyncSession
) -> ProyectoRiesgo:
    await get_proyecto(proyecto_id, user, db)
    r = ProyectoRiesgo(
        id=str(uuid.uuid4()),
        proyecto_id=proyecto_id,
        tenant_id=user.tenant_id,
        **{k: v for k, v in data.items() if v is not None},
    )
    db.add(r)
    await db.flush()
    return r


async def actualizar_riesgo(
    rid: str, data: dict, user: User, db: AsyncSession
) -> ProyectoRiesgo:
    r = (
        await db.execute(
            select(ProyectoRiesgo).where(
                ProyectoRiesgo.id == rid, ProyectoRiesgo.tenant_id == user.tenant_id
            )
        )
    ).scalar_one_or_none()
    if r is None:
        raise NotFoundError("Riesgo", rid)
    for k, v in data.items():
        if v is not None:
            setattr(r, k, v)
    await db.flush()
    return r


async def listar_aprobaciones(
    proyecto_id: str, user: User, db: AsyncSession
) -> list[ProyectoAprobacion]:
    await get_proyecto(proyecto_id, user, db)
    return list(
        (
            await db.execute(
                select(ProyectoAprobacion)
                .where(
                    ProyectoAprobacion.proyecto_id == proyecto_id,
                    ProyectoAprobacion.tenant_id == user.tenant_id,
                )
                .order_by(ProyectoAprobacion.orden)
            )
        ).scalars().all()
    )


async def crear_aprobacion(
    proyecto_id: str, data: dict, user: User, db: AsyncSession
) -> ProyectoAprobacion:
    await get_proyecto(proyecto_id, user, db)
    a = ProyectoAprobacion(
        id=str(uuid.uuid4()),
        proyecto_id=proyecto_id,
        tenant_id=user.tenant_id,
        **{k: v for k, v in data.items() if v is not None},
    )
    db.add(a)
    await db.flush()
    return a


async def resolver_aprobacion(
    aid: str, estado: str, comentario: str | None, user: User, db: AsyncSession
) -> ProyectoAprobacion:
    a = (
        await db.execute(
            select(ProyectoAprobacion).where(
                ProyectoAprobacion.id == aid,
                ProyectoAprobacion.tenant_id == user.tenant_id,
            )
        )
    ).scalar_one_or_none()
    if a is None:
        raise NotFoundError("Aprobación", aid)
    a.estado = estado
    a.comentario = comentario
    a.fecha_resolucion = datetime.now(UTC)
    await db.flush()
    return a


# ── Catálogo de interoperabilidad (REQ-08) ──────────────────────────────────

# Estado = disponibilidad comercial del conector (no integración activa):
#   disponible  → conector listo para desplegar bajo contrato.
#   on-demand   → se construye a demanda (alcance cotizable).
#   no_contratado → no incluido en el contrato actual.
#
# ADQ-03 · REQ-01 · R5.5: SUAC se eleva a integración PRIORITARIA. La Dirección
# de Servicios Urbanos rinde cuentas en SUAC, así que el catálogo lo destaca y
# lo ancla al inicio; `prioritaria=True` + `nota` documentan la sincronización
# bidireccional (evitar doble captura) y la integración real planeada para R5.5.
CATALOGO_INTEROP: list[dict] = [
    {"id": "suac", "nombre": "SUAC", "categoria": "Atención", "estado": "no_contratado",
     "prioritaria": True,
     "descripcion": "Sistema Unificado de Atención Ciudadana del Gobierno CDMX. "
                    "La Dirección de Servicios Urbanos rinde cuentas en SUAC.",
     "nota": "Integración prioritaria: sincronización bidireccional de reportes "
             "con SUAC para no capturar doble. Integración real planeada para R5.5."},
    {"id": "sacmex", "nombre": "SACMEX", "categoria": "Agua", "estado": "on-demand",
     "descripcion": "Sistema de Aguas de la CDMX: tomas, fugas y facturación."},
    {"id": "cfe", "nombre": "CFE", "categoria": "Energía", "estado": "on-demand",
     "descripcion": "Comisión Federal de Electricidad: alumbrado y suministro."},
    {"id": "c5", "nombre": "C5", "categoria": "Seguridad", "estado": "disponible",
     "descripcion": "Centro de Comando, Control, C4i4: cámaras y emergencias."},
    {"id": "finanzas", "nombre": "Finanzas / Tesorería", "categoria": "Pagos", "estado": "disponible",
     "descripcion": "Secretaría de Administración y Finanzas: predial e ingresos."},
]
