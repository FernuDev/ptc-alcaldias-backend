"""Herramientas que el LLM puede invocar para consultar datos en vivo y
preparar acciones con confirmación humana.

Cada herramienta se ejecuta SIEMPRE con el `User` autenticado, delegando en los
services existentes (reporte/obra/stats) que ya aplican el filtro por tenant +
área. Así, el modelo nunca obtiene datos fuera del alcance del usuario: si pide
un folio de otra área/tenant, la herramienta responde "sin coincidencias".
"""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agente import analytics
from app.agente.context import RolConceptual, UsuarioContexto, derive_contexto
from app.models.colonia import Colonia
from app.models.contratista import Contratista
from app.models.cuadrilla import Cuadrilla
from app.models.user import User
from app.schemas.obra import ObraCreate, ObraRead
from app.schemas.reporte import ReporteRead
from app.services import obra_service, reporte_service

# ─── Permisos por rol ─────────────────────────────────────────────────────

# Acciones que cada rol conceptual puede ejecutar via el agente.
_ACCIONES_POR_ROL: dict[RolConceptual, set[str]] = {
    "operador": {"cambiar_estado"},
    "supervisor": {"cambiar_estado", "asignar", "turnar"},
    "director": {"cambiar_estado", "asignar", "turnar", "cerrar", "crear_obra"},
    "administrador": {"cambiar_estado", "asignar", "turnar", "cerrar", "crear_obra"},
}

# ─── Esquemas de herramientas (formato OpenAI tools) ───────────────────────

