from decimal import Decimal

from pydantic import BaseModel, Field


class ContratistaRead(BaseModel):
    id: str
    razon_social: str
    rfc: str
    calificacion: Decimal | None = None

    model_config = {"from_attributes": True}


class ContratistaCreate(BaseModel):
    id: str = Field(max_length=10)
    razon_social: str = Field(max_length=200)
    rfc: str = Field(max_length=13)
    calificacion: Decimal | None = None


class ContratistaUpdate(BaseModel):
    razon_social: str | None = Field(None, max_length=200)
    rfc: str | None = Field(None, max_length=13)
    calificacion: Decimal | None = None
