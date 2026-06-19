"""Tablero financiero ejecutivo (REQ-16).

Consolida el presupuesto de obra pública en tres líneas comparables —AUTORIZADO,
EJERCIDO y COMPROMETIDO— y cruza el avance FÍSICO contra el avance FINANCIERO para
detectar desfases. Todo se calcula con agregaciones SQL sobre :class:`Obra`,
:class:`ObraPresupuestoItem` y :class:`ObraCategoria`, en línea con
``stats_service``.

Aislamiento multi-tenant y por área
-----------------------------------
El tenant SIEMPRE proviene del JWT. Para un director (rol != ``admin``) se reusa la
misma política fail-closed de ``obra_service``: sus áreas (categorías de reporte)
se mapean a categorías de obra y solo agregan sobre ese subconjunto. Un director sin
áreas mapeables no ve ninguna obra (``.in_([])`` => predicado siempre-falso).

Heurística del COMPROMETIDO
---------------------------
"Comprometido" = recursos amarrados a un contrato/obra viva que todavía no se
devengan. No existe una tabla de contratos, así que se define explícitamente:

  comprometido(obra) =
      max(autorizado - ejercido, 0)              si la obra está EN EJECUCIÓN
      0                                          en cualquier otro estado

Una obra "en ejecución" (``_ESTADOS_ACTIVOS``) tiene su techo autorizado amarrado:
lo ya ejercido es gasto consumado y el resto queda comprometido hasta cerrarse. Las
obras en planeación aún no comprometen techo y las concluidas/canceladas ya no. Se
acota con ``max(..., 0)`` para que un sobreejercicio (ejercido > autorizado) no
genere un comprometido negativo.

  disponible(obra) = max(autorizado - ejercido - comprometido, 0)

que para obras activas tiende a 0 (todo el techo está ejercido o comprometido) y
para obras en planeación equivale al techo completo aún libre.
"""

from decimal import Decimal

from sqlalchemy import Select, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.categoria import ObraCategoria
from app.models.obra import Obra
from app.models.user import User
from app.schemas.financiero import (
    AlertaFinanciera,
    DireccionFinanciero,
    ProyectoFinanciero,
    ResumenFinanciero,
)
from app.services.obra_service import _apply_tenant_and_area_filter

# Obras cuyo techo autorizado se considera "comprometido" (en ejecución).
_ESTADOS_ACTIVOS = ("en_proceso", "en_ejecucion")

# Umbral (en puntos porcentuales) a partir del cual el avance financiero que supera
# al físico se considera riesgo: se está gastando más rápido de lo que se construye.
_RIESGO_DESFASE_PP = 20.0
_RIESGO_ALTO_DESFASE_PP = 40.0

# Proporción del techo comprometido (sin ejercer) que dispara alerta informativa.
_COMPROMETIDO_ALTO_PCT = 80.0

_ZERO = Decimal("0")


def _pct(num: Decimal | float, den: Decimal | float) -> float:
    """Porcentaje seguro ``num/den*100`` redondeado a 1 decimal (0 si ``den``=0)."""
    den = float(den or 0)
    if den == 0:
        return 0.0
    return round(float(num) / den * 100, 1)


def _comprometido(autorizado: Decimal, ejercido: Decimal, estado: str) -> Decimal:
    """Comprometido de una obra según la heurística documentada en el módulo."""
    if estado in _ESTADOS_ACTIVOS:
        saldo = autorizado - ejercido
        return saldo if saldo > _ZERO else _ZERO
    return _ZERO


def _nivel_riesgo(avance_fisico: int, avance_financiero: float, sobreejercido: bool) -> str:
    """Clasifica el riesgo de una obra a partir del desfase físico/financiero."""
    if sobreejercido:
        return "alto"
    desfase = avance_financiero - avance_fisico
    if desfase >= _RIESGO_ALTO_DESFASE_PP:
        return "alto"
    if desfase >= _RIESGO_DESFASE_PP:
        return "medio"
    if desfase >= _RIESGO_DESFASE_PP / 2:
        return "bajo"
    return "ninguno"


def _select_obras(user: User) -> Select:
    """SELECT de obras visibles por el usuario con tenant + área aplicados."""
    stmt = select(
        Obra.id,
        Obra.folio,
        Obra.nombre,
        Obra.categoria_id,
        Obra.estado,
        Obra.avance_pct,
        func.coalesce(Obra.presupuesto_autorizado, 0).label("autorizado"),
        func.coalesce(Obra.presupuesto_ejercido, 0).label("ejercido"),
    )
    return _apply_tenant_and_area_filter(stmt, user)


