from decimal import Decimal

from pydantic import BaseModel


class ColoniaRead(BaseModel):
    id: str
    tenant_id: str
    nombre: str
    tipo: str
    center_lng: float
    center_lat: float
    area_ha: Decimal | None = None
    poblacion: int | None = None
    viviendas: int | None = None
    densidad: Decimal | None = None
    codigos_postales: str | None = None
    servicio_agua: int | None = None
    servicio_drenaje: int | None = None
    servicio_luz: int | None = None
    servicio_internet: int | None = None
    factor_reportes: Decimal | None = None

    model_config = {"from_attributes": True}
