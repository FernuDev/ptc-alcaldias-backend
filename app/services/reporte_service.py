import math
import uuid
from datetime import datetime, timezone

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditLogger, compute_changes
from app.core.exceptions import NotFoundError
from app.models.colonia import Colonia
from app.models.reporte import Reporte, ReporteEvidencia, ReporteEvento
from app.models.user import User
from app.schemas.common import PaginatedResponse
from app.schemas.reporte import (
    EvidenciaCreate,
    EventoCreate,
    ReporteCreate,
    ReporteRead,
    ReporteUpdate,
)

# Category mapping: director areas -> obra categories they can also see
CATEGORIA_TO_OBRA = {
    "bacheo": ["pavimentacion", "vialidad"],
    "agua": ["agua_potable", "drenaje"],
    "drenaje": ["drenaje"],
    "alumbrado": ["alumbrado"],
    "semaforos": ["alumbrado"],
    "parques": ["parques"],
    "arboles": ["parques"],
    "limpia": ["imagen_urbana"],
    "comercio_vp": ["imagen_urbana"],
    "seguridad": [],
}


def _apply_tenant_and_area_filter(
    stmt: Select, user: User
) -> Select:
    stmt = stmt.where(Reporte.tenant_id == user.tenant_id)
    if user.role != "admin" and user.areas:
        area_ids = [a.id for a in user.areas]
        stmt = stmt.where(Reporte.categoria_id.in_(area_ids))
    return stmt


async def list_reportes(
    user: User,
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    sort_by: str = "fecha_creacion",
    sort_dir: str = "desc",
    search: str | None = None,
    categorias: list[str] | None = None,
    estados: list[str] | None = None,
    prioridades: list[str] | None = None,
    fuentes: list[str] | None = None,
    colonia_ids: list[str] | None = None,
) -> PaginatedResponse[ReporteRead]:
    stmt = select(Reporte)
    stmt = _apply_tenant_and_area_filter(stmt, user)

    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            Reporte.titulo.ilike(pattern)
            | Reporte.folio.ilike(pattern)
            | Reporte.colonia_nombre.ilike(pattern)
        )
    if categorias:
        stmt = stmt.where(Reporte.categoria_id.in_(categorias))
    if estados:
        stmt = stmt.where(Reporte.estado.in_(estados))
    if prioridades:
        stmt = stmt.where(Reporte.prioridad.in_(prioridades))
    if fuentes:
        stmt = stmt.where(Reporte.fuente.in_(fuentes))
    if colonia_ids:
        stmt = stmt.where(Reporte.colonia_id.in_(colonia_ids))

    # Count
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    # Sort
    sort_col = getattr(Reporte, sort_by, Reporte.fecha_creacion)
    stmt = stmt.order_by(sort_col.desc() if sort_dir == "desc" else sort_col.asc())

    # Paginate
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    reportes = list(result.scalars().all())

    items = []
    for r in reportes:
        items.append(ReporteRead(
            id=r.id,
            tenant_id=r.tenant_id,
            folio=r.folio,
            categoria_id=r.categoria_id,
            estado=r.estado,
            prioridad=r.prioridad,
            fuente=r.fuente,
            cuadrilla_id=r.cuadrilla_id,
            colonia_id=r.colonia_id,
            colonia_nombre=r.colonia_nombre,
            lng=r.lng,
            lat=r.lat,
            peso=r.peso,
            titulo=r.titulo,
            descripcion=r.descripcion,
            ciudadano_nombre=r.ciudadano_nombre,
            ciudadano_iniciales=r.ciudadano_iniciales,
            fecha_creacion=r.fecha_creacion,
            fecha_actualizacion=r.fecha_actualizacion,
            fecha_cierre=r.fecha_cierre,
            tiempo_atencion_horas=r.tiempo_atencion_horas,
            costo_estimado=r.costo_estimado,
            gasto_real=r.gasto_real,
            obras_relacionadas_ids=[o.id for o in r.obras_relacionadas],
        ))

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=math.ceil(total / page_size) if page_size else 1,
    )


async def get_reporte(reporte_id: str, user: User, db: AsyncSession) -> ReporteRead:
    stmt = select(Reporte).where(Reporte.id == reporte_id)
    stmt = _apply_tenant_and_area_filter(stmt, user)
    result = await db.execute(stmt)
    r = result.scalar_one_or_none()
    if r is None:
        raise NotFoundError("Reporte", reporte_id)

    return ReporteRead.model_validate(r)


async def create_reporte(
    data: ReporteCreate,
    user: User,
    db: AsyncSession,
    audit: AuditLogger,
) -> Reporte:
    # Get colonia name
    col_result = await db.execute(select(Colonia).where(Colonia.id == data.colonia_id))
    colonia = col_result.scalar_one_or_none()
    colonia_nombre = colonia.nombre if colonia else None

    # Generate folio
    count_result = await db.execute(
        select(func.count()).select_from(Reporte).where(Reporte.tenant_id == user.tenant_id)
    )
    count = (count_result.scalar() or 0) + 1
    acronimo = user.tenant_id.split("-")[0][:2].upper()
    if user.tenant_id == "magdalena-contreras":
        acronimo = "MC"
    elif user.tenant_id == "tlalpan":
        acronimo = "TL"
    folio = f"{acronimo}-RC-{count:04d}"
    reporte_id = f"{acronimo}-RC-{count:04d}"

    now = datetime.now(timezone.utc)
    reporte = Reporte(
        id=reporte_id,
        tenant_id=user.tenant_id,
        folio=folio,
        categoria_id=data.categoria_id,
        estado="nuevo",
        prioridad=data.prioridad,
        fuente=data.fuente,
        colonia_id=data.colonia_id,
        colonia_nombre=colonia_nombre,
        lng=data.lng,
        lat=data.lat,
        peso=1,
        titulo=data.titulo,
        descripcion=data.descripcion,
        ciudadano_nombre=data.ciudadano_nombre,
        ciudadano_iniciales=data.ciudadano_iniciales,
        fecha_creacion=now,
        fecha_actualizacion=now,
    )
    db.add(reporte)
    await db.flush()

    # Add creation event
    evt = ReporteEvento(
        id=f"{reporte_id}-ev-001",
        reporte_id=reporte_id,
        fecha=now,
        tipo="creacion",
        titulo="Reporte creado",
        autor_nombre=user.nombre,
        autor_iniciales=user.iniciales,
        autor_rol=user.cargo,
    )
    db.add(evt)

    await audit.log(
        action="create",
        user_id=user.id,
        tenant_id=user.tenant_id,
        entity_type="reporte",
        entity_id=reporte_id,
    )

    return reporte


