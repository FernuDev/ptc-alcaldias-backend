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


# ─── Integrantes de cuadrilla ────────────────────────────────────────────────
class IntegranteRead(BaseModel):
    id: str
    nombre: str
    rol_campo: str  # jefe | integrante
    telefono: str | None = None
    activo: bool = True
    user_id: str | None = None

    model_config = {"from_attributes": True}


class IntegranteCreate(BaseModel):
    nombre: str = Field(min_length=1, max_length=120)
    rol_campo: str = Field(default="integrante", pattern=r"^(jefe|integrante)$")
    telefono: str | None = Field(None, max_length=20)
    activo: bool = True
    user_id: str | None = Field(None, max_length=50)


class IntegranteUpdate(BaseModel):
    nombre: str | None = Field(None, min_length=1, max_length=120)
    rol_campo: str | None = Field(None, pattern=r"^(jefe|integrante)$")
    telefono: str | None = Field(None, max_length=20)
    activo: bool | None = None
    user_id: str | None = Field(None, max_length=50)
