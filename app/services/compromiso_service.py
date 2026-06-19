"""Servicio de Compromisos de gobierno (metas públicas con avance medible).

CRUD + seguimiento agregado. Aislado por ``tenant_id`` (derivado del JWT). El
Agente Ejecutivo consume estos datos para reportar cumplimiento al Alcalde con
visión CROSS-DIRECCIONES (sin acotar por área).
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditLogger
from app.core.exceptions import NotFoundError
from app.models.categoria import Categoria
from app.models.compromiso import Compromiso
from app.schemas.ejecutivo import (
    CompromisoCreate,
    CompromisoOut,
    CompromisosResumen,
    CompromisoUpdate,
)

# Umbral (días) bajo el cual un compromiso no cumplido se marca "en riesgo".
_RIESGO_DIAS = 14
ESTADOS_CERRADOS = ("cumplido",)


async def _labels_areas(tenant_id: str, db: AsyncSession) -> dict[str, str]:
    """Mapa area_id -> label (categoría). Tolerante: las áreas son globales."""
    rows = await db.execute(select(Categoria.id, Categoria.label))
    return {r.id: r.label for r in rows.all()}


def _to_out(c: Compromiso, labels: dict[str, str], now: datetime) -> CompromisoOut:
    dias_restantes: int | None = None
    if c.fecha_objetivo is not None:
        objetivo = c.fecha_objetivo
        if objetivo.tzinfo is None:
            objetivo = objetivo.replace(tzinfo=UTC)
        dias_restantes = (objetivo - now).days

    no_cumplido = c.estado != "cumplido"
    en_riesgo = no_cumplido and (
        c.estado in ("en_riesgo", "retrasado")
        or (dias_restantes is not None and dias_restantes < 0)
        or (
            dias_restantes is not None
            and dias_restantes <= _RIESGO_DIAS
            and (c.avance_pct or 0) < 80
        )
    )

    return CompromisoOut(
        id=c.id,
        titulo=c.titulo,
        descripcion=c.descripcion,
        area_id=c.area_id,
        area_label=labels.get(c.area_id) if c.area_id else None,
        meta=c.meta,
        avance_pct=c.avance_pct or 0,
        estado=c.estado,  # type: ignore[arg-type]
        fecha_objetivo=c.fecha_objetivo,
        dias_restantes=dias_restantes,
        en_riesgo=en_riesgo,
        created_at=c.created_at,
    )


# ─── CRUD ────────────────────────────────────────────────────────────────────


async def list_compromisos(
    tenant_id: str,
    db: AsyncSession,
    *,
    estado: str | None = None,
    area_id: str | None = None,
) -> list[CompromisoOut]:
    filters = [Compromiso.tenant_id == tenant_id]
    if estado:
        filters.append(Compromiso.estado == estado)
    if area_id:
        filters.append(Compromiso.area_id == area_id)

    result = await db.execute(
        select(Compromiso)
        .where(*filters)
        .order_by(Compromiso.fecha_objetivo.asc().nulls_last(), Compromiso.created_at.desc())
    )
    rows = list(result.scalars().all())
    labels = await _labels_areas(tenant_id, db)
    now = datetime.now(UTC)
    return [_to_out(c, labels, now) for c in rows]


async def get_compromiso(compromiso_id: str, tenant_id: str, db: AsyncSession) -> CompromisoOut:
    c = await _fetch(compromiso_id, tenant_id, db)
    labels = await _labels_areas(tenant_id, db)
    return _to_out(c, labels, datetime.now(UTC))


async def create_compromiso(
    data: CompromisoCreate,
    tenant_id: str,
    db: AsyncSession,
    audit: AuditLogger,
    user_id: str,
) -> CompromisoOut:
    c = Compromiso(
        tenant_id=tenant_id,
        titulo=data.titulo,
        descripcion=data.descripcion,
        area_id=data.area_id,
        meta=data.meta,
        avance_pct=data.avance_pct,
        estado=data.estado,
        fecha_objetivo=data.fecha_objetivo,
    )
    db.add(c)
    await db.flush()
    await audit.log(
        action="create",
        user_id=user_id,
        tenant_id=tenant_id,
        entity_type="compromiso",
        entity_id=c.id,
    )
    labels = await _labels_areas(tenant_id, db)
    return _to_out(c, labels, datetime.now(UTC))


async def update_compromiso(
    compromiso_id: str,
    data: CompromisoUpdate,
    tenant_id: str,
    db: AsyncSession,
    audit: AuditLogger,
    user_id: str,
) -> CompromisoOut:
    c = await _fetch(compromiso_id, tenant_id, db)

    if data.titulo is not None:
        c.titulo = data.titulo
    if data.descripcion is not None:
        c.descripcion = data.descripcion
    if data.area_id is not None:
        c.area_id = data.area_id
    if data.meta is not None:
        c.meta = data.meta
    if data.avance_pct is not None:
        c.avance_pct = data.avance_pct
    if data.estado is not None:
        c.estado = data.estado
    if data.fecha_objetivo is not None:
        c.fecha_objetivo = data.fecha_objetivo

    await db.flush()
    await audit.log(
        action="update",
        user_id=user_id,
        tenant_id=tenant_id,
        entity_type="compromiso",
        entity_id=c.id,
    )
    labels = await _labels_areas(tenant_id, db)
    return _to_out(c, labels, datetime.now(UTC))


async def _fetch(compromiso_id: str, tenant_id: str, db: AsyncSession) -> Compromiso:
    result = await db.execute(
        select(Compromiso).where(
            Compromiso.id == compromiso_id, Compromiso.tenant_id == tenant_id
        )
    )
    c = result.scalar_one_or_none()
    if c is None:
        raise NotFoundError("Compromiso", compromiso_id)
    return c


# ─── Seguimiento agregado ────────────────────────────────────────────────────


async def resumen_compromisos(tenant_id: str, db: AsyncSession) -> CompromisosResumen:
    """Agrega el estado de cumplimiento de TODOS los compromisos del tenant."""
    items = await list_compromisos(tenant_id, db)
    total = len(items)
    if total == 0:
        return CompromisosResumen()

    cumplidos = sum(1 for i in items if i.estado == "cumplido")
    en_progreso = sum(1 for i in items if i.estado == "en_progreso" and not i.en_riesgo)
    en_riesgo = sum(1 for i in items if i.en_riesgo and i.estado != "cumplido")
    retrasados = sum(1 for i in items if i.estado == "retrasado")
    avance_promedio = round(sum(i.avance_pct for i in items) / total, 1)
    pct_cumplimiento = round(cumplidos / total * 100, 1)

    return CompromisosResumen(
        total=total,
        cumplidos=cumplidos,
        en_progreso=en_progreso,
        en_riesgo=en_riesgo,
        retrasados=retrasados,
        avance_promedio=avance_promedio,
        pct_cumplimiento=pct_cumplimiento,
        items=items,
    )
