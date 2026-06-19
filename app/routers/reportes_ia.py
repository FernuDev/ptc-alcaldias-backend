"""Endpoints de IA sobre reportes (módulo 16): duplicados + reclasificación.

Router separado (`/reportes-ia`) para no tocar el router `reportes` existente.
Toda la lógica vive en `app.agente.actions` (reutilizable también por las tools
del Agente Institucional). Los endpoints reciben `CurrentUser`, por lo que el
alcance (tenant + área) lo aplican los services subyacentes: nunca devuelven un
reporte fuera del alcance del usuario.
"""

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.agente import actions
from app.core.dependencies import DB, CurrentUser

router = APIRouter(prefix="/reportes-ia", tags=["reportes-ia"])


# ─── Schemas de respuesta ──────────────────────────────────────────────────


class ReporteRef(BaseModel):
    id: str
    folio: str
    titulo: str


class DuplicadoItem(BaseModel):
    id: str
    folio: str
    titulo: str
    estado: str
    colonia: str | None = None
    score: float
    confianza: str  # alta | media | baja
    distancia_m: float | None = None
    horas_diferencia: float | None = None
    similitud_texto: float
    misma_categoria: bool
    misma_colonia: bool
    motivos: list[str] = []


class DuplicadosResponse(BaseModel):
    reporte: ReporteRef
    hay_duplicados: bool
    total: int
    parametros: dict
    duplicados: list[DuplicadoItem]


class ReclasificacionResponse(BaseModel):
    reporte: ReporteRef
    categoria_actual: str
    categoria_sugerida: str
    cambia_categoria: bool
    prioridad_actual: str
    prioridad_sugerida: str
    cambia_prioridad: bool
    es_emergencia: bool
    es_sensible: bool
    requiere_revision: bool
    justificacion: str


# ─── Endpoints ─────────────────────────────────────────────────────────────


@router.get("/{reporte_id}/duplicados", response_model=DuplicadosResponse)
async def duplicados(
    reporte_id: str,
    user: CurrentUser,
    db: DB,
    radio_m: float = Query(actions.RADIO_DUPLICADO_M, ge=10, le=2000),
    dias: int = Query(7, ge=1, le=90),
    umbral: float = Query(actions.UMBRAL_DUPLICADO, ge=0.0, le=1.0),
    limite: int = Query(10, ge=1, le=50),
) -> DuplicadosResponse:
    """Posibles duplicados de un reporte (mismo incidente), ordenados por score."""
    from datetime import timedelta

    base, candidatos = await actions.detectar_duplicados(
        reporte_id,
        user,
        db,
        radio_m=radio_m,
        ventana=timedelta(days=dias),
        umbral=umbral,
        limite=limite,
    )
    return DuplicadosResponse(
        reporte=ReporteRef(id=base.id, folio=base.folio, titulo=base.titulo),
        hay_duplicados=bool(candidatos),
        total=len(candidatos),
        parametros={"radio_m": radio_m, "dias": dias, "umbral": umbral},
        duplicados=[
            DuplicadoItem(
                id=c.reporte.id,
                folio=c.reporte.folio,
                titulo=c.reporte.titulo,
                estado=c.reporte.estado,
                colonia=c.reporte.colonia_nombre,
                score=c.score,
                confianza=c.confianza,
                distancia_m=c.distancia_m,
                horas_diferencia=c.horas_diferencia,
                similitud_texto=c.similitud_texto,
                misma_categoria=c.misma_categoria,
                misma_colonia=c.misma_colonia,
                motivos=c.motivos,
            )
            for c in candidatos
        ],
    )


@router.get("/{reporte_id}/reclasificacion", response_model=ReclasificacionResponse)
async def reclasificacion(
    reporte_id: str,
    user: CurrentUser,
    db: DB,
) -> ReclasificacionResponse:
    """Sugiere categoría/prioridad para un reporte (no las aplica automáticamente)."""
    s = await actions.sugerir_reclasificacion(reporte_id, user, db)
    return ReclasificacionResponse(
        reporte=ReporteRef(id=s.reporte_id, folio=s.folio, titulo=s.titulo),
        categoria_actual=s.categoria_actual,
        categoria_sugerida=s.categoria_sugerida,
        cambia_categoria=s.cambia_categoria,
        prioridad_actual=s.prioridad_actual,
        prioridad_sugerida=s.prioridad_sugerida,
        cambia_prioridad=s.cambia_prioridad,
        es_emergencia=s.es_emergencia,
        es_sensible=s.es_sensible,
        requiere_revision=s.cambia_categoria or s.cambia_prioridad or s.es_emergencia,
        justificacion=s.justificacion,
    )
