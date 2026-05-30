from fastapi import APIRouter
from sqlalchemy import select

from app.core.dependencies import CurrentUser, DB
from app.models.categoria import Categoria, ObraCategoria
from app.schemas.categoria import CategoriaRead, ObraCategoriaRead

router = APIRouter(tags=["catalogos"])


@router.get("/categorias", response_model=list[CategoriaRead])
async def list_categorias(user: CurrentUser, db: DB):
    result = await db.execute(select(Categoria).order_by(Categoria.peso.desc()))
    return [CategoriaRead.model_validate(c) for c in result.scalars().all()]


@router.get("/obra-categorias", response_model=list[ObraCategoriaRead])
async def list_obra_categorias(user: CurrentUser, db: DB):
    result = await db.execute(select(ObraCategoria).order_by(ObraCategoria.peso.desc()))
    return [ObraCategoriaRead.model_validate(c) for c in result.scalars().all()]
