from fastapi import APIRouter, Query

from app.core.dependencies import CurrentUser, DB
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
from app.services import stats_service

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/kpis", response_model=KpisResponse)
async def kpis(user: CurrentUser, db: DB):
    return await stats_service.calc_kpis(user, db)


@router.get("/volumen", response_model=list[VolumenDia])
async def volumen(user: CurrentUser, db: DB, dias: int = Query(30, ge=1, le=365)):
    return await stats_service.volumen_por_dia(user, db, dias)


@router.get("/distribucion-categoria", response_model=list[DistribucionItem])
async def dist_categoria(user: CurrentUser, db: DB):
    return await stats_service.distribucion_categoria(user, db)


@router.get("/distribucion-estado", response_model=list[DistribucionItem])
async def dist_estado(user: CurrentUser, db: DB):
    return await stats_service.distribucion_estado(user, db)


@router.get("/top-colonias", response_model=list[TopColonia])
async def top_colonias(user: CurrentUser, db: DB, n: int = Query(6, ge=1, le=50)):
    return await stats_service.top_colonias(user, db, n)


@router.get("/sla-semanal", response_model=list[SlaSemanal])
async def sla_semanal(user: CurrentUser, db: DB, semanas: int = Query(6, ge=1, le=52)):
    return await stats_service.sla_semanal(user, db, semanas)


@router.get("/tiempo-por-categoria", response_model=list[TiempoCategoria])
async def tiempo_cat(user: CurrentUser, db: DB):
    return await stats_service.tiempo_por_categoria(user, db)


@router.get("/ranking-cuadrillas", response_model=list[RankingCuadrilla])
async def ranking_cuadrillas(user: CurrentUser, db: DB):
    return await stats_service.ranking_cuadrillas(user, db)


@router.get("/distribucion-horaria", response_model=list[DistribucionHoraria])
async def dist_horaria(user: CurrentUser, db: DB):
    return await stats_service.distribucion_horaria(user, db)


@router.get("/distribucion-dia-semana", response_model=list[DistribucionDiaSemana])
async def dist_dia(user: CurrentUser, db: DB):
    return await stats_service.distribucion_dia_semana(user, db)


@router.get("/costo-operativo", response_model=list[CostoOperativo])
async def costo_op(user: CurrentUser, db: DB):
    return await stats_service.costo_operativo(user, db)


@router.get("/actividad-reciente", response_model=list[ActividadReciente])
async def actividad(user: CurrentUser, db: DB, n: int = Query(6, ge=1, le=50)):
    return await stats_service.actividad_reciente(user, db, n)
