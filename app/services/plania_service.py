"""Servicio de Plan.IA: portafolio de proyectos, plan de trabajo y el
expediente de zona (clustering de reportes -> diagnóstico -> proyecto).

Todo se aísla por ``user.tenant_id`` (derivado del JWT). El expediente de zona
es la capacidad premium: detecta problemas estructurales a partir de reportes
recurrentes y permite convertirlos en proyectos con un clic.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
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
from app.models.user import User

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


async def expediente_zona(
    user: User,
    db: AsyncSession,
    *,
    umbral: int = 5,
    dias: int = 180,
) -> list[dict]:
    """Agrupa reportes por (categoría, colonia) en la ventana y, donde superan el
    umbral, genera un expediente con diagnóstico, recomendación y costo estimado.
    """
    desde = datetime.now(UTC) - timedelta(days=dias)
    rows = (
        await db.execute(
            select(
                Reporte.categoria_id,
                Reporte.colonia_id,
                func.count().label("total"),
                func.avg(Reporte.lat).label("lat"),
                func.avg(Reporte.lng).label("lng"),
            )
            .where(
                Reporte.tenant_id == user.tenant_id,
                Reporte.fecha_creacion >= desde,
            )
            .group_by(Reporte.categoria_id, Reporte.colonia_id)
            .having(func.count() >= umbral)
            .order_by(func.count().desc())
        )
    ).all()

    # Mapas de etiquetas.
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
    for cat_id, col_id, total, lat, lng in rows:
        label = cats.get(cat_id)
        col_nombre = cols.get(col_id)
        reco, costo = _recomendar(label, cat_id, total)
        clave_zona = f"{cat_id}:{col_id}"
        out.append(
            {
                "zona_id": clave_zona,
                "categoria_id": cat_id,
                "categoria_label": label,
                "colonia_id": col_id,
                "colonia_nombre": col_nombre,
                "total_reportes": int(total),
                "severidad": _severidad(int(total)),
                "lat": float(lat) if lat is not None else None,
                "lng": float(lng) if lng is not None else None,
                "diagnostico": (
                    f"Se acumularon {int(total)} reportes de "
                    f"«{label or cat_id}» en {col_nombre or col_id} en los "
                    f"últimos {dias} días, lo que sugiere un problema "
                    f"estructural y no incidentes aislados."
                ),
                "recomendacion": reco,
                "costo_estimado": costo,
                "ya_es_proyecto": clave_zona in ya,
            }
        )
    return out


async def convertir_zona_en_proyecto(
    data: dict, user: User, db: AsyncSession
) -> Proyecto:
    """Crea un Proyecto de Plan.IA a partir de un expediente de zona."""
    col_nombre = data.get("colonia_nombre") or data.get("colonia_id")
    clave_zona = f"{data['categoria_id']}:{data['colonia_id']}"
    p = Proyecto(
        id=str(uuid.uuid4()),
        tenant_id=user.tenant_id,
        nombre=f"{data['recomendacion']} — {col_nombre}",
        tipo="obra",
        descripcion=(
            f"Proyecto generado desde el expediente de zona: "
            f"{data.get('total_reportes', 0)} reportes recurrentes en "
            f"{col_nombre}. Recomendación: {data['recomendacion']}."
        ),
        estado="planeacion",
        prioridad="alta",
        area_id=data["categoria_id"],
        presupuesto_estimado=data.get("costo_estimado"),
        origen_zona=clave_zona,
        responsable_nombre=user.nombre,
    )
    db.add(p)
    await db.flush()
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

CATALOGO_INTEROP: list[dict] = [
    {"id": "sacmex", "nombre": "SACMEX", "categoria": "Agua", "estado": "on-demand",
     "descripcion": "Sistema de Aguas de la CDMX: tomas, fugas y facturación."},
    {"id": "cfe", "nombre": "CFE", "categoria": "Energía", "estado": "on-demand",
     "descripcion": "Comisión Federal de Electricidad: alumbrado y suministro."},
    {"id": "c5", "nombre": "C5", "categoria": "Seguridad", "estado": "on-demand",
     "descripcion": "Centro de Comando, Control, C4i4: cámaras y emergencias."},
    {"id": "finanzas", "nombre": "Finanzas / Tesorería", "categoria": "Pagos", "estado": "on-demand",
     "descripcion": "Secretaría de Administración y Finanzas: predial e ingresos."},
    {"id": "suac", "nombre": "SUAC", "categoria": "Atención", "estado": "on-demand",
     "descripcion": "Sistema Unificado de Atención Ciudadana del Gobierno CDMX."},
]
