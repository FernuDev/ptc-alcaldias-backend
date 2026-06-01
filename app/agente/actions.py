"""Acciones con confirmación humana (human-in-the-loop).

El agente nunca muta el sistema directamente:
1. `preparar_accion` valida el alcance (vía los services, que aplican tenant+área),
   persiste una propuesta `pendiente` y la devuelve SIN ejecutarla.
2. `confirmar_accion` ejecuta esa propuesta — y solo entonces — reutilizando los
   services existentes (que vuelven a validar y registran auditoría).
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agente.context import UsuarioContexto
from app.core.audit import AuditLogger
from app.models.agente_accion import AgenteAccion
from app.models.user import User
from app.schemas.agente import ConfirmActionResponse, PreparedAction
from app.schemas.obra import ObraUpdate
from app.schemas.reporte import ReporteUpdate
from app.services import obra_service, reporte_service

VIGENCIA = timedelta(minutes=15)

# Campos que cada entidad acepta en su Update (se filtra el payload por seguridad).
_CAMPOS_REPORTE = {"estado", "prioridad", "cuadrilla_id", "costo_estimado", "gasto_real"}
_CAMPOS_OBRA = {
    "estado", "prioridad", "avance_pct", "presupuesto_ejercido", "contratista_id", "fecha_fin_real"
}


def _now() -> datetime:
    return datetime.now(UTC)


def _payload_y_descripcion(tipo: str, entity_type: str, params: dict) -> tuple[dict, str]:
    """Traduce (tipo, params) a un payload de cambios + descripción legible."""
    cerrar_estado = "concluida" if entity_type == "obra" else "cerrado"

    if tipo == "cerrar":
        return {"estado": cerrar_estado}, f"Cerrar {entity_type} (estado → {cerrar_estado})"
    if tipo == "cambiar_estado":
        nuevo = params.get("estado")
        return {"estado": nuevo}, f"Cambiar estado de {entity_type} a '{nuevo}'"
    if tipo in ("asignar", "turnar"):
        if entity_type == "obra":
            cid = params.get("contratista_id")
            return {"contratista_id": cid}, f"Turnar obra al contratista '{cid}'"
        cid = params.get("cuadrilla_id")
        return {"cuadrilla_id": cid, "estado": "asignado"}, f"Turnar reporte a la cuadrilla '{cid}'"
    if tipo == "borrador":
        return {"borrador": params.get("texto", "")}, f"Borrador preparado para {entity_type}"
    raise ValueError(f"Tipo de acción no soportado: {tipo!r}")


async def preparar_accion(
    db: AsyncSession,
    ctx: UsuarioContexto,
    user: User,
    *,
    tipo: str,
    entity_type: str,
    entity_id: str,
    params: dict,
) -> PreparedAction:
    # Validación de alcance: si está fuera del tenant/área del usuario, estos
    # services lanzan NotFoundError (→ 404) antes de preparar nada.
    if entity_type == "reporte":
        await reporte_service.get_reporte(entity_id, user, db)
    elif entity_type == "obra":
        await obra_service.get_obra(entity_id, user, db)
    else:
        raise ValueError(f"entity_type no soportado: {entity_type!r}")

    payload, descripcion = _payload_y_descripcion(tipo, entity_type, params)

    accion = AgenteAccion(
        user_id=ctx.id,
        tenant_id=ctx.tenant_id,
        tipo=tipo,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload,
        estado="pendiente",
        expires_at=_now() + VIGENCIA,
    )
    db.add(accion)
    await db.flush()

    return PreparedAction(
        accion_id=accion.id,
        tipo=tipo,
        entity_type=entity_type,
        entity_id=entity_id,
        descripcion=descripcion,
        payload=payload,
    )


async def confirmar_accion(
    db: AsyncSession,
    ctx: UsuarioContexto,
    user: User,
    accion_id: str,
    audit: AuditLogger,
) -> ConfirmActionResponse:
    accion = (
        await db.execute(
            select(AgenteAccion).where(
                AgenteAccion.id == accion_id, AgenteAccion.user_id == ctx.id
            )
        )
    ).scalar_one_or_none()

    if accion is None:
        return ConfirmActionResponse(
            accion_id=accion_id,
            estado="no_encontrada",
            detalle="Acción inexistente o de otro usuario.",
        )
    if accion.estado != "pendiente":
        return ConfirmActionResponse(
            accion_id=accion_id, estado="error", detalle=f"La acción ya está '{accion.estado}'."
        )
    if accion.expires_at < _now():
        accion.estado = "expirada"
        await db.flush()
        return ConfirmActionResponse(
            accion_id=accion_id,
            estado="expirada",
            detalle="La propuesta caducó; vuelve a prepararla.",
        )

    # Ejecución real (salvo borradores, que no mutan el sistema).
    if accion.tipo != "borrador":
        cambios = accion.payload
        if accion.entity_type == "reporte":
            data = ReporteUpdate(**{k: v for k, v in cambios.items() if k in _CAMPOS_REPORTE})
            await reporte_service.update_reporte(accion.entity_id, data, user, db, audit)
        elif accion.entity_type == "obra":
            data = ObraUpdate(**{k: v for k, v in cambios.items() if k in _CAMPOS_OBRA})
            await obra_service.update_obra(accion.entity_id, data, user, db, audit)

    accion.estado = "confirmada"
    accion.confirmed_at = _now()
    await audit.log(
        action="agente_confirm",
        user_id=ctx.id,
        tenant_id=ctx.tenant_id,
        entity_type=accion.entity_type,
        entity_id=accion.entity_id,
        extra={"tipo": accion.tipo, "accion_id": accion.id, "payload": accion.payload},
    )
    await db.flush()

    return ConfirmActionResponse(
        accion_id=accion_id, estado="confirmada", detalle=f"Acción '{accion.tipo}' ejecutada."
    )