async def resumen(user: User, db: AsyncSession) -> ResumenFinanciero:
    """Consolidado global: autorizado vs ejercido vs comprometido + cruce de avance.

    El avance físico se pondera por el techo autorizado de cada obra (una obra de
    100 M pesa más que una de 1 M), de modo que sea comparable contra el avance
    financiero global (ejercido/autorizado).
    """
    rows = (await db.execute(_select_obras(user))).all()

    autorizado = _ZERO
    ejercido = _ZERO
    comprometido = _ZERO
    avance_pond_num = 0.0  # Σ avance_fisico * autorizado
    activas = 0
    sobreejercidas = 0
    en_riesgo = 0

    for r in rows:
        aut = Decimal(r.autorizado)
        eje = Decimal(r.ejercido)
        autorizado += aut
        ejercido += eje
        comprometido += _comprometido(aut, eje, r.estado)
        avance_pond_num += r.avance_pct * float(aut)
        if r.estado in _ESTADOS_ACTIVOS:
            activas += 1
        if eje > aut and aut > _ZERO:
            sobreejercidas += 1
        af = _pct(eje, aut)
        if (af - r.avance_pct) >= _RIESGO_DESFASE_PP or (eje > aut and aut > _ZERO):
            en_riesgo += 1

    avance_financiero = _pct(ejercido, autorizado)
    avance_fisico_pond = (
        round(avance_pond_num / float(autorizado), 1) if autorizado > _ZERO else 0.0
    )
    disponible = autorizado - ejercido - comprometido
    if disponible < _ZERO:
        disponible = _ZERO

    return ResumenFinanciero(
        autorizado=autorizado,
        ejercido=ejercido,
        comprometido=comprometido,
        disponible=disponible,
        pct_ejercido=avance_financiero,
        pct_comprometido=_pct(comprometido, autorizado),
        avance_fisico_pond=avance_fisico_pond,
        avance_financiero=avance_financiero,
        desfase_pp=round(avance_financiero - avance_fisico_pond, 1),
        total_obras=len(rows),
        obras_activas=activas,
        obras_sobreejercidas=sobreejercidas,
        obras_en_riesgo=en_riesgo,
    )


async def por_direccion(user: User, db: AsyncSession) -> list[DireccionFinanciero]:
    """Consolidado por dirección (categoría de obra), ordenado por techo autorizado.

    El comprometido se agrega vía ``CASE`` en SQL (mismo criterio que la heurística):
    solo las obras en ejecución suman su saldo no ejercido.
    """
    base = _select_obras(user).subquery()
    activo = base.c.estado.in_(_ESTADOS_ACTIVOS)
    saldo = base.c.autorizado - base.c.ejercido

    q = (
        select(
            base.c.categoria_id,
            ObraCategoria.label,
            ObraCategoria.color,
            func.sum(base.c.autorizado).label("autorizado"),
            func.sum(base.c.ejercido).label("ejercido"),
            func.sum(
                case((activo & (saldo > 0), saldo), else_=0)
            ).label("comprometido"),
            func.sum(base.c.avance_pct * base.c.autorizado).label("avance_pond_num"),
            func.count().label("total_obras"),
        )
        .join(ObraCategoria, base.c.categoria_id == ObraCategoria.id)
        .group_by(base.c.categoria_id, ObraCategoria.label, ObraCategoria.color)
        .order_by(func.sum(base.c.autorizado).desc())
    )
    rows = (await db.execute(q)).all()

    out: list[DireccionFinanciero] = []
    for r in rows:
        aut = Decimal(r.autorizado or 0)
        eje = Decimal(r.ejercido or 0)
        comp = Decimal(r.comprometido or 0)
        disponible = aut - eje - comp
        if disponible < _ZERO:
            disponible = _ZERO
        avance_financiero = _pct(eje, aut)
        avance_fisico = round(float(r.avance_pond_num or 0) / float(aut), 1) if aut > _ZERO else 0.0
        out.append(
            DireccionFinanciero(
                categoria_id=r.categoria_id,
                label=r.label,
                color=r.color,
                autorizado=aut,
                ejercido=eje,
                comprometido=comp,
                disponible=disponible,
                pct_ejercido=avance_financiero,
                avance_fisico_pond=avance_fisico,
                avance_financiero=avance_financiero,
                desfase_pp=round(avance_financiero - avance_fisico, 1),
                total_obras=r.total_obras,
            )
        )
    return out


def _proyecto_from_row(r) -> ProyectoFinanciero:
    """Construye la línea financiera de una obra a partir de una fila del SELECT."""
    aut = Decimal(r.autorizado)
    eje = Decimal(r.ejercido)
    comp = _comprometido(aut, eje, r.estado)
    disponible = aut - eje - comp
    if disponible < _ZERO:
        disponible = _ZERO
    avance_financiero = _pct(eje, aut)
    sobreejercido = eje > aut and aut > _ZERO
    return ProyectoFinanciero(
        obra_id=r.id,
        folio=r.folio,
        nombre=r.nombre,
        categoria_id=r.categoria_id,
        estado=r.estado,
        autorizado=aut,
        ejercido=eje,
        comprometido=comp,
        disponible=disponible,
        pct_ejercido=avance_financiero,
        avance_fisico=r.avance_pct,
        avance_financiero=avance_financiero,
        desfase_pp=round(avance_financiero - r.avance_pct, 1),
        nivel_riesgo=_nivel_riesgo(r.avance_pct, avance_financiero, sobreejercido),
    )


