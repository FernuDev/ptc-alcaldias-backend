"""Router del tablero financiero ejecutivo (REQ-16).

Expone el cruce presupuestal autorizado vs ejercido vs comprometido y el contraste
avance físico vs financiero que consume el director / ejecutivo:

  - ``GET /financiero/resumen``             consolidado global del universo visible.
  - ``GET /financiero/por-direccion``       desglose por dirección (categoría de obra).
  - ``GET /financiero/proyectos-en-riesgo`` obras con desfase o sobreejercicio.
  - ``GET /financiero/alertas``             alertas de control presupuestal en vivo.

Todo el tablero exige el permiso ``EJECUTIVO_VER`` (admin, director_area y
supervisor lo tienen). El tenant SIEMPRE proviene del JWT y, para roles no-admin,
se respeta el aislamiento por área de ``obra_service``. La lógica vive en
``financiero_service``; este router solo enruta. Se registra en ``main.py``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.dependencies import DB, require_permission
from app.core.permissions import Permission
from app.models.user import User
from app.schemas.financiero import (
    AlertaFinanciera,
    DireccionFinanciero,
    ProyectoFinanciero,
    ResumenFinanciero,
)
from app.services import financiero_service

router = APIRouter(prefix="/financiero", tags=["financiero"])

EjecutivoUser = Annotated[User, Depends(require_permission(Permission.EJECUTIVO_VER))]


@router.get("/resumen", response_model=ResumenFinanciero)
async def resumen(user: EjecutivoUser, db: DB):
    """Consolidado global: autorizado/ejercido/comprometido + cruce físico vs financiero."""
    return await financiero_service.resumen(user, db)


@router.get("/por-direccion", response_model=list[DireccionFinanciero])
async def por_direccion(user: EjecutivoUser, db: DB):
    """Desglose presupuestal por dirección (categoría de obra)."""
    return await financiero_service.por_direccion(user, db)


@router.get("/proyectos-en-riesgo", response_model=list[ProyectoFinanciero])
async def proyectos_en_riesgo(user: EjecutivoUser, db: DB):
    """Obras con sobreejercicio o avance financiero muy por delante del físico."""
    return await financiero_service.proyectos_en_riesgo(user, db)


@router.get("/alertas", response_model=list[AlertaFinanciera])
async def alertas(user: EjecutivoUser, db: DB):
    """Alertas de control presupuestal calculadas en vivo (sin persistencia)."""
    return await financiero_service.alertas(user, db)