async def update_reporte(
    reporte_id: str,
    data: ReporteUpdate,
    user: User,
    db: AsyncSession,
    audit: AuditLogger,
) -> Reporte:
    stmt = select(Reporte).where(Reporte.id == reporte_id, Reporte.tenant_id == user.tenant_id)
    result = await db.execute(stmt)
    reporte = result.scalar_one_or_none()
    if reporte is None:
        raise NotFoundError("Reporte", reporte_id)

    old = {
        "estado": reporte.estado,
        "prioridad": reporte.prioridad,
        "cuadrilla_id": reporte.cuadrilla_id,
    }

    if data.estado is not None:
        reporte.estado = data.estado
        if data.estado in ("resuelto", "cerrado") and reporte.fecha_cierre is None:
            reporte.fecha_cierre = datetime.now(timezone.utc)
            if reporte.fecha_creacion:
                delta = reporte.fecha_cierre - reporte.fecha_creacion
                reporte.tiempo_atencion_horas = round(delta.total_seconds() / 3600, 1)
    if data.prioridad is not None:
        reporte.prioridad = data.prioridad
    if data.cuadrilla_id is not None:
        reporte.cuadrilla_id = data.cuadrilla_id
    if data.costo_estimado is not None:
        reporte.costo_estimado = data.costo_estimado
    if data.gasto_real is not None:
        reporte.gasto_real = data.gasto_real

    reporte.fecha_actualizacion = datetime.now(timezone.utc)

    new = {
        "estado": reporte.estado,
        "prioridad": reporte.prioridad,
        "cuadrilla_id": reporte.cuadrilla_id,
    }
    changes = compute_changes(old, new)

    await audit.log(
        action="update",
        user_id=user.id,
        tenant_id=user.tenant_id,
        entity_type="reporte",
        entity_id=reporte_id,
        changes=changes,
    )

    return reporte


async def delete_reporte(
    reporte_id: str,
    user: User,
    db: AsyncSession,
    audit: AuditLogger,
) -> None:
    stmt = select(Reporte).where(Reporte.id == reporte_id, Reporte.tenant_id == user.tenant_id)
    result = await db.execute(stmt)
    reporte = result.scalar_one_or_none()
    if reporte is None:
        raise NotFoundError("Reporte", reporte_id)

    await db.delete(reporte)
    await audit.log(
        action="delete",
        user_id=user.id,
        tenant_id=user.tenant_id,
        entity_type="reporte",
        entity_id=reporte_id,
    )


async def add_evidencia(
    reporte_id: str,
    data: EvidenciaCreate,
    user: User,
    db: AsyncSession,
    audit: AuditLogger,
) -> ReporteEvidencia:
    stmt = select(Reporte).where(Reporte.id == reporte_id, Reporte.tenant_id == user.tenant_id)
    result = await db.execute(stmt)
    if result.scalar_one_or_none() is None:
        raise NotFoundError("Reporte", reporte_id)

    ev = ReporteEvidencia(
        id=f"{reporte_id}-ev-{uuid.uuid4().hex[:8]}",
        reporte_id=reporte_id,
        url=data.url,
        caption=data.caption,
        fecha=datetime.now(timezone.utc),
        autor=user.nombre,
        tipo=data.tipo,
    )
    db.add(ev)

    await audit.log(
        action="create",
        user_id=user.id,
        tenant_id=user.tenant_id,
        entity_type="reporte_evidencia",
        entity_id=ev.id,
    )
    return ev


async def add_evento(
    reporte_id: str,
    data: EventoCreate,
    user: User,
    db: AsyncSession,
    audit: AuditLogger,
) -> ReporteEvento:
    stmt = select(Reporte).where(Reporte.id == reporte_id, Reporte.tenant_id == user.tenant_id)
    result = await db.execute(stmt)
    if result.scalar_one_or_none() is None:
        raise NotFoundError("Reporte", reporte_id)

    evt = ReporteEvento(
        id=f"{reporte_id}-tl-{uuid.uuid4().hex[:8]}",
        reporte_id=reporte_id,
        fecha=datetime.now(timezone.utc),
        tipo=data.tipo,
        titulo=data.titulo,
        descripcion=data.descripcion,
        autor_nombre=data.autor_nombre or user.nombre,
        autor_iniciales=data.autor_iniciales or user.iniciales,
        autor_rol=data.autor_rol or user.cargo,
    )
    db.add(evt)

    await audit.log(
        action="create",
        user_id=user.id,
        tenant_id=user.tenant_id,
        entity_type="reporte_evento",
        entity_id=evt.id,
    )
    return evt
