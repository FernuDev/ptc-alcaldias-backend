"""Router de scorecards de desempeño (REQ-06).

Tarjetas de rendimiento por cuadrilla y por persona. La VISIBILIDAD JERÁRQUICA
es la pieza clave y se resuelve en :mod:`app.services.scorecard_service` a partir
del rol/permisos y las áreas del ``CurrentUser``:

* admin → todo el tenant.
* director_area / supervisor → su equipo (cuadrillas/personal de su área).
* jefe_cuadrilla / inspector → solo lo suyo (su cuadrilla / su persona).

Nadie ve a sus pares. El acceso lo controla el propio servicio: los roles sin
visibilidad reciben 403. El tenant SIEMPRE proviene del JWT.

La integración registra este router en ``main.py`` (no se toca aquí).
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.dependencies import DB, CurrentUser
from app.schemas.scorecard import (
    CuadrillaScorecard,
    PersonaScorecard,
    ScorecardScope,
)
from app.services import scorecard_service

router = APIRouter(prefix="/scorecards", tags=["scorecards"])


class CuadrillasScorecardResponse(BaseModel):
    scope: ScorecardScope
    cuadrillas: list[CuadrillaScorecard]


class PersonalScorecardResponse(BaseModel):
    scope: ScorecardScope
    personal: list[PersonaScorecard]


@router.get("/cuadrillas", response_model=CuadrillasScorecardResponse)
async def scorecards_cuadrillas(user: CurrentUser, db: DB):
    """Scorecards de las cuadrillas visibles para el usuario (según su rol)."""
    cards, scope = await scorecard_service.scorecards_cuadrillas(user, db)
    return CuadrillasScorecardResponse(scope=scope, cuadrillas=cards)


@router.get("/cuadrillas/{cuadrilla_id}", response_model=CuadrillaScorecard)
async def scorecard_cuadrilla(cuadrilla_id: str, user: CurrentUser, db: DB):
    """Scorecard de una cuadrilla. 403 si el usuario no puede verla, 404 si no existe."""
    return await scorecard_service.scorecard_cuadrilla(cuadrilla_id, user, db)


@router.get("/personal", response_model=PersonalScorecardResponse)
async def scorecards_personal(user: CurrentUser, db: DB):
    """Scorecards por persona (integrante) según la visibilidad del usuario."""
    cards, scope = await scorecard_service.scorecards_personal(user, db)
    return PersonalScorecardResponse(scope=scope, personal=cards)
