from decimal import Decimal

from pydantic import BaseModel


class CategoriaRead(BaseModel):
    id: str
    label: str
    color: str
    icono: str | None = None
    peso: Decimal

    model_config = {"from_attributes": True}


class ObraCategoriaRead(BaseModel):
    id: str
    label: str
    color: str
    peso: Decimal

    model_config = {"from_attributes": True}