async def proyectos_en_riesgo(user: User, db: AsyncSession) -> list[ProyectoFinanciero]:
    """Obras donde el gasto va muy por delante de la obra física o hay sobreejercicio.

    Criterio de riesgo (cualquiera dispara): sobreejercicio (ejercido > autorizado)
    o desfase financiero-físico >= ``_RIESGO_DESFASE_PP``. Se ordena de mayor a menor
    desfase para que el director ataque primero lo más expuesto.
    """
    rows = (await db.execute(_select_obras(user))).all()
    proyectos = [_proyecto_from_row(r) for r in rows]
    en_riesgo = [
        p
        for p in proyectos
        if p.nivel_riesgo in ("medio", "alto")
        or (p.ejercido > p.autorizado and p.autorizado > _ZERO)
    ]
    en_riesgo.sort(key=lambda p: p.desfase_pp, reverse=True)
    return en_riesgo


async def alertas(user: User, db: AsyncSession) -> list[AlertaFinanciera]:
    """Alertas de control presupuestal calculadas en vivo (sin persistencia).

    Tres familias:
      - ``sobreejercicio``      ejercido > autorizado (rebasó el techo aprobado).
      - ``riesgo_avance``       avance financiero supera al físico por encima del
                                umbral (se gasta más rápido de lo que se construye).
      - ``comprometido_alto``   obra en ejecución con >80 % del techo comprometido
                                (saldo no ejercido) y avance físico todavía bajo.
    """
    rows = (await db.execute(_select_obras(user))).all()
    out: list[AlertaFinanciera] = []

    for r in rows:
        aut = Decimal(r.autorizado)
        eje = Decimal(r.ejercido)
        af = _pct(eje, aut)
        desfase = af - r.avance_pct

        if eje > aut and aut > _ZERO:
            sobre = eje - aut
            out.append(
                AlertaFinanciera(
                    tipo="sobreejercicio",
                    severidad="alta",
                    obra_id=r.id,
                    folio=r.folio,
                    nombre=r.nombre,
                    titulo=f"Sobreejercicio: {r.nombre}",
                    detalle=(
                        f"Ejercido ${eje:,.0f} supera el autorizado ${aut:,.0f} "
                        f"(+${sobre:,.0f}, {af:.0f}% del techo)."
                    ),
                    autorizado=aut,
                    ejercido=eje,
                    avance_fisico=r.avance_pct,
                    avance_financiero=af,
                )
            )
        elif desfase >= _RIESGO_DESFASE_PP:
            out.append(
                AlertaFinanciera(
                    tipo="riesgo_avance",
                    severidad="alta" if desfase >= _RIESGO_ALTO_DESFASE_PP else "media",
                    obra_id=r.id,
                    folio=r.folio,
                    nombre=r.nombre,
                    titulo=f"Avance financiero adelantado: {r.nombre}",
                    detalle=(
                        f"Financiero {af:.0f}% vs físico {r.avance_pct}% "
                        f"(desfase {desfase:.0f} pp)."
                    ),
                    autorizado=aut,
                    ejercido=eje,
                    avance_fisico=r.avance_pct,
                    avance_financiero=af,
                )
            )

        if r.estado in _ESTADOS_ACTIVOS and aut > _ZERO:
            comp = _comprometido(aut, eje, r.estado)
            pct_comp = _pct(comp, aut)
            if pct_comp >= _COMPROMETIDO_ALTO_PCT and r.avance_pct < 50:
                out.append(
                    AlertaFinanciera(
                        tipo="comprometido_alto",
                        severidad="media",
                        obra_id=r.id,
                        folio=r.folio,
                        nombre=r.nombre,
                        titulo=f"Techo comprometido al {pct_comp:.0f}%: {r.nombre}",
                        detalle=(
                            f"${comp:,.0f} comprometidos sin ejercer con avance "
                            f"físico de solo {r.avance_pct}%."
                        ),
                        autorizado=aut,
                        ejercido=eje,
                        avance_fisico=r.avance_pct,
                        avance_financiero=af,
                    )
                )

    # Sobreejercicio primero, luego mayor desfase financiero-físico.
    _orden = {"alta": 0, "media": 1, "baja": 2}
    out.sort(key=lambda a: (_orden.get(a.severidad, 3), -(a.avance_financiero - a.avance_fisico)))
    return out