_TOOLS_LECTURA: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "consultar_reporte",
            "description": (
                "Devuelve el detalle de un reporte ciudadano por su folio "
                "(p. ej. MC-2026-0358) o id. Solo dentro del alcance del usuario."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "referencia": {"type": "string", "description": "Folio o id del reporte"}
                },
                "required": ["referencia"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "buscar_reportes",
            "description": (
                "Busca reportes con filtros opcionales y devuelve una lista resumida. "
                "Útil para 'cuántos reportes críticos hay', 'reportes en proceso de bacheo', etc."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "texto": {"type": "string", "description": "Texto a buscar"},
                    "estado": {
                        "type": "string",
                        "enum": ["nuevo", "asignado", "en_proceso", "resuelto", "cerrado"],
                    },
                    "prioridad": {"type": "string", "enum": ["baja", "media", "alta", "critica"]},
                    "categoria": {"type": "string", "description": "id de categoría"},
                    "limite": {"type": "integer", "description": "Máximo de resultados (≤20)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_obra",
            "description": "Devuelve el detalle de una obra por folio o id (dentro del alcance).",
            "parameters": {
                "type": "object",
                "properties": {"referencia": {"type": "string"}},
                "required": ["referencia"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "navegar",
            "description": (
                "Genera un enlace para abrir una pantalla del sistema (el usuario lo pulsa). "
                "Úsalo cuando pidan ver/ir a una pantalla, o al detalle de un reporte u obra. "
                "Úsalo también de forma proactiva cuando respondas sobre un reporte u obra "
                "para ofrecer acceso al detalle."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "destino": {
                        "type": "string",
                        "enum": [
                            "dashboard", "bandeja", "reportes", "obras",
                            "personal", "configuracion", "reporte", "obra",
                        ],
                    },
                    "referencia": {
                        "type": "string",
                        "description": "Folio o id; requerido si destino es 'reporte' u 'obra'",
                    },
                },
                "required": ["destino"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "metricas",
            "description": (
                "Calcula métricas agregadas del área/tenant del usuario. intents válidos: "
                + ", ".join(analytics.INTENTS)
                + "."
            ),
            "parameters": {
                "type": "object",
                "properties": {"intent": {"type": "string"}},
                "required": ["intent"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "detectar_duplicados",
            "description": (
                "Detecta posibles reportes DUPLICADOS de un reporte dado (folio o id): "
                "otros reportes que probablemente describen el mismo incidente, por "
                "cercanía geográfica (~150 m), ventana temporal, misma categoría y "
                "similitud de texto. Úsalo cuando pregunten si un reporte ya existe, "
                "si hay reportes repetidos, o antes de asignar para evitar trabajo doble."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "referencia": {"type": "string", "description": "Folio o id del reporte"}
                },
                "required": ["referencia"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sugerir_reclasificacion",
            "description": (
                "Sugiere una RECLASIFICACIÓN (categoría y prioridad) para un reporte "
                "dado (folio o id), apoyándose en el clasificador de IA. Indica si la "
                "categoría o prioridad actual deberían cambiar y por qué. Úsalo cuando "
                "duden si un reporte está bien clasificado o pidan revisar su prioridad."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "referencia": {"type": "string", "description": "Folio o id del reporte"}
                },
                "required": ["referencia"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "diagnostico",
            "description": (
                "Ejecuta un diagnóstico completo del estado de la alcaldía: KPIs, "
                "distribución por categoría y estado, top colonias, SLA, ranking de "
                "cuadrillas, costos y actividad reciente. Úsalo cuando el usuario pida "
                "un análisis general, recomendaciones, opinión sobre qué mejorar, o "
                "panorama de la situación de la alcaldía."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
]

_TOOL_PREPARAR_ACCION: dict = {
    "type": "function",
    "function": {
        "name": "preparar_accion",
        "description": (
            "Prepara una acción sobre un reporte u obra que REQUIERE confirmación humana. "
            "Nunca muta el sistema directamente: crea una propuesta pendiente que el "
            "funcionario puede confirmar o rechazar. Tipos: asignar (turnar a cuadrilla/"
            "contratista), cambiar_estado, cerrar."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "tipo": {
                    "type": "string",
                    "enum": ["asignar", "turnar", "cambiar_estado", "cerrar"],
                    "description": "Tipo de acción a preparar.",
                },
                "entity_type": {
                    "type": "string",
                    "enum": ["reporte", "obra"],
                },
                "entity_id": {
                    "type": "string",
                    "description": "ID del reporte u obra (no folio). Usa el id devuelto por consultar_reporte/obra.",
                },
                "params": {
                    "type": "object",
                    "description": (
                        "Parámetros de la acción. Para asignar reporte: {cuadrilla_id: 'MC-C01'}. "
                        "Para asignar obra: {contratista_id: '...'}. "
                        "Para cambiar_estado: {estado: 'en_proceso'}."
                    ),
                },
            },
            "required": ["tipo", "entity_type", "entity_id"],
        },
    },
}

_TOOL_LISTAR_CUADRILLAS: dict = {
    "type": "function",
    "function": {
        "name": "listar_cuadrillas",
        "description": (
            "Lista las cuadrillas del tenant con su carga de trabajo actual "
            "(reportes activos, resueltos, total). Úsalo para saber qué cuadrilla "
            "está disponible o tiene menor carga antes de asignar."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
}


_TOOL_CREAR_OBRA: dict = {
    "type": "function",
    "function": {
        "name": "crear_obra",
        "description": (
            "Crea una nueva obra pública. Requiere confirmación humana. "
            "Antes de llamar, usa listar_colonias y listar_contratistas para "
            "obtener los ids válidos."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "nombre": {"type": "string", "description": "Nombre descriptivo de la obra"},
                "descripcion": {"type": "string"},
                "categoria_id": {
                    "type": "string",
                    "enum": [
                        "agua_potable", "alumbrado", "drenaje", "edificios_publicos",
                        "escuelas", "imagen_urbana", "parques", "pavimentacion", "vialidad",
                    ],
                },
                "prioridad": {"type": "string", "enum": ["baja", "media", "alta", "estrategica"]},
                "colonia_id": {"type": "string", "description": "ID de la colonia (usa listar_colonias)"},
                "contratista_id": {"type": "string", "description": "ID del contratista (usa listar_contratistas). Opcional."},
                "fecha_inicio": {"type": "string", "description": "Fecha inicio ISO (YYYY-MM-DD)"},
                "fecha_fin_estimada": {"type": "string", "description": "Fecha fin estimada ISO (YYYY-MM-DD)"},
                "presupuesto_autorizado": {"type": "number", "description": "Presupuesto en MXN. Opcional."},
            },
            "required": ["nombre", "categoria_id", "prioridad", "colonia_id", "fecha_inicio", "fecha_fin_estimada"],
        },
    },
}

_TOOL_LISTAR_COLONIAS: dict = {
    "type": "function",
    "function": {
        "name": "listar_colonias",
        "description": "Lista las colonias del tenant del usuario. Úsalo para obtener el colonia_id al crear obras.",
        "parameters": {"type": "object", "properties": {}},
    },
}

_TOOL_LISTAR_CONTRATISTAS: dict = {
    "type": "function",
    "function": {
        "name": "listar_contratistas",
        "description": "Lista los contratistas disponibles con su calificación. Úsalo antes de asignar contratista a una obra.",
        "parameters": {"type": "object", "properties": {}},
    },
}


def tools_para_rol(ctx: UsuarioContexto) -> list[dict]:
    """Devuelve los tools disponibles según el rol del usuario."""
    tools = list(_TOOLS_LECTURA)
    acciones = _ACCIONES_POR_ROL.get(ctx.rol, set())
    if acciones:
        tools.append(_TOOL_PREPARAR_ACCION)
        if "asignar" in acciones or "turnar" in acciones:
            tools.append(_TOOL_LISTAR_CUADRILLAS)
        if "crear_obra" in acciones:
            tools.append(_TOOL_CREAR_OBRA)
            tools.append(_TOOL_LISTAR_COLONIAS)
            tools.append(_TOOL_LISTAR_CONTRATISTAS)
    return tools


# Mantener TOOLS_SCHEMA como alias para compatibilidad.
TOOLS_SCHEMA = _TOOLS_LECTURA


# ─── Resúmenes compactos (ahorran tokens) ──────────────────────────────────


def _resumen_reporte(r: ReporteRead) -> dict:
    return {
        "folio": r.folio,
        "id": r.id,
        "titulo": r.titulo,
        "categoria": r.categoria_id,
        "estado": r.estado,
        "prioridad": r.prioridad,
        "fuente": r.fuente,
        "colonia": r.colonia_nombre,
        "cuadrilla_id": r.cuadrilla_id,
        "descripcion": (r.descripcion or "")[:500],
        "fecha_creacion": r.fecha_creacion,
        "fecha_actualizacion": r.fecha_actualizacion,
        "fecha_cierre": r.fecha_cierre,
        "tiempo_atencion_horas": r.tiempo_atencion_horas,
        "costo_estimado": r.costo_estimado,
        "ciudadano": r.ciudadano_nombre,
        "evidencias": len(r.evidencias),
        "ultimos_eventos": [
            {"fecha": e.fecha, "tipo": e.tipo, "titulo": e.titulo} for e in r.eventos[-3:]
        ],
        "obras_relacionadas": r.obras_relacionadas_ids,
    }


def _resumen_obra(o: ObraRead) -> dict:
    return {
        "folio": o.folio,
        "id": o.id,
        "nombre": o.nombre,
        "categoria": o.categoria_id,
        "estado": o.estado,
        "prioridad": o.prioridad,
        "colonia": o.colonia_nombre,
        "avance_pct": o.avance_pct,
        "responsable": o.responsable_nombre,
        "contratista_id": o.contratista_id,
        "fecha_inicio": o.fecha_inicio,
        "fecha_fin_estimada": o.fecha_fin_estimada,
        "fecha_fin_real": o.fecha_fin_real,
        "presupuesto_autorizado": o.presupuesto_autorizado,
        "presupuesto_ejercido": o.presupuesto_ejercido,
        "descripcion": (o.descripcion or "")[:500],
    }


# ─── Implementaciones (todas con alcance del usuario) ──────────────────────


async def _consultar_reporte(args: dict, user: User, db: AsyncSession) -> dict:
    ref = str(args.get("referencia", "")).strip()
    if not ref:
        return {"error": "Falta 'referencia' (folio o id)."}
    pag = await reporte_service.list_reportes(user, db, page_size=5, search=ref)
    match = next(
        (r for r in pag.items if r.folio == ref or r.id == ref),
        pag.items[0] if pag.items else None,
    )
    if match is None:
        return {
            "encontrado": False,
            "referencia": ref,
            "mensaje": "Sin coincidencias en tu alcance.",
        }
    detalle = await reporte_service.get_reporte(match.id, user, db)
    return {"encontrado": True, **_resumen_reporte(detalle)}


async def _buscar_reportes(args: dict, user: User, db: AsyncSession) -> dict:
    def _lista(v):
        return [v] if v else None

    limite = min(int(args.get("limite") or 10), 20)
    pag = await reporte_service.list_reportes(
        user,
        db,
        page_size=limite,
        search=args.get("texto") or None,
        estados=_lista(args.get("estado")),
        prioridades=_lista(args.get("prioridad")),
        categorias=_lista(args.get("categoria")),
    )
    return {
        "total": pag.total,
        "mostrados": len(pag.items),
        "reportes": [
            {
                "folio": r.folio,
                "titulo": r.titulo,
                "estado": r.estado,
                "prioridad": r.prioridad,
                "categoria": r.categoria_id,
                "colonia": r.colonia_nombre,
                "fecha_creacion": r.fecha_creacion,
            }
            for r in pag.items
        ],
    }


async def _consultar_obra(args: dict, user: User, db: AsyncSession) -> dict:
    ref = str(args.get("referencia", "")).strip()
    if not ref:
        return {"error": "Falta 'referencia' (folio o id)."}
    pag = await obra_service.list_obras(user, db, page_size=5, search=ref)
    match = next(
        (o for o in pag.items if o.folio == ref or o.id == ref),
        pag.items[0] if pag.items else None,
    )
    if match is None:
        return {
            "encontrado": False,
            "referencia": ref,
            "mensaje": "Sin coincidencias en tu alcance.",
        }
    detalle = await obra_service.get_obra(match.id, user, db)
    return {"encontrado": True, **_resumen_obra(detalle)}


# Pantallas fijas del backoffice (sin parámetro).
_RUTAS_FIJAS = {
    "dashboard": ("/backoffice", "Panel principal"),
    "bandeja": ("/backoffice/bandeja", "Bandeja de reportes"),
    "reportes": ("/backoffice/reportes", "Analítica de reportes"),
    "obras": ("/backoffice/obras", "Obras"),
    "personal": ("/backoffice/personal", "Personal"),
    "configuracion": ("/backoffice/configuracion", "Configuración"),
}


async def _navegar(args: dict, user: User, db: AsyncSession) -> dict:
    destino = str(args.get("destino", "")).strip()

    if destino in _RUTAS_FIJAS:
        href, titulo = _RUTAS_FIJAS[destino]
        return {"navegacion": {"href": href, "titulo": titulo}}

    # Pantallas de detalle: se valida el alcance resolviendo el folio/id.
    ref = str(args.get("referencia", "")).strip()
    if destino in ("reporte", "obra") and not ref:
        return {"error": f"Falta 'referencia' para abrir el detalle de {destino}."}

    if destino == "reporte":
        pag = await reporte_service.list_reportes(user, db, page_size=5, search=ref)
        match = next(
            (r for r in pag.items if r.folio == ref or r.id == ref),
            pag.items[0] if pag.items else None,
        )
        if match is None:
            return {"encontrado": False, "mensaje": "Sin coincidencias en tu alcance."}
        return {
            "navegacion": {
                "href": f"/backoffice/reportes/{match.id}",
                "titulo": f"Reporte {match.folio}",
            }
        }

    if destino == "obra":
        pag = await obra_service.list_obras(user, db, page_size=5, search=ref)
        match = next(
            (o for o in pag.items if o.folio == ref or o.id == ref),
            pag.items[0] if pag.items else None,
        )
        if match is None:
            return {"encontrado": False, "mensaje": "Sin coincidencias en tu alcance."}
        return {
            "navegacion": {
                "href": f"/backoffice/obras/{match.id}",
                "titulo": f"Obra {match.folio}",
            }
        }

    return {"error": f"destino desconocido: {destino}"}


async def _metricas(args: dict, user: User, db: AsyncSession) -> dict:
    intent = str(args.get("intent", "")).strip()
    if intent not in analytics.INTENTS:
        return {"error": f"intent inválido. Opciones: {list(analytics.INTENTS)}"}
    datos = await analytics.ejecutar_intent(intent, user, db)
    return {"intent": intent, "datos": datos}


async def _listar_cuadrillas(args: dict, user: User, db: AsyncSession) -> dict:
    from app.models.reporte import Reporte

    stmt = (
        select(
            Cuadrilla.id,
            Cuadrilla.nombre,
            func.count(Reporte.id)
            .filter(Reporte.estado.in_(["asignado", "en_proceso"]))
            .label("activos"),
            func.count(Reporte.id)
            .filter(Reporte.estado.in_(["resuelto", "cerrado"]))
            .label("resueltos"),
            func.count(Reporte.id).label("total"),
        )
        .outerjoin(Reporte, Reporte.cuadrilla_id == Cuadrilla.id)
        .where(Cuadrilla.tenant_id == user.tenant_id)
        .group_by(Cuadrilla.id, Cuadrilla.nombre)
        .order_by(Cuadrilla.id)
    )
    result = await db.execute(stmt)
    return {
        "cuadrillas": [
            {
                "id": row.id,
                "nombre": row.nombre,
                "reportes_activos": row.activos,
                "reportes_resueltos": row.resueltos,
                "reportes_total": row.total,
            }
            for row in result.all()
        ]
    }


async def _preparar_accion(args: dict, user: User, db: AsyncSession) -> dict:
    from app.agente import actions

    ctx = derive_contexto(user)
    tipo = str(args.get("tipo", "")).strip()
    entity_type = str(args.get("entity_type", "")).strip()
    entity_id = str(args.get("entity_id", "")).strip()
    params = args.get("params") or {}

    # Validar permisos del rol.
    acciones_permitidas = _ACCIONES_POR_ROL.get(ctx.rol, set())
    if tipo not in acciones_permitidas:
        return {
            "error": f"Tu rol ({ctx.rol}) no tiene permiso para la acción '{tipo}'. "
            f"Acciones disponibles: {sorted(acciones_permitidas) or 'ninguna'}."
        }

    if not entity_id:
        return {"error": "Falta entity_id. Consulta primero el reporte/obra para obtener su id."}

    prepared = await actions.preparar_accion(
        db, ctx, user,
        tipo=tipo,
        entity_type=entity_type,
        entity_id=entity_id,
        params=params,
    )
    return {
        "accion_preparada": True,
        "accion_id": prepared.accion_id,
        "descripcion": prepared.descripcion,
        "payload": prepared.payload,
        "requiere_confirmacion": True,
        "mensaje": (
            f"Acción preparada: {prepared.descripcion}. "
            "El funcionario debe confirmar antes de que se ejecute."
        ),
    }


async def _diagnostico(args: dict, user: User, db: AsyncSession) -> dict:
    """Ejecuta un diagnóstico y genera un análisis narrativo via LLM."""
    import json as _json

    from app.agente.llm.factory import get_llm_client

    datos: dict[str, Any] = {}
    for intent in ("kpis", "distribucion_categoria", "distribucion_estado",
                    "top_colonias", "tiempo_por_categoria", "ranking_cuadrillas",
                    "costo_operativo"):
        try:
            datos[intent] = await analytics.ejecutar_intent(intent, user, db)
        except Exception:
            pass

    datos_json = _json.dumps(datos, ensure_ascii=False, default=str)

    llm = get_llm_client()
    analisis = await llm.chat(
        [
            {
                "role": "system",
                "content": (
                    "Eres un analista de gestión pública. Se te entregan datos operativos "
                    "reales de una alcaldía. Redacta un diagnóstico con recomendaciones "
                    "CONCRETAS y ACCIONABLES. Cada recomendación debe citar el dato que "
                    "la sustenta. Estructura: 1) Situación general, 2) Áreas críticas por "
                    "categoría, 3) Colonias prioritarias, 4) Rendimiento de cuadrillas, "
                    "5) Recomendaciones (numeradas). Usa tablas y negritas. Sé directo."
                ),
            },
            {
                "role": "user",
                "content": f"Analiza estos datos y dame recomendaciones:\n{datos_json}",
            },
        ],
        max_tokens=3000,
    )

    return {"analisis": analisis}


async def _listar_colonias(args: dict, user: User, db: AsyncSession) -> dict:
    stmt = select(Colonia.id, Colonia.nombre).where(Colonia.tenant_id == user.tenant_id).order_by(Colonia.nombre)
    result = await db.execute(stmt)
    return {"colonias": [{"id": row.id, "nombre": row.nombre} for row in result.all()]}


async def _listar_contratistas(args: dict, user: User, db: AsyncSession) -> dict:
    stmt = select(Contratista.id, Contratista.razon_social, Contratista.calificacion).order_by(Contratista.id)
    result = await db.execute(stmt)
    return {
        "contratistas": [
            {"id": row.id, "razon_social": row.razon_social, "calificacion": float(row.calificacion) if row.calificacion else None}
            for row in result.all()
        ]
    }


async def _crear_obra(args: dict, user: User, db: AsyncSession) -> dict:
    from datetime import datetime

    from app.core.audit import AuditLogger

    ctx = derive_contexto(user)
    acciones_permitidas = _ACCIONES_POR_ROL.get(ctx.rol, set())
    if "crear_obra" not in acciones_permitidas:
        return {"error": f"Tu rol ({ctx.rol}) no tiene permiso para crear obras."}

    try:
        data = ObraCreate(
            nombre=args.get("nombre", ""),
            descripcion=args.get("descripcion"),
            categoria_id=args.get("categoria_id", ""),
            prioridad=args.get("prioridad", "media"),
            colonia_id=args.get("colonia_id", ""),
            contratista_id=args.get("contratista_id"),
            fecha_inicio=datetime.fromisoformat(args["fecha_inicio"]),
            fecha_fin_estimada=datetime.fromisoformat(args["fecha_fin_estimada"]),
            presupuesto_autorizado=args.get("presupuesto_autorizado"),
        )
    except (KeyError, ValueError) as e:
        return {"error": f"Datos inválidos: {e}"}

    audit = AuditLogger(db)
    obra = await obra_service.create_obra(data, user, db, audit)
    return {
        "creada": True,
        "obra_id": obra.id,
        "folio": obra.folio,
        "nombre": obra.nombre,
        "estado": obra.estado,
        "mensaje": f"Obra '{obra.nombre}' creada con folio {obra.folio} en estado planeación.",
    }


async def _resolver_reporte_id(ref: str, user: User, db: AsyncSession) -> str | None:
    """Resuelve un folio o id a un id de reporte dentro del alcance del usuario."""
    pag = await reporte_service.list_reportes(user, db, page_size=5, search=ref)
    match = next(
        (r for r in pag.items if r.folio == ref or r.id == ref),
        pag.items[0] if pag.items else None,
    )
    return match.id if match else None


async def _detectar_duplicados(args: dict, user: User, db: AsyncSession) -> dict:
    from app.agente import actions

    ref = str(args.get("referencia", "")).strip()
    if not ref:
        return {"error": "Falta 'referencia' (folio o id)."}
    reporte_id = await _resolver_reporte_id(ref, user, db)
    if reporte_id is None:
        return {
            "encontrado": False,
            "referencia": ref,
            "mensaje": "Sin coincidencias en tu alcance.",
        }

    base, candidatos = await actions.detectar_duplicados(reporte_id, user, db)
    return {
        "encontrado": True,
        "reporte": {"folio": base.folio, "id": base.id, "titulo": base.titulo},
        "total_duplicados": len(candidatos),
        "hay_duplicados": bool(candidatos),
        "duplicados": [
            {
                "folio": c.reporte.folio,
                "id": c.reporte.id,
                "titulo": c.reporte.titulo,
                "estado": c.reporte.estado,
                "colonia": c.reporte.colonia_nombre,
                "score": c.score,
                "confianza": c.confianza,
                "distancia_m": c.distancia_m,
                "horas_diferencia": c.horas_diferencia,
                "similitud_texto": c.similitud_texto,
                "motivos": c.motivos,
            }
            for c in candidatos
        ],
    }


async def _sugerir_reclasificacion(args: dict, user: User, db: AsyncSession) -> dict:
    from app.agente import actions

    ref = str(args.get("referencia", "")).strip()
    if not ref:
        return {"error": "Falta 'referencia' (folio o id)."}
    reporte_id = await _resolver_reporte_id(ref, user, db)
    if reporte_id is None:
        return {
            "encontrado": False,
            "referencia": ref,
            "mensaje": "Sin coincidencias en tu alcance.",
        }

    s = await actions.sugerir_reclasificacion(reporte_id, user, db)
    return {
        "encontrado": True,
        "reporte": {"folio": s.folio, "id": s.reporte_id},
        "categoria_actual": s.categoria_actual,
        "categoria_sugerida": s.categoria_sugerida,
        "cambia_categoria": s.cambia_categoria,
        "prioridad_actual": s.prioridad_actual,
        "prioridad_sugerida": s.prioridad_sugerida,
        "cambia_prioridad": s.cambia_prioridad,
        "es_emergencia": s.es_emergencia,
        "es_sensible": s.es_sensible,
        "justificacion": s.justificacion,
    }


_DISPATCH = {
    "consultar_reporte": _consultar_reporte,
    "buscar_reportes": _buscar_reportes,
    "consultar_obra": _consultar_obra,
    "navegar": _navegar,
    "metricas": _metricas,
    "diagnostico": _diagnostico,
    "detectar_duplicados": _detectar_duplicados,
    "sugerir_reclasificacion": _sugerir_reclasificacion,
    "listar_cuadrillas": _listar_cuadrillas,
    "listar_colonias": _listar_colonias,
    "listar_contratistas": _listar_contratistas,
    "crear_obra": _crear_obra,
    "preparar_accion": _preparar_accion,
}

ETIQUETAS = {
    "consultar_reporte": "Consulta de reporte",
    "buscar_reportes": "Búsqueda de reportes",
    "consultar_obra": "Consulta de obra",
    "navegar": "Navegación",
    "metricas": "Métricas del sistema",
    "diagnostico": "Diagnóstico integral",
    "detectar_duplicados": "Detección de duplicados",
    "sugerir_reclasificacion": "Sugerencia de reclasificación",
    "listar_cuadrillas": "Consulta de cuadrillas",
    "listar_colonias": "Consulta de colonias",
    "listar_contratistas": "Consulta de contratistas",
    "crear_obra": "Creación de obra",
    "preparar_accion": "Preparación de acción",
}


async def ejecutar_tool(name: str, args: dict, user: User, db: AsyncSession) -> Any:
    """Ejecuta una herramienta por nombre. Los errores se devuelven como dato
    (no se propagan) para que el modelo pueda explicarlos al usuario."""
    fn = _DISPATCH.get(name)
    if fn is None:
        return {"error": f"Herramienta desconocida: {name}"}
    try:
        return await fn(args, user, db)
    except Exception as exc:  # noqa: BLE001 (incluye NotFound/Forbidden por alcance)
        return {"error": str(exc)}
