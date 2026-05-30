"""Export endpoints for PDF, CSV, and Excel.

All endpoints respect tenant isolation and area filtering via JWT.
"""

from fastapi import APIRouter, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import CurrentUser, DB
from app.models.obra import Obra
from app.models.reporte import Reporte
from app.models.tenant import Tenant
from app.models.user import User
from app.services import stats_service
from app.services.exports import csv_generator, excel_generator, pdf_generator

router = APIRouter(prefix="/exports", tags=["exports"])


# ─── Helpers ──────────────────────────────────────────────────────────────

async def _get_tenant_meta(user: User, db: AsyncSession) -> dict:
    result = await db.execute(select(Tenant).where(Tenant.id == user.tenant_id))
    t = result.scalar_one()
    return {"tenant_name": t.nombre_corto or t.nombre, "tenant_color": t.primario}


async def _fetch_reportes(user: User, db: AsyncSession) -> list[dict]:
    stmt = select(Reporte).where(Reporte.tenant_id == user.tenant_id)
    if user.role != "admin" and user.areas:
        area_ids = [a.id for a in user.areas]
        stmt = stmt.where(Reporte.categoria_id.in_(area_ids))
    stmt = stmt.order_by(Reporte.fecha_creacion.desc())
    result = await db.execute(stmt)
    return [
        {
            "id": r.id, "folio": r.folio, "categoria_id": r.categoria_id,
            "estado": r.estado, "prioridad": r.prioridad, "fuente": r.fuente,
            "cuadrilla_id": r.cuadrilla_id, "colonia_nombre": r.colonia_nombre,
            "titulo": r.titulo, "descripcion": r.descripcion,
            "ciudadano_nombre": r.ciudadano_nombre,
            "lng": r.lng, "lat": r.lat,
            "fecha_creacion": r.fecha_creacion.isoformat() if r.fecha_creacion else "",
            "fecha_cierre": r.fecha_cierre.isoformat() if r.fecha_cierre else "",
            "tiempo_atencion_horas": str(r.tiempo_atencion_horas) if r.tiempo_atencion_horas else "",
            "costo_estimado": str(r.costo_estimado) if r.costo_estimado else "",
            "gasto_real": str(r.gasto_real) if r.gasto_real else "",
        }
        for r in result.scalars().all()
    ]


async def _fetch_obras(user: User, db: AsyncSession) -> list[dict]:
    from app.services.obra_service import REPORT_CAT_TO_OBRA_CAT

    stmt = select(Obra).where(Obra.tenant_id == user.tenant_id)
    if user.role != "admin" and user.areas:
        area_ids = [a.id for a in user.areas]
        obra_cats = set()
        for aid in area_ids:
            obra_cats.update(REPORT_CAT_TO_OBRA_CAT.get(aid, []))
        if obra_cats:
            stmt = stmt.where(Obra.categoria_id.in_(list(obra_cats)))
    stmt = stmt.order_by(Obra.fecha_inicio.desc())
    result = await db.execute(stmt)
    return [
        {
            "id": o.id, "folio": o.folio, "nombre": o.nombre,
            "categoria_id": o.categoria_id, "estado": o.estado,
            "prioridad": o.prioridad, "colonia_nombre": o.colonia_nombre,
            "contratista_id": o.contratista_id,
            "avance_pct": o.avance_pct,
            "presupuesto_autorizado": str(o.presupuesto_autorizado) if o.presupuesto_autorizado else "",
            "presupuesto_ejercido": str(o.presupuesto_ejercido) if o.presupuesto_ejercido else "",
            "fecha_inicio": o.fecha_inicio.isoformat() if o.fecha_inicio else "",
            "fecha_fin_estimada": o.fecha_fin_estimada.isoformat() if o.fecha_fin_estimada else "",
            "fecha_fin_real": o.fecha_fin_real.isoformat() if o.fecha_fin_real else "",
            "responsable_nombre": o.responsable_nombre,
        }
        for o in result.scalars().all()
    ]


async def _fetch_stats(user: User, db: AsyncSession) -> dict:
    kpis = await stats_service.calc_kpis(user, db)
    dist_cat = await stats_service.distribucion_categoria(user, db)
    dist_est = await stats_service.distribucion_estado(user, db)
    top_col = await stats_service.top_colonias(user, db, 10)
    volumen = await stats_service.volumen_por_dia(user, db, 30)
    ranking = await stats_service.ranking_cuadrillas(user, db)
    costo = await stats_service.costo_operativo(user, db)
    return {
        "kpis": kpis.model_dump(),
        "dist_categoria": [d.model_dump() for d in dist_cat],
        "dist_estado": [d.model_dump() for d in dist_est],
        "top_colonias": [d.model_dump() for d in top_col],
        "volumen": [d.model_dump() for d in volumen],
        "ranking_cuadrillas": [d.model_dump() for d in ranking],
        "costo_operativo": [d.model_dump() for d in costo],
    }


