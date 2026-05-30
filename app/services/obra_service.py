import math
import uuid
from datetime import datetime, timezone

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditLogger, compute_changes
from app.core.exceptions import NotFoundError
from app.models.colonia import Colonia
from app.models.obra import (
    Obra,
    ObraCalleAfectada,
    ObraDocumento,
    ObraEquipo,
    ObraEvidencia,
    ObraTimeline,
)
from app.models.user import User
from app.schemas.common import PaginatedResponse
from app.schemas.obra import (
    CalleAfectadaCreate,
    DocumentoCreate,
    EquipoCreate,
    ObraCreate,
    ObraEvidenciaCreate,
    ObraRead,
    ObraUpdate,
    TimelineCreate,
)

# Mapping from reporte categories to obra categories (for director filtering)
REPORT_CAT_TO_OBRA_CAT: dict[str, list[str]] = {
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


def _apply_tenant_and_area_filter(stmt: Select, user: User) -> Select:
    stmt = stmt.where(Obra.tenant_id == user.tenant_id)
    if user.role != "admin" and user.areas:
        area_ids = [a.id for a in user.areas]
        obra_cats = set()
        for aid in area_ids:
            obra_cats.update(REPORT_CAT_TO_OBRA_CAT.get(aid, []))
        if obra_cats:
            stmt = stmt.where(Obra.categoria_id.in_(list(obra_cats)))
    return stmt


async def list_obras(
    user: User,
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    sort_by: str = "fecha_inicio",
    sort_dir: str = "desc",
    search: str | None = None,
    categorias: list[str] | None = None,
    estados: list[str] | None = None,
    prioridades: list[str] | None = None,
    colonia_ids: list[str] | None = None,
) -> PaginatedResponse[ObraRead]:
    stmt = select(Obra)
    stmt = _apply_tenant_and_area_filter(stmt, user)

    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            Obra.nombre.ilike(pattern)
            | Obra.folio.ilike(pattern)
            | Obra.colonia_nombre.ilike(pattern)
        )
    if categorias:
        stmt = stmt.where(Obra.categoria_id.in_(categorias))
    if estados:
        stmt = stmt.where(Obra.estado.in_(estados))
    if prioridades:
        stmt = stmt.where(Obra.prioridad.in_(prioridades))
    if colonia_ids:
        stmt = stmt.where(Obra.colonia_id.in_(colonia_ids))

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    sort_col = getattr(Obra, sort_by, Obra.fecha_inicio)
    stmt = stmt.order_by(sort_col.desc() if sort_dir == "desc" else sort_col.asc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(stmt)
    obras = list(result.scalars().all())
    items = [ObraRead.model_validate(o) for o in obras]

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=math.ceil(total / page_size) if page_size else 1,
    )


async def get_obra(obra_id: str, user: User, db: AsyncSession) -> ObraRead:
    stmt = select(Obra).where(Obra.id == obra_id)
    stmt = _apply_tenant_and_area_filter(stmt, user)
    result = await db.execute(stmt)
    o = result.scalar_one_or_none()
    if o is None:
        raise NotFoundError("Obra", obra_id)
    return ObraRead.model_validate(o)


