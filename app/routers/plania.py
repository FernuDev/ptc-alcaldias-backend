"""Router de Plan.IA — portafolio, proyectos, expediente de zona, interoperabilidad."""

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import DB, Audit, CurrentUser, require_permission
from app.core.permissions import Permission
from app.schemas.plania import (
    AprobacionCreate,
    AprobacionRead,
    AprobacionResolve,
    ConectorInterop,
    ConvertirZonaInput,
    ExpedienteZona,
    GenerarTicketInput,
    PortafolioResumen,
    ProyectoCreate,
    ProyectoListItem,
    ProyectoRead,
    ProyectoTareaRead,
    ProyectoUpdate,
    RiesgoCreate,
    RiesgoRead,
    RiesgoUpdate,
    StakeholderCreate,
    StakeholderRead,
    TareaCreate,
    TareaUpdate,
    TicketEspejoRead,
)
from app.services import plania_service as svc
from app.services import tarea_service

router = APIRouter(prefix="/plania", tags=["plania"])

_GestionObra = Depends(require_permission(Permission.OBRA_GESTIONAR))


# ── Portafolio ──────────────────────────────────────────────────────────────


@router.get("/portafolio", response_model=PortafolioResumen)
async def get_portafolio(user: CurrentUser, db: DB):
    return await svc.portafolio(user, db)


# ── Proyectos ───────────────────────────────────────────────────────────────


@router.get("/proyectos", response_model=list[ProyectoListItem])
async def listar_proyectos(
    user: CurrentUser,
    db: DB,
    tipo: str | None = Query(None),
    estado: str | None = Query(None),
):
    return await svc.listar_proyectos(user, db, tipo=tipo, estado=estado)


@router.get("/proyectos/{proyecto_id}", response_model=ProyectoRead)
async def get_proyecto(proyecto_id: str, user: CurrentUser, db: DB):
    return await svc.get_proyecto(proyecto_id, user, db)


@router.post("/proyectos", response_model=ProyectoRead, status_code=201)
async def crear_proyecto(
    data: ProyectoCreate, user: CurrentUser, db: DB, _=_GestionObra
):
    return await svc.crear_proyecto(data.model_dump(), user, db)


@router.put("/proyectos/{proyecto_id}", response_model=ProyectoRead)
async def actualizar_proyecto(
    proyecto_id: str,
    data: ProyectoUpdate,
    user: CurrentUser,
    db: DB,
    _=_GestionObra,
):
    return await svc.actualizar_proyecto(
        proyecto_id, data.model_dump(exclude_unset=True), user, db
    )


# ── Tareas del proyecto (plan de trabajo / Gantt) ───────────────────────────


@router.post(
    "/proyectos/{proyecto_id}/tareas",
    response_model=ProyectoTareaRead,
    status_code=201,
)
async def crear_tarea(
    proyecto_id: str,
    data: TareaCreate,
    user: CurrentUser,
    db: DB,
    _=_GestionObra,
):
    return await svc.crear_tarea(proyecto_id, data.model_dump(), user, db)


@router.put("/tareas/{tarea_id}", response_model=ProyectoTareaRead)
async def actualizar_tarea(
    tarea_id: str,
    data: TareaUpdate,
    user: CurrentUser,
    db: DB,
    _=_GestionObra,
):
    return await svc.actualizar_tarea(
        tarea_id, data.model_dump(exclude_unset=True), user, db
    )


# ── Puente Proyectos ↔ Cuadrillas (ticket espejo, REQ-07/QA-A) ──────────────


@router.post(
    "/tareas/{proyecto_tarea_id}/generar-ticket",
    response_model=TicketEspejoRead,
    status_code=201,
)
async def generar_ticket(
    proyecto_tarea_id: str,
    data: GenerarTicketInput,
    user: CurrentUser,
    db: DB,
    audit: Audit,
    _=_GestionObra,
):
    """Genera un ticket de cuadrilla (tarea de campo) espejo de una tarea de
    proyecto. El ticket aparece en el Monitor; al cerrarse, la tarea de proyecto
    se marca completada y queda la trazabilidad del origen."""
    return await tarea_service.crear_ticket_desde_proyecto_tarea(
        proyecto_tarea_id, user, db, audit, cuadrilla_id=data.cuadrilla_id
    )


