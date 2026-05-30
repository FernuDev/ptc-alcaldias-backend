from fastapi import APIRouter

from app.core.dependencies import CurrentUser, DB
from app.schemas.colonia import ColoniaRead
from app.services import colonia_service

router = APIRouter(tags=["catalogos"])


@router.get("/colonias", response_model=list[ColoniaRead])
async def list_colonias(user: CurrentUser, db: DB):
    colonias = await colonia_service.list_colonias(user.tenant_id, db)
    return [ColoniaRead.model_validate(c) for c in colonias]
