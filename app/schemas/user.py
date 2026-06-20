from pydantic import BaseModel, EmailStr, Field


class UserRead(BaseModel):
    id: str
    tenant_id: str
    email: str
    nombre: str
    iniciales: str
    cargo: str
    role: str
    areas: list[str] = []
    avatar_tone: str | None = None
    is_active: bool
    # R5 · REQ-17: posición en el árbol organizacional.
    nodo_id: str | None = None
    rol_nivel: str | None = None  # derivado del nivel del nodo
    es_campo: bool = False

    model_config = {"from_attributes": True}


class UserCreate(BaseModel):
    id: str = Field(max_length=50)
    email: EmailStr
    nombre: str = Field(max_length=120)
    iniciales: str = Field(max_length=5)
    cargo: str = Field(max_length=200)
    role: str = Field(
        pattern=r"^(admin|director_area|supervisor|jefe_cuadrilla|inspector|ciudadano)$"
    )
    areas: list[str] = []
    avatar_tone: str | None = Field(None, max_length=7)
    password: str = Field(min_length=8, max_length=100)
    nodo_id: str | None = Field(None, max_length=40)
    # Si se omite, se deriva del nivel del nodo (jefe_cuadrilla/integrante => True).
    es_campo: bool | None = None


class UserUpdate(BaseModel):
    nombre: str | None = Field(None, max_length=120)
    cargo: str | None = Field(None, max_length=200)
    role: str | None = Field(
        None, pattern=r"^(admin|director_area|supervisor|jefe_cuadrilla|inspector|ciudadano)$"
    )
    areas: list[str] | None = None
    avatar_tone: str | None = Field(None, max_length=7)
    is_active: bool | None = None
    nodo_id: str | None = Field(None, max_length=40)
    es_campo: bool | None = None
