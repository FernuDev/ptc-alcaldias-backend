"""Analítica por intents cerrados (caso de uso 4).

La aritmética la hace SQL a través de los servicios existentes
(`stats_service`), que YA aplican el filtro por tenant + área del usuario. El
modelo solo narra los números; nunca recalcula ni genera SQL. Esto evita
inyección y fugas de alcance, y reutiliza código probado.
"""

import json
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agente.context import UsuarioContexto
from app.agente.llm.base import LLMClient
from app.agente.prompts.system_prompt import SYSTEM_PROMPT
from app.models.user import User
from app.services import stats_service

# Registro cerrado: intent -> (descripción, función(user, db, params) -> datos).
IntentFn = Callable[[User, AsyncSession, dict], Awaitable[Any]]

INTENTS: dict[str, tuple[str, IntentFn]] = {
    "kpis": (
        "Indicadores clave (KPIs) del periodo",
        lambda u, db, p: stats_service.calc_kpis(u, db),
    ),
    "volumen_diario": (
        "Volumen de reportes por día (params: dias)",
        lambda u, db, p: stats_service.volumen_por_dia(u, db, dias=int(p.get("dias", 30))),
    ),
    "distribucion_categoria": (
        "Distribución de reportes por categoría",
        lambda u, db, p: stats_service.distribucion_categoria(u, db),
    ),
    "distribucion_estado": (
        "Distribución de reportes por estado",
        lambda u, db, p: stats_service.distribucion_estado(u, db),
    ),
    "top_colonias": (
        "Colonias con más reportes (params: n)",
        lambda u, db, p: stats_service.top_colonias(u, db, n=int(p.get("n", 6))),
    ),
    "sla_semanal": (
        "Cumplimiento de SLA por semana (params: semanas)",
        lambda u, db, p: stats_service.sla_semanal(u, db, semanas=int(p.get("semanas", 6))),
    ),
    "tiempo_por_categoria": (
        "Tiempo promedio de atención por categoría",
        lambda u, db, p: stats_service.tiempo_por_categoria(u, db),
    ),
    "ranking_cuadrillas": (
        "Ranking de desempeño de cuadrillas",
        lambda u, db, p: stats_service.ranking_cuadrillas(u, db),
    ),
    "costo_operativo": (
        "Costo operativo por categoría",
        lambda u, db, p: stats_service.costo_operativo(u, db),
    ),
    "actividad_reciente": (
        "Actividad reciente (params: n)",
        lambda u, db, p: stats_service.actividad_reciente(u, db, n=int(p.get("n", 6))),
    ),
}


def intents_disponibles() -> dict[str, str]:
    return {k: v[0] for k, v in INTENTS.items()}


def _serializar(datos: Any) -> Any:
    if isinstance(datos, list):
        return [d.model_dump() if hasattr(d, "model_dump") else d for d in datos]
    if hasattr(datos, "model_dump"):
        return datos.model_dump()
    return datos


async def ejecutar_intent(
    intent: str, user: User, db: AsyncSession, params: dict | None = None
) -> Any:
    """Ejecuta un intent del registro. Lanza ValueError si no existe."""
    if intent not in INTENTS:
        raise ValueError(f"Intent desconocido: {intent!r}")
    _, fn = INTENTS[intent]
    datos = await fn(user, db, params or {})
    return _serializar(datos)


async def seleccionar_intent(consulta: str, llm: LLMClient) -> str | None:
    """Mapea una consulta en lenguaje natural a un intent del registro (o None)."""
    catalogo = "\n".join(f"- {k}: {d}" for k, d in intents_disponibles().items())
    instruccion = (
        "Eres un enrutador. Dada la consulta del funcionario, elige el intent más "
        "adecuado de esta lista o 'ninguno'. Responde SOLO JSON: "
        '{"intent": "<nombre|ninguno>"}.\n\n' + catalogo
    )
    try:
        crudo = await llm.chat(
            [
                {"role": "system", "content": instruccion},
                {"role": "user", "content": consulta},
            ]
        )
        inicio, fin = crudo.index("{"), crudo.rindex("}") + 1
        intent = json.loads(crudo[inicio:fin]).get("intent")
        return intent if intent in INTENTS else None
    except Exception:
        return None


async def narrar(llm: LLMClient, intent: str, datos: Any, ctx: UsuarioContexto) -> str:
    """El modelo interpreta los números ya calculados (no recalcula)."""
    from app.agente.orchestrator import _bloque_usuario

    mensajes = [
        {"role": "system", "content": f"{SYSTEM_PROMPT}\n\n{_bloque_usuario(ctx)}"},
        {
            "role": "system",
            "content": (
                f"RESULTADO DE CONSULTA '{intent}' (narra e interpreta estos datos; "
                "NO recalcules ni inventes cifras):\n"
                f"{json.dumps(datos, ensure_ascii=False, default=str)}"
            ),
        },
        {"role": "user", "content": f"Resume e interpreta el resultado de '{intent}'."},
    ]
    return await llm.chat(mensajes)
