from decimal import Decimal

from pydantic import BaseModel


class KpisResponse(BaseModel):
    activos: int
    resueltos: int
    tiempo_promedio_dias: float
    en_riesgo_sla: int
    total_rango: int
    pct_resueltos: float


class VolumenDia(BaseModel):
    fecha: str
    dia: str
    recibidos: int
    atendidos: int


class DistribucionItem(BaseModel):
    id: str
    label: str
    color: str
    count: int
    pct: float


class TopColonia(BaseModel):
    colonia_id: str
    colonia_nombre: str
    count: int


class SlaSemanal(BaseModel):
    semana: str
    promedio_horas: float


class TiempoCategoria(BaseModel):
    categoria_id: str
    label: str
    promedio_horas: float


class RankingCuadrilla(BaseModel):
    cuadrilla_id: str
    nombre: str
    resueltos: int
    promedio_horas: float
    sla_pct: float


class ActividadReciente(BaseModel):
    id: str
    tipo: str
    titulo: str
    fecha: str
    categoria_id: str | None = None
    estado: str | None = None


class DistribucionHoraria(BaseModel):
    hora: int
    count: int


class DistribucionDiaSemana(BaseModel):
    dia: int
    nombre: str
    count: int


class CostoOperativo(BaseModel):
    categoria_id: str
    label: str
    estimado: Decimal
    ejercido: Decimal