# ═══════════════════════════════════════════════════════════════════════════
# Reportes exports
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/reportes/pdf")
async def export_reportes_pdf(user: CurrentUser, db: DB):
    meta = await _get_tenant_meta(user, db)
    reportes = await _fetch_reportes(user, db)
    stats = await _fetch_stats(user, db)

    content = pdf_generator.generate_reportes_pdf(
        tenant_name=meta["tenant_name"],
        tenant_color=meta["tenant_color"],
        kpis=stats["kpis"],
        dist_categoria=stats["dist_categoria"],
        dist_estado=stats["dist_estado"],
        top_colonias=stats["top_colonias"],
        volumen=stats["volumen"],
        reportes=reportes,
    )
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=reportes.pdf"},
    )


@router.get("/reportes/csv")
async def export_reportes_csv(user: CurrentUser, db: DB):
    reportes = await _fetch_reportes(user, db)
    content = csv_generator.generate_reportes_csv(reportes)
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=reportes.csv"},
    )


@router.get("/reportes/excel")
async def export_reportes_excel(user: CurrentUser, db: DB):
    meta = await _get_tenant_meta(user, db)
    reportes = await _fetch_reportes(user, db)
    stats = await _fetch_stats(user, db)

    content = excel_generator.generate_reportes_excel(
        reportes=reportes,
        kpis=stats["kpis"],
        dist_categoria=stats["dist_categoria"],
        dist_estado=stats["dist_estado"],
        top_colonias=stats["top_colonias"],
        tenant_name=meta["tenant_name"],
    )
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=reportes.xlsx"},
    )


# ═══════════════════════════════════════════════════════════════════════════
# Obras exports
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/obras/pdf")
async def export_obras_pdf(user: CurrentUser, db: DB):
    meta = await _get_tenant_meta(user, db)
    obras = await _fetch_obras(user, db)

    content = pdf_generator.generate_obras_pdf(
        tenant_name=meta["tenant_name"],
        tenant_color=meta["tenant_color"],
        obras=obras,
        stats={},
    )
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=obras.pdf"},
    )


@router.get("/obras/csv")
async def export_obras_csv(user: CurrentUser, db: DB):
    obras = await _fetch_obras(user, db)
    content = csv_generator.generate_obras_csv(obras)
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=obras.csv"},
    )


@router.get("/obras/excel")
async def export_obras_excel(user: CurrentUser, db: DB):
    meta = await _get_tenant_meta(user, db)
    obras = await _fetch_obras(user, db)

    content = excel_generator.generate_obras_excel(
        obras=obras,
        tenant_name=meta["tenant_name"],
    )
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=obras.xlsx"},
    )


# ═══════════════════════════════════════════════════════════════════════════
# Stats executive report
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/stats/pdf")
async def export_stats_pdf(user: CurrentUser, db: DB):
    meta = await _get_tenant_meta(user, db)
    stats = await _fetch_stats(user, db)

    content = pdf_generator.generate_stats_pdf(
        tenant_name=meta["tenant_name"],
        tenant_color=meta["tenant_color"],
        kpis=stats["kpis"],
        dist_categoria=stats["dist_categoria"],
        dist_estado=stats["dist_estado"],
        top_colonias=stats["top_colonias"],
        volumen=stats["volumen"],
        ranking_cuadrillas=stats["ranking_cuadrillas"],
        costo_operativo=stats["costo_operativo"],
    )
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=reporte-ejecutivo.pdf"},
    )


@router.get("/stats/excel")
async def export_stats_excel(user: CurrentUser, db: DB):
    meta = await _get_tenant_meta(user, db)
    # Reuse reportes excel with stats for the executive report
    reportes = await _fetch_reportes(user, db)
    stats = await _fetch_stats(user, db)

    content = excel_generator.generate_reportes_excel(
        reportes=reportes,
        kpis=stats["kpis"],
        dist_categoria=stats["dist_categoria"],
        dist_estado=stats["dist_estado"],
        top_colonias=stats["top_colonias"],
        tenant_name=meta["tenant_name"],
    )
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=reporte-ejecutivo.xlsx"},
    )
