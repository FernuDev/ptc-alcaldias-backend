"""Stats computed via SQL aggregations — replaces the in-memory JS calculations."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import case, cast, extract, func, select, text, Float
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.categoria import Categoria
from app.models.colonia import Colonia
from app.models.cuadrilla import Cuadrilla
from app.models.reporte import Reporte
from app.models.user import User
from app.schemas.stats import (
    ActividadReciente,
    CostoOperativo,
    DistribucionDiaSemana,
    DistribucionHoraria,
    DistribucionItem,
    KpisResponse,
    RankingCuadrilla,
    SlaSemanal,
    TiempoCategoria,
    TopColonia,
    VolumenDia,
)

ESTADOS_ABIERTOS = ("nuevo", "asignado", "en_proceso")
SLA_LIMITS = {"critica": 12, "alta": 48, "media": 96, "baja": 168}
DIA_NOMBRES = ["Lun", "Mar", "Mie", "Jue", "Vie", "Sab", "Dom"]


def _base_filter(user: User):
    """Return a list of WHERE clauses for tenant + area isolation."""
    filters = [Reporte.tenant_id == user.tenant_id]
    if user.role != "admin" and user.areas:
        area_ids = [a.id for a in user.areas]
        filters.append(Reporte.categoria_id.in_(area_ids))
    return filters


async def calc_kpis(user: User, db: AsyncSession) -> KpisResponse:
    filters = _base_filter(user)
    now = datetime.now(timezone.utc)

    total_q = select(func.count()).select_from(Reporte).where(*filters)
    total = (await db.execute(total_q)).scalar() or 0

    activos_q = select(func.count()).select_from(Reporte).where(*filters, Reporte.estado.in_(ESTADOS_ABIERTOS))
    activos = (await db.execute(activos_q)).scalar() or 0

    resueltos_q = select(func.count()).select_from(Reporte).where(*filters, Reporte.estado == "resuelto")
    resueltos = (await db.execute(resueltos_q)).scalar() or 0

    avg_q = select(func.avg(Reporte.tiempo_atencion_horas)).where(
        *filters, Reporte.estado.in_(("resuelto", "cerrado"))
    )
    avg_hours = (await db.execute(avg_q)).scalar() or 0

    # SLA risk: open reports exceeding their priority SLA limit
    sla_case = case(
        (Reporte.prioridad == "critica", 12),
        (Reporte.prioridad == "alta", 48),
        (Reporte.prioridad == "media", 96),
        else_=168,
    )
    age_hours = extract("epoch", now - Reporte.fecha_creacion) / 3600
    sla_q = select(func.count()).select_from(Reporte).where(
        *filters, Reporte.estado.in_(ESTADOS_ABIERTOS), age_hours > sla_case
    )
    en_riesgo = (await db.execute(sla_q)).scalar() or 0

    return KpisResponse(
        activos=activos,
        resueltos=resueltos,
        tiempo_promedio_dias=float(avg_hours) / 24 if avg_hours else 0,
        en_riesgo_sla=en_riesgo,
        total_rango=total,
        pct_resueltos=round(resueltos / total * 100, 1) if total else 0,
    )


async def volumen_por_dia(user: User, db: AsyncSession, dias: int = 30) -> list[VolumenDia]:
    filters = _base_filter(user)
    since = datetime.now(timezone.utc) - timedelta(days=dias)

    recibidos_q = (
        select(
            func.date(Reporte.fecha_creacion).label("dia"),
            func.count().label("count"),
        )
        .where(*filters, Reporte.fecha_creacion >= since)
        .group_by(text("dia"))
        .order_by(text("dia"))
    )
    recibidos = {str(r.dia): r.count for r in (await db.execute(recibidos_q)).all()}

    atendidos_q = (
        select(
            func.date(Reporte.fecha_cierre).label("dia"),
            func.count().label("count"),
        )
        .where(*filters, Reporte.fecha_cierre >= since, Reporte.fecha_cierre.isnot(None))
        .group_by(text("dia"))
        .order_by(text("dia"))
    )
    atendidos = {str(r.dia): r.count for r in (await db.execute(atendidos_q)).all()}

    all_days = sorted(set(list(recibidos.keys()) + list(atendidos.keys())))
    return [
        VolumenDia(
            fecha=d,
            dia=d,
            recibidos=recibidos.get(d, 0),
            atendidos=atendidos.get(d, 0),
        )
        for d in all_days
    ]


async def distribucion_categoria(user: User, db: AsyncSession) -> list[DistribucionItem]:
    filters = _base_filter(user)
    q = (
        select(
            Reporte.categoria_id,
            Categoria.label,
            Categoria.color,
            func.count().label("count"),
        )
        .join(Categoria, Reporte.categoria_id == Categoria.id)
        .where(*filters)
        .group_by(Reporte.categoria_id, Categoria.label, Categoria.color)
        .order_by(func.count().desc())
    )
    rows = (await db.execute(q)).all()
    total = sum(r.count for r in rows) or 1
    return [
        DistribucionItem(id=r.categoria_id, label=r.label, color=r.color, count=r.count, pct=round(r.count / total * 100, 1))
        for r in rows
    ]


async def distribucion_estado(user: User, db: AsyncSession) -> list[DistribucionItem]:
    filters = _base_filter(user)
    ESTADO_META = {
        "nuevo": ("#3A8DC0", "Nuevo"),
        "asignado": ("#6B2D8E", "Asignado"),
        "en_proceso": ("#BC955C", "En proceso"),
        "resuelto": ("#2D7A4F", "Resuelto"),
        "cerrado": ("#6B7280", "Cerrado"),
    }
    q = (
        select(Reporte.estado, func.count().label("count"))
        .where(*filters)
        .group_by(Reporte.estado)
    )
    rows = (await db.execute(q)).all()
    total = sum(r.count for r in rows) or 1
    return [
        DistribucionItem(
            id=r.estado,
            label=ESTADO_META.get(r.estado, (r.estado, r.estado))[1],
            color=ESTADO_META.get(r.estado, ("#888", r.estado))[0],
            count=r.count,
            pct=round(r.count / total * 100, 1),
        )
        for r in rows
    ]


async def top_colonias(user: User, db: AsyncSession, n: int = 6) -> list[TopColonia]:
    filters = _base_filter(user)
    q = (
        select(Reporte.colonia_id, Reporte.colonia_nombre, func.count().label("count"))
        .where(*filters)
        .group_by(Reporte.colonia_id, Reporte.colonia_nombre)
        .order_by(func.count().desc())
        .limit(n)
    )
    rows = (await db.execute(q)).all()
    return [TopColonia(colonia_id=r.colonia_id, colonia_nombre=r.colonia_nombre or "", count=r.count) for r in rows]


async def sla_semanal(user: User, db: AsyncSession, semanas: int = 6) -> list[SlaSemanal]:
    filters = _base_filter(user)
    since = datetime.now(timezone.utc) - timedelta(weeks=semanas)
    q = (
        select(
            func.date_trunc("week", Reporte.fecha_cierre).label("semana"),
            func.avg(Reporte.tiempo_atencion_horas).label("promedio"),
        )
        .where(*filters, Reporte.fecha_cierre >= since, Reporte.fecha_cierre.isnot(None))
        .group_by(text("semana"))
        .order_by(text("semana"))
    )
    rows = (await db.execute(q)).all()
    return [SlaSemanal(semana=str(r.semana)[:10], promedio_horas=round(float(r.promedio or 0), 1)) for r in rows]


async def tiempo_por_categoria(user: User, db: AsyncSession) -> list[TiempoCategoria]:
    filters = _base_filter(user)
    q = (
        select(
            Reporte.categoria_id,
            Categoria.label,
            func.avg(Reporte.tiempo_atencion_horas).label("promedio"),
        )
        .join(Categoria, Reporte.categoria_id == Categoria.id)
        .where(*filters, Reporte.tiempo_atencion_horas.isnot(None))
        .group_by(Reporte.categoria_id, Categoria.label)
        .order_by(func.avg(Reporte.tiempo_atencion_horas).desc())
    )
    rows = (await db.execute(q)).all()
    return [TiempoCategoria(categoria_id=r.categoria_id, label=r.label, promedio_horas=round(float(r.promedio or 0), 1)) for r in rows]


async def ranking_cuadrillas(user: User, db: AsyncSession) -> list[RankingCuadrilla]:
    filters = _base_filter(user)
    now = datetime.now(timezone.utc)
    sla_case = case(
        (Reporte.prioridad == "critica", 12),
        (Reporte.prioridad == "alta", 48),
        (Reporte.prioridad == "media", 96),
        else_=168,
    )
    q = (
        select(
            Reporte.cuadrilla_id,
            Cuadrilla.nombre,
            func.count().label("resueltos"),
            func.avg(Reporte.tiempo_atencion_horas).label("promedio"),
            (
                func.sum(case((Reporte.tiempo_atencion_horas <= cast(sla_case, Float), 1), else_=0))
                * 100.0
                / func.count()
            ).label("sla_pct"),
        )
        .join(Cuadrilla, Reporte.cuadrilla_id == Cuadrilla.id)
        .where(*filters, Reporte.cuadrilla_id.isnot(None), Reporte.estado.in_(("resuelto", "cerrado")))
        .group_by(Reporte.cuadrilla_id, Cuadrilla.nombre)
        .order_by(func.count().desc())
    )
    rows = (await db.execute(q)).all()
    return [
        RankingCuadrilla(
            cuadrilla_id=r.cuadrilla_id,
            nombre=r.nombre,
            resueltos=r.resueltos,
            promedio_horas=round(float(r.promedio or 0), 1),
            sla_pct=round(float(r.sla_pct or 0), 1),
        )
        for r in rows
    ]


async def distribucion_horaria(user: User, db: AsyncSession) -> list[DistribucionHoraria]:
    filters = _base_filter(user)
    q = (
        select(extract("hour", Reporte.fecha_creacion).label("hora"), func.count().label("count"))
        .where(*filters)
        .group_by(text("hora"))
        .order_by(text("hora"))
    )
    rows = (await db.execute(q)).all()
    return [DistribucionHoraria(hora=int(r.hora), count=r.count) for r in rows]


async def distribucion_dia_semana(user: User, db: AsyncSession) -> list[DistribucionDiaSemana]:
    filters = _base_filter(user)
    q = (
        select(extract("isodow", Reporte.fecha_creacion).label("dow"), func.count().label("count"))
        .where(*filters)
        .group_by(text("dow"))
        .order_by(text("dow"))
    )
    rows = (await db.execute(q)).all()
    return [
        DistribucionDiaSemana(dia=int(r.dow), nombre=DIA_NOMBRES[int(r.dow) - 1] if int(r.dow) <= 7 else "?", count=r.count)
        for r in rows
    ]


async def costo_operativo(user: User, db: AsyncSession) -> list[CostoOperativo]:
    filters = _base_filter(user)
    q = (
        select(
            Reporte.categoria_id,
            Categoria.label,
            func.coalesce(func.sum(Reporte.costo_estimado), 0).label("estimado"),
            func.coalesce(func.sum(Reporte.gasto_real), 0).label("ejercido"),
        )
        .join(Categoria, Reporte.categoria_id == Categoria.id)
        .where(*filters)
        .group_by(Reporte.categoria_id, Categoria.label)
        .order_by(func.sum(Reporte.costo_estimado).desc())
    )
    rows = (await db.execute(q)).all()
    return [CostoOperativo(categoria_id=r.categoria_id, label=r.label, estimado=r.estimado, ejercido=r.ejercido) for r in rows]


async def actividad_reciente(user: User, db: AsyncSession, n: int = 6) -> list[ActividadReciente]:
    filters = _base_filter(user)
    q = (
        select(Reporte.id, Reporte.titulo, Reporte.fecha_actualizacion, Reporte.categoria_id, Reporte.estado)
        .where(*filters)
        .order_by(Reporte.fecha_actualizacion.desc())
        .limit(n)
    )
    rows = (await db.execute(q)).all()
    return [
        ActividadReciente(
            id=r.id,
            tipo="reporte",
            titulo=r.titulo,
            fecha=r.fecha_actualizacion.isoformat() if r.fecha_actualizacion else "",
            categoria_id=r.categoria_id,
            estado=r.estado,
        )
        for r in rows
    ]
