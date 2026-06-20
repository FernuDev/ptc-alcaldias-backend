"""Scorecards de desempeño (REQ-06) calculados vía agregación SQL.

Tarjetas de rendimiento por **cuadrilla** y por **persona** (integrante de campo).
Sigue el estilo de :mod:`app.services.stats_service` (ver ``ranking_cuadrillas``):
agregaciones puras en SQL, una sesión async, sin cálculo en memoria salvo el
ensamblado final de los schemas.

Métricas
--------
* reportes/tareas resueltos (volumen cerrado).
* tiempo medio de atención (horas) de reportes cerrados.
* % de cumplimiento de SLA (cerrado dentro del límite por prioridad).
* carga vs capacidad (tareas activas vs nº de integrantes activos).
* reaperturas / reincidencias (reportes reabiertos tras 'resuelto', heurística
  por ``ReporteEvento``: un cierre seguido de actividad posterior).

Visibilidad jerárquica (clave)
------------------------------
La función de scope ``_visibilidad`` traduce el rol del ``CurrentUser`` en el
conjunto de cuadrillas que puede ver:

* **admin** → todo el tenant.
* **director_area / supervisor** (permiso ``EJECUTIVO_VER``) → su equipo: las
  cuadrillas cuya especialidad cae en alguna de SUS áreas asignadas. Fail-closed:
  sin áreas no ve nada.
* **jefe_cuadrilla / inspector** (sin ``EJECUTIVO_VER``) → solo lo suyo: la
  cuadrilla a la que pertenece su ``Integrante`` vinculado.

Nadie ve a sus pares. El tenant SIEMPRE proviene del JWT (filtro ``tenant_id``).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import Float, and_, case, cast, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, NotFoundError
from app.core.permissions import Permission, has_permission
from app.models.campo import Tarea
from app.models.cuadrilla import Cuadrilla, Integrante, cuadrilla_especialidades
from app.models.reporte import Reporte, ReporteEvento
from app.models.user import User
from app.schemas.scorecard import (
    CuadrillaScorecard,
    PersonaScorecard,
    ScorecardMetricas,
    ScorecardScope,
)

# Estados de un reporte que NO están cerrados (carga viva).
ESTADOS_ABIERTOS = ("nuevo", "asignado", "en_proceso")
ESTADOS_CERRADOS = ("resuelto", "cerrado")
# Estados de tarea que cuentan como carga activa (sin cerrar).
TAREA_ESTADOS_ACTIVOS = ("pendiente", "en_ruta", "en_sitio")
# Límite SLA en horas por prioridad (idéntico a stats_service).
SLA_CASE = case(
    (Reporte.prioridad == "critica", 12),
    (Reporte.prioridad == "alta", 48),
    (Reporte.prioridad == "media", 96),
    else_=168,
)


@dataclass
class _Scope:
    """Alcance de visibilidad resuelto para el usuario actual."""

    nivel: str  # global | area | propio
    # Lista de cuadrilla_ids visibles. ``None`` significa "todas" (admin).
    cuadrilla_ids: list[str] | None
    areas: list[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# Visibilidad jerárquica
# ─────────────────────────────────────────────────────────────────────────────
async def _visibilidad(user: User, db: AsyncSession) -> _Scope:
    """Resuelve qué cuadrillas puede ver ``user`` según su rol/permisos.

    No expone pares: un director ve su área, un operador ve solo su cuadrilla.
    """
    if user.role == "admin":
        return _Scope(nivel="global", cuadrilla_ids=None)

    # R5 · Fase 4: con el RBAC heredado encendido, el alcance se deriva del árbol.
    # El desempeño global solo es visible desde Administración y Finanzas / Alcalde;
    # el resto ve su sub-árbol (sin ver a sus pares).
    from app.core.scoping import (
        es_nodo_transversal_global,
        is_global_scope,
        rbac_heredado_activo,
        user_scope_cuadrilla_ids,
    )

    if rbac_heredado_activo() and user.nodo_id:
        if is_global_scope(user) or es_nodo_transversal_global(user):
            return _Scope(nivel="global", cuadrilla_ids=None)
        ids = await user_scope_cuadrilla_ids(db, user) or []
        return _Scope(nivel="area", cuadrilla_ids=ids, areas=[])

    # Director de área / supervisor: equipo de su(s) área(s) (visión ejecutiva).
    if has_permission(user.role, Permission.EJECUTIVO_VER):
        area_ids = [a.id for a in user.areas]
        if not area_ids:
            # Fail-closed: sin áreas asignadas no agrega a nadie.
            return _Scope(nivel="area", cuadrilla_ids=[], areas=[])
        rows = await db.execute(
            select(cuadrilla_especialidades.c.cuadrilla_id)
            .join(Cuadrilla, Cuadrilla.id == cuadrilla_especialidades.c.cuadrilla_id)
            .where(
                Cuadrilla.tenant_id == user.tenant_id,
                cuadrilla_especialidades.c.categoria_id.in_(area_ids),
            )
            .distinct()
        )
        ids = [r[0] for r in rows.all()]
        return _Scope(nivel="area", cuadrilla_ids=ids, areas=area_ids)

    # Operador de campo (jefe_cuadrilla / inspector): solo SU cuadrilla.
    if has_permission(user.role, Permission.CAMPO_EJECUTAR):
        row = await db.execute(
            select(Integrante.cuadrilla_id).where(
                Integrante.user_id == user.id,
                Integrante.tenant_id == user.tenant_id,
            )
        )
        propia = row.scalar_one_or_none()
        return _Scope(nivel="propio", cuadrilla_ids=[propia] if propia else [])

    # Cualquier otro rol no tiene acceso a scorecards de desempeño.
    raise ForbiddenError("No tiene visibilidad sobre scorecards de desempeño")


def _scope_to_schema(scope: _Scope, user: User) -> ScorecardScope:
    return ScorecardScope(rol=user.role, nivel=scope.nivel, areas=scope.areas)


# ─────────────────────────────────────────────────────────────────────────────
# Agregaciones por cuadrilla
# ─────────────────────────────────────────────────────────────────────────────
async def _reportes_por_cuadrilla(
    user: User, db: AsyncSession, cuadrilla_ids: list[str] | None
) -> dict[str, dict]:
    """Volumen cerrado, tiempo medio y SLA de reportes, agrupado por cuadrilla."""
    filters = [Reporte.tenant_id == user.tenant_id, Reporte.cuadrilla_id.isnot(None)]
    if cuadrilla_ids is not None:
        filters.append(Reporte.cuadrilla_id.in_(cuadrilla_ids))

    q = (
        select(
            Reporte.cuadrilla_id.label("cid"),
            func.count(
                case((Reporte.estado.in_(ESTADOS_CERRADOS), Reporte.id))
            ).label("resueltos"),
            func.avg(
                case(
                    (Reporte.estado.in_(ESTADOS_CERRADOS), Reporte.tiempo_atencion_horas)
                )
            ).label("tiempo_medio"),
            func.count(
                case(
                    (
                        and_(
                            Reporte.estado.in_(ESTADOS_CERRADOS),
                            Reporte.tiempo_atencion_horas.isnot(None),
                        ),
                        Reporte.id,
                    )
                )
            ).label("sla_total"),
            func.count(
                case(
                    (
                        and_(
                            Reporte.estado.in_(ESTADOS_CERRADOS),
                            Reporte.tiempo_atencion_horas.isnot(None),
                            Reporte.tiempo_atencion_horas <= cast(SLA_CASE, Float),
                        ),
                        Reporte.id,
                    )
                )
            ).label("sla_dentro"),
        )
        .where(*filters)
        .group_by(Reporte.cuadrilla_id)
    )
    rows = (await db.execute(q)).all()
    return {
        r.cid: {
            "reportes_resueltos": r.resueltos or 0,
            "tiempo_medio_horas": round(float(r.tiempo_medio or 0), 1),
            "sla_total": r.sla_total or 0,
            "sla_dentro": r.sla_dentro or 0,
        }
        for r in rows
    }


async def _tareas_por_cuadrilla(
    user: User, db: AsyncSession, cuadrilla_ids: list[str] | None
) -> dict[str, dict]:
    """Tareas resueltas (cerradas) y tareas activas, agrupado por cuadrilla."""
    filters = [Tarea.tenant_id == user.tenant_id, Tarea.cuadrilla_id.isnot(None)]
    if cuadrilla_ids is not None:
        filters.append(Tarea.cuadrilla_id.in_(cuadrilla_ids))

    q = (
        select(
            Tarea.cuadrilla_id.label("cid"),
            func.count(case((Tarea.estado == "cerrada", Tarea.id))).label("resueltas"),
            func.count(
                case((Tarea.estado.in_(TAREA_ESTADOS_ACTIVOS), Tarea.id))
            ).label("activas"),
        )
        .where(*filters)
        .group_by(Tarea.cuadrilla_id)
    )
    rows = (await db.execute(q)).all()
    return {
        r.cid: {"tareas_resueltas": r.resueltas or 0, "tareas_activas": r.activas or 0}
        for r in rows
    }


async def _reaperturas_por_cuadrilla(
    user: User, db: AsyncSession, cuadrilla_ids: list[str] | None
) -> dict[str, int]:
    """Cuenta reportes reabiertos por cuadrilla (reincidencias).

    Heurística por ``ReporteEvento``: un reporte cuenta como reapertura si tiene
    un evento de cierre y, posteriormente, otro evento (no de creación/cierre),
    señal de que volvió a abrirse / requirió nueva intervención tras 'resuelto'.
    """
    cierre = func.min(
        case((ReporteEvento.tipo == "cierre", ReporteEvento.fecha))
    ).label("primer_cierre")
    ult_actividad = func.max(
        case(
            (ReporteEvento.tipo.notin_(("creacion", "cierre")), ReporteEvento.fecha)
        )
    ).label("ult_actividad")

    filters = [Reporte.tenant_id == user.tenant_id, Reporte.cuadrilla_id.isnot(None)]
    if cuadrilla_ids is not None:
        filters.append(Reporte.cuadrilla_id.in_(cuadrilla_ids))

    sub = (
        select(
            Reporte.id.label("rid"),
            Reporte.cuadrilla_id.label("cid"),
            cierre,
            ult_actividad,
        )
        .join(ReporteEvento, ReporteEvento.reporte_id == Reporte.id)
        .where(*filters)
        .group_by(Reporte.id, Reporte.cuadrilla_id)
    ).subquery()

    q = (
        select(sub.c.cid, func.count().label("reaperturas"))
        .where(
            sub.c.primer_cierre.isnot(None),
            sub.c.ult_actividad.isnot(None),
            sub.c.ult_actividad > sub.c.primer_cierre,
        )
        .group_by(sub.c.cid)
    )
    rows = (await db.execute(q)).all()
    return {r.cid: r.reaperturas or 0 for r in rows}


async def _capacidad_por_cuadrilla(
    user: User, db: AsyncSession, cuadrilla_ids: list[str] | None
) -> dict[str, int]:
    """Capacidad = nº de integrantes activos (personas) por cuadrilla."""
    filters = [Integrante.tenant_id == user.tenant_id, Integrante.activo.is_(True)]
    if cuadrilla_ids is not None:
        filters.append(Integrante.cuadrilla_id.in_(cuadrilla_ids))
    q = (
        select(Integrante.cuadrilla_id, func.count().label("n"))
        .where(*filters)
        .group_by(Integrante.cuadrilla_id)
    )
    rows = (await db.execute(q)).all()
    return {r.cuadrilla_id: r.n or 0 for r in rows}


def _ensamblar_metricas(
    rep: dict, tar: dict, reaperturas: int, capacidad: int
) -> ScorecardMetricas:
    reportes_resueltos = rep.get("reportes_resueltos", 0)
    tareas_resueltas = tar.get("tareas_resueltas", 0)
    tareas_activas = tar.get("tareas_activas", 0)
    sla_total = rep.get("sla_total", 0)
    sla_dentro = rep.get("sla_dentro", 0)

    sla_pct = round(sla_dentro / sla_total * 100, 1) if sla_total else 0.0
    carga_pct = round(tareas_activas / capacidad * 100, 1) if capacidad else 0.0
    reincidencia_pct = (
        round(reaperturas / reportes_resueltos * 100, 1) if reportes_resueltos else 0.0
    )

    return ScorecardMetricas(
        reportes_resueltos=reportes_resueltos,
        tareas_resueltas=tareas_resueltas,
        resueltos_total=reportes_resueltos + tareas_resueltas,
        tiempo_medio_horas=rep.get("tiempo_medio_horas", 0.0),
        sla_cumplimiento_pct=sla_pct,
        sla_dentro=sla_dentro,
        sla_total=sla_total,
        tareas_activas=tareas_activas,
        capacidad=capacidad,
        carga_pct=carga_pct,
        reaperturas=reaperturas,
        reincidencia_pct=reincidencia_pct,
    )


# ─────────────────────────────────────────────────────────────────────────────
# API pública del servicio
# ─────────────────────────────────────────────────────────────────────────────
async def scorecards_cuadrillas(
    user: User, db: AsyncSession
) -> tuple[list[CuadrillaScorecard], ScorecardScope]:
    """Scorecards de TODAS las cuadrillas visibles para el usuario."""
    scope = await _visibilidad(user, db)
    if scope.cuadrilla_ids is not None and not scope.cuadrilla_ids:
        return [], _scope_to_schema(scope, user)

    cards = await _build_cuadrilla_cards(user, db, scope.cuadrilla_ids)
    return cards, _scope_to_schema(scope, user)


async def scorecard_cuadrilla(
    cuadrilla_id: str, user: User, db: AsyncSession
) -> CuadrillaScorecard:
    """Scorecard de UNA cuadrilla, validando que el usuario pueda verla."""
    scope = await _visibilidad(user, db)
    if scope.cuadrilla_ids is not None and cuadrilla_id not in scope.cuadrilla_ids:
        raise ForbiddenError("No tiene visibilidad sobre esta cuadrilla")

    cards = await _build_cuadrilla_cards(user, db, [cuadrilla_id])
    if not cards:
        # La cuadrilla no existe en el tenant (o no tiene datos): card vacía si existe.
        existe = await db.execute(
            select(Cuadrilla).where(
                Cuadrilla.id == cuadrilla_id, Cuadrilla.tenant_id == user.tenant_id
            )
        )
        c = existe.scalar_one_or_none()
        if c is None:
            raise NotFoundError("Cuadrilla", cuadrilla_id)
        return CuadrillaScorecard(
            cuadrilla_id=c.id,
            nombre=c.nombre,
            integrantes=0,
            metricas=ScorecardMetricas(),
        )
    return cards[0]


async def _build_cuadrilla_cards(
    user: User, db: AsyncSession, cuadrilla_ids: list[str] | None
) -> list[CuadrillaScorecard]:
    # Nombres de las cuadrillas en alcance.
    cua_q = select(Cuadrilla.id, Cuadrilla.nombre).where(
        Cuadrilla.tenant_id == user.tenant_id
    )
    if cuadrilla_ids is not None:
        cua_q = cua_q.where(Cuadrilla.id.in_(cuadrilla_ids))
    cuadrillas = {r.id: r.nombre for r in (await db.execute(cua_q)).all()}
    if not cuadrillas:
        return []

    ids = list(cuadrillas.keys())
    rep = await _reportes_por_cuadrilla(user, db, ids)
    tar = await _tareas_por_cuadrilla(user, db, ids)
    reap = await _reaperturas_por_cuadrilla(user, db, ids)
    cap = await _capacidad_por_cuadrilla(user, db, ids)

    cards = [
        CuadrillaScorecard(
            cuadrilla_id=cid,
            nombre=nombre,
            integrantes=cap.get(cid, 0),
            metricas=_ensamblar_metricas(
                rep.get(cid, {}), tar.get(cid, {}), reap.get(cid, 0), cap.get(cid, 0)
            ),
        )
        for cid, nombre in cuadrillas.items()
    ]
    # Orden por volumen resuelto desc (más productivas primero), como ranking.
    cards.sort(key=lambda c: c.metricas.resueltos_total, reverse=True)
    return cards


# ─────────────────────────────────────────────────────────────────────────────
# Scorecards por persona (integrante)
# ─────────────────────────────────────────────────────────────────────────────
async def _tareas_por_integrante(
    user: User, db: AsyncSession, integrante_ids: list[str]
) -> dict[str, dict]:
    """Tareas resueltas / activas, agrupado por integrante."""
    q = (
        select(
            Tarea.integrante_id.label("iid"),
            func.count(case((Tarea.estado == "cerrada", Tarea.id))).label("resueltas"),
            func.count(
                case((Tarea.estado.in_(TAREA_ESTADOS_ACTIVOS), Tarea.id))
            ).label("activas"),
        )
        .where(
            Tarea.tenant_id == user.tenant_id,
            Tarea.integrante_id.in_(integrante_ids),
        )
        .group_by(Tarea.integrante_id)
    )
    rows = (await db.execute(q)).all()
    return {
        r.iid: {"tareas_resueltas": r.resueltas or 0, "tareas_activas": r.activas or 0}
        for r in rows
    }


async def _reportes_por_integrante(
    user: User, db: AsyncSession, integrante_ids: list[str]
) -> dict[str, dict]:
    """Reportes cerrados / tiempo medio / SLA atribuidos a la persona vía Tarea.

    Un reporte se atribuye a un integrante cuando existe una Tarea con
    ``integrante_id`` y ``reporte_id`` que lo enlaza (el trabajo de campo real).
    """
    q = (
        select(
            Tarea.integrante_id.label("iid"),
            # DISTINCT sobre reporte.id: una persona puede tener varias tareas que
            # apuntan al mismo reporte; no debe contarse dos veces.
            func.count(
                distinct(
                    case((Reporte.estado.in_(ESTADOS_CERRADOS), Reporte.id))
                )
            ).label("resueltos"),
            func.avg(
                case(
                    (Reporte.estado.in_(ESTADOS_CERRADOS), Reporte.tiempo_atencion_horas)
                )
            ).label("tiempo_medio"),
            func.count(
                distinct(
                    case(
                        (
                            and_(
                                Reporte.estado.in_(ESTADOS_CERRADOS),
                                Reporte.tiempo_atencion_horas.isnot(None),
                            ),
                            Reporte.id,
                        )
                    )
                )
            ).label("sla_total"),
            func.count(
                distinct(
                    case(
                        (
                            and_(
                                Reporte.estado.in_(ESTADOS_CERRADOS),
                                Reporte.tiempo_atencion_horas.isnot(None),
                                Reporte.tiempo_atencion_horas <= cast(SLA_CASE, Float),
                            ),
                            Reporte.id,
                        )
                    )
                )
            ).label("sla_dentro"),
        )
        .join(Reporte, Reporte.id == Tarea.reporte_id)
        .where(
            Tarea.tenant_id == user.tenant_id,
            Tarea.integrante_id.in_(integrante_ids),
            Tarea.reporte_id.isnot(None),
        )
        .group_by(Tarea.integrante_id)
    )
    rows = (await db.execute(q)).all()
    return {
        r.iid: {
            "reportes_resueltos": r.resueltos or 0,
            "tiempo_medio_horas": round(float(r.tiempo_medio or 0), 1),
            "sla_total": r.sla_total or 0,
            "sla_dentro": r.sla_dentro or 0,
        }
        for r in rows
    }


async def scorecards_personal(
    user: User, db: AsyncSession
) -> tuple[list[PersonaScorecard], ScorecardScope]:
    """Scorecards por persona (integrante) según la visibilidad del usuario.

    * admin → todo el personal del tenant.
    * director/supervisor → personal de las cuadrillas de su área.
    * jefe_cuadrilla/inspector → personal de SU cuadrilla (incluye su propia card).
    """
    scope = await _visibilidad(user, db)
    if scope.cuadrilla_ids is not None and not scope.cuadrilla_ids:
        return [], _scope_to_schema(scope, user)

    # Integrantes en alcance (activos), con nombre de su cuadrilla.
    int_q = (
        select(Integrante, Cuadrilla.nombre.label("cua_nombre"))
        .join(Cuadrilla, Cuadrilla.id == Integrante.cuadrilla_id)
        .where(Integrante.tenant_id == user.tenant_id, Integrante.activo.is_(True))
    )
    if scope.cuadrilla_ids is not None:
        int_q = int_q.where(Integrante.cuadrilla_id.in_(scope.cuadrilla_ids))
    rows = (await db.execute(int_q)).all()
    integrantes = [(r[0], r.cua_nombre) for r in rows]
    if not integrantes:
        return [], _scope_to_schema(scope, user)

    ids = [i.id for i, _ in integrantes]
    tar = await _tareas_por_integrante(user, db, ids)
    rep = await _reportes_por_integrante(user, db, ids)

    cards = [
        PersonaScorecard(
            integrante_id=i.id,
            nombre=i.nombre,
            rol_campo=i.rol_campo,
            cuadrilla_id=i.cuadrilla_id,
            cuadrilla_nombre=cua_nombre,
            user_id=i.user_id,
            metricas=_ensamblar_metricas(
                rep.get(i.id, {}),
                tar.get(i.id, {}),
                # Reincidencia individual no se atribuye por persona (se mide a nivel
                # cuadrilla); se deja en 0 para no imputar reaperturas a una persona.
                0,
                # Capacidad por persona = 1 (una persona).
                1,
            ),
        )
        for i, cua_nombre in integrantes
    ]
    cards.sort(key=lambda c: c.metricas.resueltos_total, reverse=True)
    return cards, _scope_to_schema(scope, user)
