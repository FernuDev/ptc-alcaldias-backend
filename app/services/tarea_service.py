"""Servicio de tareas de campo (despacho operativo a cuadrillas).

Una tarea es el trabajo concreto que ejecuta una cuadrilla en calle. Se origina
en un reporte ciudadano, una obra o se crea manualmente, y avanza por la máquina
de estados ``pendiente -> en_ruta -> en_sitio -> cerrada`` (sin saltos). El cierre
exige evidencia fotográfica antes/después del reporte asociado y propaga la
resolución al reporte (reusando la lógica de ``reporte_service``).

El tenant SIEMPRE se deriva de ``user.tenant_id`` y se filtra por ``WHERE tenant_id``.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditLogger
from app.core.exceptions import ConflictError, NotFoundError
from app.models.campo import Tarea
from app.models.cuadrilla import Cuadrilla, Integrante
from app.models.obra import Obra
from app.models.proyecto import ProyectoTarea
from app.models.reporte import Reporte, ReporteEvidencia
from app.models.user import User
from app.services import notificacion_service, reporte_service

logger = logging.getLogger(__name__)

# Máquina de estados de la tarea: transiciones lineales permitidas (sin saltos).
_TRANSICIONES: dict[str, str] = {
    "pendiente": "en_ruta",
    "en_ruta": "en_sitio",
    "en_sitio": "cerrada",
}
_ESTADOS_VALIDOS = frozenset({"pendiente", "en_ruta", "en_sitio", "cerrada"})


def _apply_tenant_filter(stmt: Select, user: User) -> Select:
    return stmt.where(Tarea.tenant_id == user.tenant_id)


async def _get_tarea_or_404(tarea_id: str, user: User, db: AsyncSession) -> Tarea:
    result = await db.execute(
        select(Tarea).where(Tarea.id == tarea_id, Tarea.tenant_id == user.tenant_id)
    )
    tarea = result.scalar_one_or_none()
    if tarea is None:
        raise NotFoundError("Tarea", tarea_id)
    return tarea


async def _validar_cuadrilla(
    cuadrilla_id: str, user: User, db: AsyncSession
) -> Cuadrilla:
    result = await db.execute(
        select(Cuadrilla).where(
            Cuadrilla.id == cuadrilla_id, Cuadrilla.tenant_id == user.tenant_id
        )
    )
    cuad = result.scalar_one_or_none()
    if cuad is None:
        raise NotFoundError("Cuadrilla", cuadrilla_id)
    return cuad


async def _validar_integrante(
    integrante_id: str, cuadrilla_id: str, user: User, db: AsyncSession
) -> Integrante:
    result = await db.execute(
        select(Integrante).where(
            Integrante.id == integrante_id,
            Integrante.tenant_id == user.tenant_id,
            Integrante.cuadrilla_id == cuadrilla_id,
        )
    )
    integ = result.scalar_one_or_none()
    if integ is None:
        raise NotFoundError("Integrante", integrante_id)
    return integ


# ─────────────────────────────────────────────────────────────────────────────
# Mi-ruta (trabajador de campo vinculado por Integrante.user_id)
# ─────────────────────────────────────────────────────────────────────────────


async def integrante_de_usuario(user: User, db: AsyncSession) -> Integrante | None:
    """Resuelve el Integrante vinculado al ``user`` actual (por ``user_id``).

    Filtra por tenant del usuario. Devuelve ``None`` si la cuenta no está
    vinculada a ningún integrante de campo (p. ej. un supervisor sin cuadrilla).
    """
    result = await db.execute(
        select(Integrante).where(
            Integrante.user_id == user.id,
            Integrante.tenant_id == user.tenant_id,
        )
    )
    return result.scalar_one_or_none()


async def tareas_de_cuadrilla_ruteadas(
    cuadrilla_id: str, user: User, db: AsyncSession
) -> list[Tarea]:
    """Lista las tareas de una cuadrilla ordenadas como ruta de trabajo.

    Orden: primero las ruteadas por ``orden_ruta`` ascendente (las que no tienen
    orden van al final), luego por prioridad (crítica → baja) y fecha de creación.
    """
    prioridad_orden = {"critica": 0, "alta": 1, "media": 2, "baja": 3}
    stmt = (
        _apply_tenant_filter(select(Tarea), user)
        .where(Tarea.cuadrilla_id == cuadrilla_id)
        .order_by(
            Tarea.orden_ruta.is_(None),
            Tarea.orden_ruta.asc(),
            Tarea.created_at.asc(),
        )
    )
    result = await db.execute(stmt)
    tareas = list(result.scalars().all())
    # Desempate fino por prioridad dentro del mismo tramo de orden_ruta (estable).
    tareas.sort(
        key=lambda t: (
            t.orden_ruta is None,
            t.orden_ruta if t.orden_ruta is not None else 0,
            prioridad_orden.get(t.prioridad, 99),
            t.created_at,
        )
    )
    return tareas


# ─────────────────────────────────────────────────────────────────────────────
# Lectura
# ─────────────────────────────────────────────────────────────────────────────


async def list_tareas(
    user: User,
    db: AsyncSession,
    *,
    estado: str | None = None,
    cuadrilla_id: str | None = None,
    colonia_id: str | None = None,
) -> list[Tarea]:
    """Lista tareas del tenant, filtrando por estado, cuadrilla y/o colonia.

    Ordena por ``orden_ruta`` (las ruteadas primero) y luego por fecha de creación.
    """
    stmt = _apply_tenant_filter(select(Tarea), user)
    if estado is not None:
        stmt = stmt.where(Tarea.estado == estado)
    if cuadrilla_id is not None:
        stmt = stmt.where(Tarea.cuadrilla_id == cuadrilla_id)
    if colonia_id is not None:
        stmt = stmt.where(Tarea.colonia_id == colonia_id)
    stmt = stmt.order_by(
        Tarea.orden_ruta.is_(None), Tarea.orden_ruta.asc(), Tarea.created_at.asc()
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_tarea(tarea_id: str, user: User, db: AsyncSession) -> Tarea:
    """Obtiene una tarea del tenant o lanza ``NotFoundError``."""
    return await _get_tarea_or_404(tarea_id, user, db)


# ─────────────────────────────────────────────────────────────────────────────
# Creación
# ─────────────────────────────────────────────────────────────────────────────


async def crear_tarea_desde_reporte(
    reporte_id: str,
    user: User,
    db: AsyncSession,
    audit: AuditLogger,
    *,
    cuadrilla_id: str | None = None,
    integrante_id: str | None = None,
    instrucciones: str | None = None,
) -> Tarea:
    """Crea una tarea originada en un reporte ciudadano.

    Copia título/coordenadas/colonia del reporte. Si se pasa ``cuadrilla_id``, la
    deja asignada (estado ``pendiente``). Valida que el reporte (y la cuadrilla)
    pertenezcan al tenant del usuario.
    """
    result = await db.execute(
        select(Reporte).where(
            Reporte.id == reporte_id, Reporte.tenant_id == user.tenant_id
        )
    )
    reporte = result.scalar_one_or_none()
    if reporte is None:
        raise NotFoundError("Reporte", reporte_id)

    if cuadrilla_id is not None:
        await _validar_cuadrilla(cuadrilla_id, user, db)
        if integrante_id is not None:
            await _validar_integrante(integrante_id, cuadrilla_id, user, db)
    elif integrante_id is not None:
        raise ConflictError("No se puede asignar un integrante sin cuadrilla.")

    tarea = Tarea(
        tenant_id=user.tenant_id,
        cuadrilla_id=cuadrilla_id,
        integrante_id=integrante_id,
        origen_tipo="reporte",
        reporte_id=reporte_id,
        titulo=(reporte.titulo or "Tarea de campo")[:200],
        descripcion=reporte.descripcion,
        prioridad=reporte.prioridad or "media",
        estado="pendiente",
        lat=reporte.lat,
        lng=reporte.lng,
        colonia_id=reporte.colonia_id,
        instrucciones=instrucciones,
    )
    db.add(tarea)
    await db.flush()

    await audit.log(
        action="create",
        user_id=user.id,
        tenant_id=user.tenant_id,
        entity_type="tarea",
        entity_id=tarea.id,
        extra={"origen_tipo": "reporte", "reporte_id": reporte_id},
    )
    return tarea


async def crear_tarea_desde_obra(
    obra_id: str,
    user: User,
    db: AsyncSession,
    audit: AuditLogger,
    *,
    cuadrilla_id: str | None = None,
    integrante_id: str | None = None,
    titulo: str | None = None,
    instrucciones: str | None = None,
) -> Tarea:
    """Crea una tarea originada en una obra.

    Copia centro/colonia de la obra. Permite sobrescribir el ``titulo``. Valida que
    la obra (y la cuadrilla) pertenezcan al tenant del usuario.
    """
    result = await db.execute(
        select(Obra).where(Obra.id == obra_id, Obra.tenant_id == user.tenant_id)
    )
    obra = result.scalar_one_or_none()
    if obra is None:
        raise NotFoundError("Obra", obra_id)

    if cuadrilla_id is not None:
        await _validar_cuadrilla(cuadrilla_id, user, db)
        if integrante_id is not None:
            await _validar_integrante(integrante_id, cuadrilla_id, user, db)
    elif integrante_id is not None:
        raise ConflictError("No se puede asignar un integrante sin cuadrilla.")

    tarea = Tarea(
        tenant_id=user.tenant_id,
        cuadrilla_id=cuadrilla_id,
        integrante_id=integrante_id,
        origen_tipo="obra",
        obra_id=obra_id,
        titulo=(titulo or obra.nombre or "Tarea de obra")[:200],
        descripcion=obra.descripcion,
        prioridad=obra.prioridad or "media",
        estado="pendiente",
        lat=obra.center_lat,
        lng=obra.center_lng,
        colonia_id=obra.colonia_id,
        instrucciones=instrucciones,
    )
    db.add(tarea)
    await db.flush()

    await audit.log(
        action="create",
        user_id=user.id,
        tenant_id=user.tenant_id,
        entity_type="tarea",
        entity_id=tarea.id,
        extra={"origen_tipo": "obra", "obra_id": obra_id},
    )
    return tarea


async def crear_tarea_manual(
    titulo: str,
    user: User,
    db: AsyncSession,
    audit: AuditLogger,
    *,
    descripcion: str | None = None,
    prioridad: str = "media",
    cuadrilla_id: str | None = None,
    integrante_id: str | None = None,
    lat: float | None = None,
    lng: float | None = None,
    colonia_id: str | None = None,
    instrucciones: str | None = None,
    checklist: list[dict] | None = None,
) -> Tarea:
    """Crea una tarea manual (sin origen en reporte/obra).

    Valida que la cuadrilla (y el integrante) pertenezcan al tenant del usuario.
    """
    if cuadrilla_id is not None:
        await _validar_cuadrilla(cuadrilla_id, user, db)
        if integrante_id is not None:
            await _validar_integrante(integrante_id, cuadrilla_id, user, db)
    elif integrante_id is not None:
        raise ConflictError("No se puede asignar un integrante sin cuadrilla.")

    tarea = Tarea(
        tenant_id=user.tenant_id,
        cuadrilla_id=cuadrilla_id,
        integrante_id=integrante_id,
        origen_tipo="manual",
        titulo=titulo[:200],
        descripcion=descripcion,
        prioridad=prioridad,
        estado="pendiente",
        lat=lat,
        lng=lng,
        colonia_id=colonia_id,
        instrucciones=instrucciones,
        checklist=checklist or [],
    )
    db.add(tarea)
    await db.flush()

    await audit.log(
        action="create",
        user_id=user.id,
        tenant_id=user.tenant_id,
        entity_type="tarea",
        entity_id=tarea.id,
        extra={"origen_tipo": "manual"},
    )
    return tarea


async def crear_ticket_desde_proyecto_tarea(
    proyecto_tarea_id: str,
    user: User,
    db: AsyncSession,
    audit: AuditLogger,
    *,
    cuadrilla_id: str | None = None,
) -> Tarea:
    """Crea un ticket de cuadrilla (tarea de campo) espejo de una tarea de proyecto.

    El ticket «vive» en Cuadrillas (aparece en el Monitor); la tarea de proyecto
    solo se replica como espejo de solo-avance. Evita duplicar tickets abiertos.
    """
    pt = (
        await db.execute(
            select(ProyectoTarea).where(
                ProyectoTarea.id == proyecto_tarea_id,
                ProyectoTarea.tenant_id == user.tenant_id,
            )
        )
    ).scalar_one_or_none()
    if pt is None:
        raise NotFoundError("Tarea de proyecto", proyecto_tarea_id)

    existente = (
        await db.execute(
            select(Tarea).where(
                Tarea.tenant_id == user.tenant_id,
                Tarea.proyecto_tarea_id == proyecto_tarea_id,
                Tarea.estado != "cerrada",
            )
        )
    ).scalar_one_or_none()
    if existente is not None:
        raise ConflictError(
            "Ya existe un ticket de cuadrilla abierto para esta tarea de proyecto."
        )

    if cuadrilla_id is not None:
        await _validar_cuadrilla(cuadrilla_id, user, db)

    tarea = Tarea(
        tenant_id=user.tenant_id,
        cuadrilla_id=cuadrilla_id,
        origen_tipo="proyecto",
        proyecto_id=pt.proyecto_id,
        proyecto_tarea_id=pt.id,
        titulo=(pt.nombre or "Ticket de cuadrilla")[:200],
        prioridad="media",
        estado="pendiente",
    )
    db.add(tarea)
    await db.flush()

    await audit.log(
        action="create",
        user_id=user.id,
        tenant_id=user.tenant_id,
        entity_type="tarea",
        entity_id=tarea.id,
        extra={
            "origen_tipo": "proyecto",
            "proyecto_id": pt.proyecto_id,
            "proyecto_tarea_id": pt.id,
        },
    )
    return tarea


# ─────────────────────────────────────────────────────────────────────────────
# Asignación y máquina de estados
# ─────────────────────────────────────────────────────────────────────────────


async def asignar(
    tarea_id: str,
    cuadrilla_id: str,
    user: User,
    db: AsyncSession,
    audit: AuditLogger,
    *,
    integrante_id: str | None = None,
) -> Tarea:
    """Asigna (o reasigna) una tarea a una cuadrilla y, opcionalmente, a un integrante.

    Valida cuadrilla/integrante dentro del tenant. El integrante debe pertenecer a
    la cuadrilla indicada.
    """
    tarea = await _get_tarea_or_404(tarea_id, user, db)
    await _validar_cuadrilla(cuadrilla_id, user, db)
    if integrante_id is not None:
        await _validar_integrante(integrante_id, cuadrilla_id, user, db)

    old = {"cuadrilla_id": tarea.cuadrilla_id, "integrante_id": tarea.integrante_id}
    tarea.cuadrilla_id = cuadrilla_id
    tarea.integrante_id = integrante_id
    await db.flush()

    await audit.log(
        action="update",
        user_id=user.id,
        tenant_id=user.tenant_id,
        entity_type="tarea",
        entity_id=tarea.id,
        changes={
            "cuadrilla_id": {"old": old["cuadrilla_id"], "new": cuadrilla_id},
            "integrante_id": {"old": old["integrante_id"], "new": integrante_id},
        },
    )
    return tarea


async def cambiar_estado(
    tarea_id: str,
    nuevo_estado: str,
    user: User,
    db: AsyncSession,
    audit: AuditLogger,
) -> Tarea:
    """Avanza la tarea por la máquina de estados, rechazando saltos inválidos.

    Transiciones permitidas: ``pendiente -> en_ruta -> en_sitio -> cerrada``. Para
    llegar a ``cerrada`` usa :func:`cerrar_tarea` (valida evidencia y propaga al
    reporte); aquí se redirige a esa función para no duplicar reglas.
    """
    if nuevo_estado not in _ESTADOS_VALIDOS:
        raise ConflictError(f"Estado de tarea inválido: '{nuevo_estado}'.")

    tarea = await _get_tarea_or_404(tarea_id, user, db)

    if nuevo_estado == tarea.estado:
        raise ConflictError(f"La tarea ya está en estado '{nuevo_estado}'.")

    if _TRANSICIONES.get(tarea.estado) != nuevo_estado:
        raise ConflictError(
            f"Transición inválida: '{tarea.estado}' -> '{nuevo_estado}'. "
            f"La secuencia válida es pendiente -> en_ruta -> en_sitio -> cerrada."
        )

    if nuevo_estado == "cerrada":
        return await cerrar_tarea(tarea_id, user, db, audit)

    old_estado = tarea.estado
    tarea.estado = nuevo_estado
    await db.flush()

    await audit.log(
        action="update",
        user_id=user.id,
        tenant_id=user.tenant_id,
        entity_type="tarea",
        entity_id=tarea.id,
        changes={"estado": {"old": old_estado, "new": nuevo_estado}},
    )
    return tarea


async def cerrar_tarea(
    tarea_id: str,
    user: User,
    db: AsyncSession,
    audit: AuditLogger,
    *,
    nota: str | None = None,
) -> Tarea:
    """Cierra una tarea, exigiendo evidencia antes/después y propagando al reporte.

    Reglas:
      1. La tarea debe estar en ``en_sitio`` (la transición previa es obligatoria).
      2. Si la tarea proviene de un reporte, ese reporte DEBE tener al menos una
         evidencia ``momento='antes'`` y otra ``momento='despues'``; si no, se
         rechaza con ``ConflictError``.
      3. Marca la tarea ``cerrada`` + ``fecha_cierre``.
      4. Para tareas de reporte: pasa el reporte a ``resuelto`` reusando
         ``reporte_service.marcar_resuelto_desde_campo`` (tiempos de atención) y
         notifica a los responsables (defensivo).

    Filtra por tenant del usuario.
    """
    tarea = await _get_tarea_or_404(tarea_id, user, db)

    if tarea.estado == "cerrada":
        raise ConflictError("La tarea ya está cerrada.")
    if tarea.estado != "en_sitio":
        raise ConflictError(
            f"Solo se puede cerrar una tarea en 'en_sitio' (estado actual: "
            f"'{tarea.estado}')."
        )

    reporte: Reporte | None = None
    if tarea.origen_tipo == "reporte" and tarea.reporte_id is not None:
        result = await db.execute(
            select(Reporte).where(
                Reporte.id == tarea.reporte_id,
                Reporte.tenant_id == user.tenant_id,
            )
        )
        reporte = result.scalar_one_or_none()
        if reporte is None:
            raise NotFoundError("Reporte", tarea.reporte_id)

        momentos = await db.execute(
            select(ReporteEvidencia.momento).where(
                ReporteEvidencia.reporte_id == tarea.reporte_id
            )
        )
        presentes = {m for (m,) in momentos.all() if m}
        if "antes" not in presentes or "despues" not in presentes:
            raise ConflictError("evidencia antes/después obligatoria para cerrar")

    old_estado = tarea.estado
    tarea.estado = "cerrada"
    tarea.fecha_cierre = datetime.now(UTC)
    tarea.cierre_nota = nota or f"Cerrada en campo por {user.nombre} con evidencia de cuadrilla."
    await db.flush()

    await audit.log(
        action="update",
        user_id=user.id,
        tenant_id=user.tenant_id,
        entity_type="tarea",
        entity_id=tarea.id,
        changes={"estado": {"old": old_estado, "new": "cerrada"}},
    )

    # Sincronización espejo (REQ-07): si el ticket nace de una tarea de proyecto,
    # refleja el cierre en la tarea de proyecto (solo-avance) y adjunta la nota.
    if tarea.proyecto_tarea_id is not None:
        pt = (
            await db.execute(
                select(ProyectoTarea).where(
                    ProyectoTarea.id == tarea.proyecto_tarea_id,
                    ProyectoTarea.tenant_id == user.tenant_id,
                )
            )
        ).scalar_one_or_none()
        if pt is not None:
            pt.estado = "completada"
            pt.avance_pct = 100
            await db.flush()
            await audit.log(
                action="update",
                user_id=user.id,
                tenant_id=user.tenant_id,
                entity_type="proyecto_tarea",
                entity_id=pt.id,
                extra={
                    "espejo_de_ticket": tarea.id,
                    "cierre_nota": tarea.cierre_nota,
                },
            )

    if reporte is not None:
        await reporte_service.marcar_resuelto_desde_campo(
            reporte,
            db,
            actor_nombre=user.nombre,
            nota="Tarea de campo cerrada con evidencia antes/después.",
        )
        # Notifica a los responsables del cierre (defensivo: nunca rompe el flujo).
        try:
            await notificacion_service.notificar_responsables(
                db,
                tenant_id=user.tenant_id,
                tipo="cierre",
                titulo=f"Reporte {reporte.folio} · resuelto en campo",
                cuerpo=(
                    f"{reporte.titulo} — cerrado por {user.nombre} "
                    f"con evidencia antes/después."
                ),
                href=f"/reportes/{reporte.id}",
                entity_type="reporte",
                entity_id=reporte.id,
                categoria_id=reporte.categoria_id,
                excluir_user_id=user.id,
            )
        except Exception:  # noqa: BLE001 — las notificaciones nunca rompen el flujo
            logger.exception(
                "No se pudo notificar el cierre en campo del reporte %s", reporte.id
            )

    return tarea
