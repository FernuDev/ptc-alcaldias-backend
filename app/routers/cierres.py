"""Router de cierres viales de Tu Alcald.IA (REQ-02).

Dos superficies con distinto nivel de acceso:

- ``GET  /cierres``                  PÚBLICO (sin auth). Alimenta el banner
  ciudadano con las calles cerradas vigentes del tenant. La alcaldía se
  determina por query (``tenant_id``/``clave_geo``), igual que el router
  ``publico`` existente; si se omiten, se usa la alcaldía por defecto (demo).
- ``POST /cierres/{calle_id}/publicar``  PROTEGIDO. Publica un cierre y dispara
  la notificación por cercanía (geocerca). Requiere el permiso de despacho de
  cuadrillas (quien coordina la operación en campo). El tenant SIEMPRE se deriva
  del JWT; el body solo aporta el radio de la geocerca.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import DB, Audit, require_permission
from app.core.permissions import Permission
from app.models.user import User
from app.schemas.cierres import (
    CierresActivosResponse,
    PublicarCierreRequest,
    PublicarCierreResponse,
)
from app.services import cierres_service

router = APIRouter(prefix="/cierres", tags=["cierres"])

# Quien coordina la operación (admin/director/supervisor) puede publicar cierres.
DespachadorUser = Annotated[
    User, Depends(require_permission(Permission.CUADRILLA_DESPACHAR))
]


@router.get("", response_model=CierresActivosResponse)
async def listar_cierres_activos(
    db: DB,
    tenant_id: str | None = Query(None, max_length=50),
    clave_geo: str | None = Query(None, max_length=10),
):
    """Banner ciudadano (PÚBLICO): cierres viales vigentes de la alcaldía.

    Sin autenticación. Devuelve las calles cerradas activas con su tipo de
    afectación, ubicación, vigencia, obra de origen y alternativas viales.
    """
    return await cierres_service.cierres_activos(
        db, tenant_id=tenant_id, clave_geo=clave_geo
    )


@router.post("/{calle_id}/publicar", response_model=PublicarCierreResponse)
async def publicar_cierre(
    calle_id: str,
    data: PublicarCierreRequest,
    user: DespachadorUser,
    db: DB,
    audit: Audit,
):
    """Publica un cierre vial y notifica por cercanía (geocerca) a los responsables.

    El tenant se deriva del JWT (multi-tenant). Calcula las colonias dentro del
    radio del cierre y crea notificaciones tipo ``cierre`` para el área de la
    obra. Documenta el punto de extensión hacia push real.
    """
    resultado = await cierres_service.publicar_cierre(
        db,
        calle_id=calle_id,
        tenant_id=user.tenant_id,
        radio_km=data.radio_km,
        mensaje=data.mensaje,
        excluir_user_id=user.id,
    )
    await audit.log(
        action="cierre.publicar",
        user_id=user.id,
        tenant_id=user.tenant_id,
        entity_type="obra",
        entity_id=resultado.obra_id,
        extra={
            "calle_id": resultado.calle_id,
            "tipo_afectacion": resultado.tipo_afectacion,
            "radio_km": resultado.radio_km,
            "colonias_en_cercania": [c.id for c in resultado.colonias_en_cercania],
            "notificaciones_enviadas": resultado.notificaciones_enviadas,
        },
    )
    return resultado
