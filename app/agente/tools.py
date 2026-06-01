"""Herramientas que el LLM puede invocar para consultar datos en vivo.

Cada herramienta se ejecuta SIEMPRE con el `User` autenticado, delegando en los
services existentes (reporte/obra/stats) que ya aplican el filtro por tenant +
área. Así, el modelo nunca obtiene datos fuera del alcance del usuario: si pide
un folio de otra área/tenant, la herramienta responde "sin coincidencias".
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agente import analytics
from app.models.user import User
from app.schemas.obra import ObraRead
from app.schemas.reporte import ReporteRead
from app.services import obra_service, reporte_service

# ─── Esquemas de herramientas (formato OpenAI tools) ───────────────────────

TOOLS_SCHEMA: list[dict] = [
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
                "Úsalo cuando pidan ver/ir a una pantalla, o al detalle de un reporte u obra."
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
]


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


_DISPATCH = {
    "consultar_reporte": _consultar_reporte,
    "buscar_reportes": _buscar_reportes,
    "consultar_obra": _consultar_obra,
    "navegar": _navegar,
    "metricas": _metricas,
}

ETIQUETAS = {
    "consultar_reporte": "Consulta de reporte",
    "buscar_reportes": "Búsqueda de reportes",
    "consultar_obra": "Consulta de obra",
    "navegar": "Navegación",
    "metricas": "Métricas del sistema",
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