async def create_obra(
    data: ObraCreate,
    user: User,
    db: AsyncSession,
    audit: AuditLogger,
) -> Obra:
    col_result = await db.execute(select(Colonia).where(Colonia.id == data.colonia_id))
    colonia = col_result.scalar_one_or_none()
    colonia_nombre = colonia.nombre if colonia else None

    count_result = await db.execute(
        select(func.count()).select_from(Obra).where(Obra.tenant_id == user.tenant_id)
    )
    count = (count_result.scalar() or 0) + 1
    acr = "MC" if user.tenant_id == "magdalena-contreras" else "TL"
    obra_id = f"{acr}-OB-{count:03d}"
    folio = f"{acr}-OBR-2026-{count:03d}"

    obra = Obra(
        id=obra_id,
        tenant_id=user.tenant_id,
        folio=folio,
        nombre=data.nombre,
        descripcion=data.descripcion,
        categoria_id=data.categoria_id,
        estado="planeacion",
        prioridad=data.prioridad,
        colonia_id=data.colonia_id,
        colonia_nombre=colonia_nombre,
        center_lng=data.center_lng or (colonia.center_lng if colonia else 0),
        center_lat=data.center_lat or (colonia.center_lat if colonia else 0),
        responsable_nombre=user.nombre,
        responsable_iniciales=user.iniciales,
        responsable_cargo=user.cargo,
        contratista_id=data.contratista_id,
        fecha_inicio=data.fecha_inicio,
        fecha_fin_estimada=data.fecha_fin_estimada,
        avance_pct=0,
        presupuesto_autorizado=data.presupuesto_autorizado,
        presupuesto_ejercido=0,
    )
    db.add(obra)
    await db.flush()

    tl = ObraTimeline(
        id=f"{obra_id}-tl-001",
        obra_id=obra_id,
        fecha=datetime.now(timezone.utc),
        tipo="creacion",
        titulo="Obra registrada en el sistema",
        autor_nombre=user.nombre,
        autor_iniciales=user.iniciales,
        autor_rol=user.cargo,
    )
    db.add(tl)

    await audit.log(
        action="create",
        user_id=user.id,
        tenant_id=user.tenant_id,
        entity_type="obra",
        entity_id=obra_id,
    )
    return obra


async def update_obra(
    obra_id: str,
    data: ObraUpdate,
    user: User,
    db: AsyncSession,
    audit: AuditLogger,
) -> Obra:
    stmt = select(Obra).where(Obra.id == obra_id, Obra.tenant_id == user.tenant_id)
    result = await db.execute(stmt)
    obra = result.scalar_one_or_none()
    if obra is None:
        raise NotFoundError("Obra", obra_id)

    old = {"estado": obra.estado, "avance_pct": obra.avance_pct, "contratista_id": obra.contratista_id}

    if data.estado is not None:
        obra.estado = data.estado
        if data.estado == "concluida" and obra.fecha_fin_real is None:
            obra.fecha_fin_real = datetime.now(timezone.utc)
    if data.prioridad is not None:
        obra.prioridad = data.prioridad
    if data.avance_pct is not None:
        obra.avance_pct = data.avance_pct
    if data.presupuesto_ejercido is not None:
        obra.presupuesto_ejercido = data.presupuesto_ejercido
    if data.contratista_id is not None:
        obra.contratista_id = data.contratista_id
    if data.fecha_fin_real is not None:
        obra.fecha_fin_real = data.fecha_fin_real

    new = {"estado": obra.estado, "avance_pct": obra.avance_pct, "contratista_id": obra.contratista_id}
    changes = compute_changes(old, new)

    await audit.log(
        action="update",
        user_id=user.id,
        tenant_id=user.tenant_id,
        entity_type="obra",
        entity_id=obra_id,
        changes=changes,
    )
    return obra


async def delete_obra(
    obra_id: str, user: User, db: AsyncSession, audit: AuditLogger
) -> None:
    stmt = select(Obra).where(Obra.id == obra_id, Obra.tenant_id == user.tenant_id)
    result = await db.execute(stmt)
    obra = result.scalar_one_or_none()
    if obra is None:
        raise NotFoundError("Obra", obra_id)
    await db.delete(obra)
    await audit.log(
        action="delete",
        user_id=user.id,
        tenant_id=user.tenant_id,
        entity_type="obra",
        entity_id=obra_id,
    )


async def add_equipo(
    obra_id: str, data: EquipoCreate, user: User, db: AsyncSession, audit: AuditLogger
) -> ObraEquipo:
    stmt = select(Obra).where(Obra.id == obra_id, Obra.tenant_id == user.tenant_id)
    if not (await db.execute(stmt)).scalar_one_or_none():
        raise NotFoundError("Obra", obra_id)
    member = ObraEquipo(
        id=f"{obra_id}-eq-{uuid.uuid4().hex[:6]}",
        obra_id=obra_id,
        nombre=data.nombre,
        iniciales=data.iniciales,
        rol=data.rol,
        contacto=data.contacto,
    )
    db.add(member)
    await audit.log(action="create", user_id=user.id, tenant_id=user.tenant_id, entity_type="obra_equipo", entity_id=member.id)
    return member


