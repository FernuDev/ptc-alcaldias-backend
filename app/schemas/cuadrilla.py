from pydantic import BaseModel, Field


class CuadrillaRead(BaseModel):
    id: str
    tenant_id: str
    nombre: str
    integrantes: int | None = None
    especialidades: list[str] = []

    model_config = {"from_attributes": True}


class CuadrillaCreate(BaseModel):
    id: str = Field(max_length=10)
    nombre: str = Field(max_length=80)
    integrantes: int | None = None
    especialidades: list[str] = []


class CuadrillaUpdate(BaseModel):
    nombre: str | None = Field(None, max_length=80)
    integrantes: int | None = None
    especialidades: list[str] | None = None