# ── Expediente de zona (premium) ────────────────────────────────────────────


@router.get("/expediente-zona", response_model=list[ExpedienteZona])
async def expediente_zona(
    user: CurrentUser,
    db: DB,
    umbral: int | None = Query(None, ge=2, le=50),
    dias: int | None = Query(None, ge=7, le=730),
    radio: int | None = Query(None, ge=50, le=3000),
):
    # Sin overrides usa los parámetros configurados por tenant (Configuración).
    return await svc.expediente_zona(user, db, umbral=umbral, dias=dias, radio=radio)


@router.post(
    "/expediente-zona/convertir", response_model=ProyectoRead, status_code=201
)
async def convertir_zona(
    data: ConvertirZonaInput,
    user: CurrentUser,
    db: DB,
    audit: Audit,
    _=_GestionObra,
):
    return await svc.convertir_zona_en_proyecto(data.model_dump(), user, db, audit)


# ── Coordinación: stakeholders ──────────────────────────────────────────────


@router.get(
    "/proyectos/{proyecto_id}/stakeholders", response_model=list[StakeholderRead]
)
async def listar_stakeholders(proyecto_id: str, user: CurrentUser, db: DB):
    return await svc.listar_stakeholders(proyecto_id, user, db)


@router.post(
    "/proyectos/{proyecto_id}/stakeholders",
    response_model=StakeholderRead,
    status_code=201,
)
async def crear_stakeholder(
    proyecto_id: str,
    data: StakeholderCreate,
    user: CurrentUser,
    db: DB,
    _=_GestionObra,
):
    return await svc.crear_stakeholder(proyecto_id, data.model_dump(), user, db)


@router.delete("/stakeholders/{sid}")
async def eliminar_stakeholder(sid: str, user: CurrentUser, db: DB, _=_GestionObra):
    await svc.eliminar_stakeholder(sid, user, db)
    return {"detail": "Stakeholder eliminado"}


# ── Coordinación: riesgos ───────────────────────────────────────────────────


@router.get("/proyectos/{proyecto_id}/riesgos", response_model=list[RiesgoRead])
async def listar_riesgos(proyecto_id: str, user: CurrentUser, db: DB):
    return await svc.listar_riesgos(proyecto_id, user, db)


@router.post(
    "/proyectos/{proyecto_id}/riesgos", response_model=RiesgoRead, status_code=201
)
async def crear_riesgo(
    proyecto_id: str, data: RiesgoCreate, user: CurrentUser, db: DB, _=_GestionObra
):
    return await svc.crear_riesgo(proyecto_id, data.model_dump(), user, db)


@router.put("/riesgos/{rid}", response_model=RiesgoRead)
async def actualizar_riesgo(
    rid: str, data: RiesgoUpdate, user: CurrentUser, db: DB, _=_GestionObra
):
    return await svc.actualizar_riesgo(
        rid, data.model_dump(exclude_unset=True), user, db
    )


# ── Coordinación: flujo de aprobación ───────────────────────────────────────


@router.get(
    "/proyectos/{proyecto_id}/aprobaciones", response_model=list[AprobacionRead]
)
async def listar_aprobaciones(proyecto_id: str, user: CurrentUser, db: DB):
    return await svc.listar_aprobaciones(proyecto_id, user, db)


@router.post(
    "/proyectos/{proyecto_id}/aprobaciones",
    response_model=AprobacionRead,
    status_code=201,
)
async def crear_aprobacion(
    proyecto_id: str,
    data: AprobacionCreate,
    user: CurrentUser,
    db: DB,
    _=_GestionObra,
):
    return await svc.crear_aprobacion(proyecto_id, data.model_dump(), user, db)


@router.put("/aprobaciones/{aid}", response_model=AprobacionRead)
async def resolver_aprobacion(
    aid: str,
    data: AprobacionResolve,
    user: CurrentUser,
    db: DB,
    _=_GestionObra,
):
    return await svc.resolver_aprobacion(
        aid, data.estado, data.comentario, user, db
    )


# ── Interoperabilidad (catálogo, REQ-08) ────────────────────────────────────


@router.get("/interoperabilidad", response_model=list[ConectorInterop])
async def interoperabilidad(user: CurrentUser):
    return svc.CATALOGO_INTEROP