async def add_calle(
    obra_id: str, data: CalleAfectadaCreate, user: User, db: AsyncSession, audit: AuditLogger
) -> ObraCalleAfectada:
    stmt = select(Obra).where(Obra.id == obra_id, Obra.tenant_id == user.tenant_id)
    if not (await db.execute(stmt)).scalar_one_or_none():
        raise NotFoundError("Obra", obra_id)
    calle = ObraCalleAfectada(
        id=f"{obra_id}-ca-{uuid.uuid4().hex[:6]}",
        obra_id=obra_id,
        nombre=data.nombre,
        estado=data.estado,
        coordenadas=data.coordenadas,
        alternativas_viales=data.alternativas_viales,
    )
    db.add(calle)
    await audit.log(action="create", user_id=user.id, tenant_id=user.tenant_id, entity_type="obra_calle", entity_id=calle.id)
    return calle


async def add_timeline(
    obra_id: str, data: TimelineCreate, user: User, db: AsyncSession, audit: AuditLogger
) -> ObraTimeline:
    stmt = select(Obra).where(Obra.id == obra_id, Obra.tenant_id == user.tenant_id)
    if not (await db.execute(stmt)).scalar_one_or_none():
        raise NotFoundError("Obra", obra_id)
    tl = ObraTimeline(
        id=f"{obra_id}-tl-{uuid.uuid4().hex[:6]}",
        obra_id=obra_id,
        fecha=datetime.now(timezone.utc),
        tipo=data.tipo,
        titulo=data.titulo,
        descripcion=data.descripcion,
        autor_nombre=data.autor_nombre or user.nombre,
        autor_iniciales=data.autor_iniciales or user.iniciales,
        autor_rol=data.autor_rol or user.cargo,
    )
    db.add(tl)
    await audit.log(action="create", user_id=user.id, tenant_id=user.tenant_id, entity_type="obra_timeline", entity_id=tl.id)
    return tl


async def add_documento(
    obra_id: str, data: DocumentoCreate, user: User, db: AsyncSession, audit: AuditLogger
) -> ObraDocumento:
    stmt = select(Obra).where(Obra.id == obra_id, Obra.tenant_id == user.tenant_id)
    if not (await db.execute(stmt)).scalar_one_or_none():
        raise NotFoundError("Obra", obra_id)
    doc = ObraDocumento(
        id=f"{obra_id}-doc-{uuid.uuid4().hex[:6]}",
        obra_id=obra_id,
        nombre=data.nombre,
        tipo=data.tipo,
        tamano_kb=data.tamano_kb,
        fecha_subida=datetime.now(timezone.utc),
        autor=data.autor or user.nombre,
    )
    db.add(doc)
    await audit.log(action="create", user_id=user.id, tenant_id=user.tenant_id, entity_type="obra_documento", entity_id=doc.id)
    return doc


async def add_evidencia(
    obra_id: str, data: ObraEvidenciaCreate, user: User, db: AsyncSession, audit: AuditLogger
) -> ObraEvidencia:
    stmt = select(Obra).where(Obra.id == obra_id, Obra.tenant_id == user.tenant_id)
    if not (await db.execute(stmt)).scalar_one_or_none():
        raise NotFoundError("Obra", obra_id)
    ev = ObraEvidencia(
        id=f"{obra_id}-ev-{uuid.uuid4().hex[:6]}",
        obra_id=obra_id,
        url=data.url,
        caption=data.caption,
        fecha=datetime.now(timezone.utc),
        autor=user.nombre,
        tipo=data.tipo,
    )
    db.add(ev)
    await audit.log(action="create", user_id=user.id, tenant_id=user.tenant_id, entity_type="obra_evidencia", entity_id=ev.id)
    return ev
