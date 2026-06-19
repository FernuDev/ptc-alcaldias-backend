"""Orquestador del Agente Ejecutivo (asistente del Alcalde).

REUTILIZA la infraestructura del Agente Institucional SIN editarla:
- Motor LLM (DeepSeek) vía ``app.agente.llm.factory.get_llm_client``.

A diferencia del Institucional (acotado por dirección/área), este orquestador
opera con visión CROSS-DIRECCIONES: agrega desempeño de TODO el tenant, lee el
cumplimiento de compromisos y estima el sentimiento ciudadano.

Las agregaciones globales se calculan aquí (tenant-wide, sin filtro por área)
para no tocar ``stats_service`` (cuyo ``_base_filter`` acota a las áreas del
usuario). Así el Ejecutivo siempre ve la alcaldía completa.
"""

import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import case, extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agente.llm.base import LLMClient, LLMError, Message
from app.agente.llm.factory import get_llm_client
from app.agente_ejecutivo.system_prompt import SYSTEM_PROMPT_EJECUTIVO
from app.core.config import settings
from app.models.categoria import Categoria
from app.models.reporte import Reporte
from app.models.user import User
from app.schemas.ejecutivo import (
    DesempenoArea,
    EjecutivoChatResponse,
    ResumenEjecutivo,
    SentimientoArea,
    SentimientoResponse,
)
from app.services import compromiso_service

ESTADOS_ABIERTOS = ("nuevo", "asignado", "en_proceso")

# Tamaño de la muestra de descripciones recientes que clasifica el LLM.
_MUESTRA_SENTIMIENTO = 30
_SENTIMIENTO_DIAS = 30


# ─── Desempeño global y por dirección (tenant-wide) ──────────────────────────


async def kpis_globales(tenant_id: str, db: AsyncSession) -> dict:
    """KPIs de TODA la alcaldía (sin acotar por área)."""
    now = datetime.now(UTC)
    base = [Reporte.tenant_id == tenant_id]

    total = (await db.execute(select(func.count()).select_from(Reporte).where(*base))).scalar() or 0
    activos = (
        await db.execute(
            select(func.count())
            .select_from(Reporte)
            .where(*base, Reporte.estado.in_(ESTADOS_ABIERTOS))
        )
    ).scalar() or 0
    resueltos = (
        await db.execute(
            select(func.count()).select_from(Reporte).where(*base, Reporte.estado == "resuelto")
        )
    ).scalar() or 0
    avg_hours = (
        await db.execute(
            select(func.avg(Reporte.tiempo_atencion_horas)).where(
                *base, Reporte.estado.in_(("resuelto", "cerrado"))
            )
        )
    ).scalar() or 0

    sla_case = case(
        (Reporte.prioridad == "critica", 12),
        (Reporte.prioridad == "alta", 48),
        (Reporte.prioridad == "media", 96),
        else_=168,
    )
    age_hours = extract("epoch", now - Reporte.fecha_creacion) / 3600
    en_riesgo = (
        await db.execute(
            select(func.count())
            .select_from(Reporte)
            .where(*base, Reporte.estado.in_(ESTADOS_ABIERTOS), age_hours > sla_case)
        )
    ).scalar() or 0

    return {
        "total": int(total),
        "activos": int(activos),
        "resueltos": int(resueltos),
        "en_riesgo_sla": int(en_riesgo),
        "tiempo_promedio_dias": round(float(avg_hours) / 24, 2) if avg_hours else 0.0,
        "pct_resueltos": round(resueltos / total * 100, 1) if total else 0.0,
    }


async def desempeno_por_direccion(tenant_id: str, db: AsyncSession) -> list[DesempenoArea]:
    """Desempeño por dirección/área para TODO el tenant."""
    now = datetime.now(UTC)
    base = [Reporte.tenant_id == tenant_id]
    sla_case = case(
        (Reporte.prioridad == "critica", 12),
        (Reporte.prioridad == "alta", 48),
        (Reporte.prioridad == "media", 96),
        else_=168,
    )
    age_hours = extract("epoch", now - Reporte.fecha_creacion) / 3600

    q = (
        select(
            Reporte.categoria_id,
            Categoria.label,
            func.count().label("total"),
            func.sum(case((Reporte.estado.in_(ESTADOS_ABIERTOS), 1), else_=0)).label("activos"),
            func.sum(case((Reporte.estado == "resuelto", 1), else_=0)).label("resueltos"),
            func.sum(
                case(
                    (
                        Reporte.estado.in_(ESTADOS_ABIERTOS) & (age_hours > sla_case),
                        1,
                    ),
                    else_=0,
                )
            ).label("en_riesgo"),
            func.avg(
                case(
                    (Reporte.estado.in_(("resuelto", "cerrado")), Reporte.tiempo_atencion_horas),
                    else_=None,
                )
            ).label("promedio"),
        )
        .join(Categoria, Reporte.categoria_id == Categoria.id)
        .where(*base)
        .group_by(Reporte.categoria_id, Categoria.label)
        .order_by(func.count().desc())
    )
    rows = (await db.execute(q)).all()
    resultado: list[DesempenoArea] = []
    for r in rows:
        total = int(r.total or 0)
        resueltos = int(r.resueltos or 0)
        resultado.append(
            DesempenoArea(
                area_id=r.categoria_id,
                label=r.label,
                activos=int(r.activos or 0),
                resueltos=resueltos,
                en_riesgo_sla=int(r.en_riesgo or 0),
                pct_resueltos=round(resueltos / total * 100, 1) if total else 0.0,
                tiempo_promedio_dias=round(float(r.promedio) / 24, 2) if r.promedio else 0.0,
            )
        )
    return resultado


# ─── Sentimiento ciudadano ───────────────────────────────────────────────────


async def _muestra_descripciones(tenant_id: str, db: AsyncSession) -> list[tuple[str, str]]:
    """Muestra reciente de (categoria_id, descripcion) para clasificar el tono."""
    since = datetime.now(UTC) - timedelta(days=_SENTIMIENTO_DIAS)
    q = (
        select(Reporte.categoria_id, Reporte.descripcion)
        .where(
            Reporte.tenant_id == tenant_id,
            Reporte.descripcion.isnot(None),
            Reporte.fecha_creacion >= since,
        )
        .order_by(Reporte.fecha_creacion.desc())
        .limit(_MUESTRA_SENTIMIENTO)
    )
    rows = (await db.execute(q)).all()
    return [(r.categoria_id, r.descripcion) for r in rows if r.descripcion]


async def _clasificar_tonos(
    descripciones: list[str], llm: LLMClient
) -> list[str]:
    """Clasifica cada descripción como positivo|neutral|negativo vía LLM.

    Tolerante a fallos: si el LLM falla o el parseo no cuadra, cae a heurística.
    Devuelve una lista del mismo largo que ``descripciones``.
    """
    if not descripciones:
        return []

    numeradas = "\n".join(f"{i + 1}. {d[:280]}" for i, d in enumerate(descripciones))
    instruccion = (
        "Eres un analista de percepción ciudadana. Clasifica el TONO de cada reporte "
        "vecinal sobre servicios públicos como 'positivo', 'neutral' o 'negativo' "
        "(la mayoría de las quejas son negativas o neutrales). Responde SOLO con un "
        'objeto JSON: {"tonos": ["negativo", "neutral", ...]} con exactamente un '
        "elemento por reporte, en orden."
    )
    mensajes: list[Message] = [
        {"role": "system", "content": instruccion},
        {"role": "user", "content": numeradas},
    ]
    try:
        crudo = await llm.chat(mensajes, temperature=0.0)
        inicio = crudo.index("{")
        fin = crudo.rindex("}") + 1
        datos = json.loads(crudo[inicio:fin])
        tonos = datos.get("tonos", [])
    except (LLMError, ValueError, json.JSONDecodeError, KeyError):
        tonos = []

    validos = {"positivo", "neutral", "negativo"}
    salida: list[str] = []
    for i in range(len(descripciones)):
        t = tonos[i] if i < len(tonos) else None
        salida.append(t if t in validos else _heuristica_tono(descripciones[i]))
    return salida


_PALABRAS_NEG = (
    "no sirve", "no funciona", "pesimo", "pésimo", "harto", "harta", "peligro",
    "urgente", "denuncia", "abandono", "nadie", "queja", "molesto", "molesta",
    "fuga", "basura", "rata", "inseguridad", "robo", "mal", "tirado",
)
_PALABRAS_POS = (
    "gracias", "excelente", "rapido", "rápido", "resuelto", "felicito",
    "atendieron", "buen", "buena", "mejor", "limpio",
)


def _heuristica_tono(texto: str) -> str:
    t = texto.lower()
    neg = sum(1 for p in _PALABRAS_NEG if p in t)
    pos = sum(1 for p in _PALABRAS_POS if p in t)
    if pos > neg:
        return "positivo"
    if neg > pos:
        return "negativo"
    return "neutral"


def _indice(positivo: int, negativo: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round((positivo - negativo) / total, 3)


def _etiqueta(indice: float) -> str:
    if indice >= 0.15:
        return "positivo"
    if indice <= -0.15:
        return "negativo"
    return "neutral"


async def analizar_sentimiento(
    tenant_id: str,
    db: AsyncSession,
    *,
    llm: LLMClient | None = None,
) -> SentimientoResponse:
    """Estima el sentimiento ciudadano agregando el tono de reportes recientes."""
    llm = llm or get_llm_client()
    muestra = await _muestra_descripciones(tenant_id, db)
    if not muestra:
        return SentimientoResponse(
            resumen="No hay reportes recientes para evaluar el ánimo ciudadano."
        )

    descripciones = [d for _, d in muestra]
    tonos = await _clasificar_tonos(descripciones, llm)

    labels_rows = await db.execute(select(Categoria.id, Categoria.label))
    labels = {r.id: r.label for r in labels_rows.all()}

    pos = neg = neu = 0
    por_area: dict[str, dict[str, int]] = {}
    for (cat_id, _), tono in zip(muestra, tonos, strict=False):
        if tono == "positivo":
            pos += 1
        elif tono == "negativo":
            neg += 1
        else:
            neu += 1
        bucket = por_area.setdefault(cat_id, {"positivo": 0, "neutral": 0, "negativo": 0})
        bucket[tono] += 1

    total = len(muestra)
    indice = _indice(pos, neg, total)

    areas: list[SentimientoArea] = []
    for cat_id, b in por_area.items():
        sub_total = b["positivo"] + b["neutral"] + b["negativo"]
        areas.append(
            SentimientoArea(
                area_id=cat_id,
                label=labels.get(cat_id, cat_id),
                positivo=b["positivo"],
                neutral=b["neutral"],
                negativo=b["negativo"],
                indice=_indice(b["positivo"], b["negativo"], sub_total),
            )
        )
    areas.sort(key=lambda a: a.indice)

    return SentimientoResponse(
        indice_global=indice,
        etiqueta=_etiqueta(indice),  # type: ignore[arg-type]
        positivo=pos,
        neutral=neu,
        negativo=neg,
        muestra=total,
        por_area=areas,
    )


# ─── Síntesis ejecutiva ──────────────────────────────────────────────────────


def _bloque_contexto(
    kpis: dict,
    desempeno: list[DesempenoArea],
    compromisos,
    sentimiento: SentimientoResponse,
) -> str:
    payload = {
        "kpis_globales": kpis,
        "desempeno_por_direccion": [d.model_dump() for d in desempeno],
        "compromisos": {
            "total": compromisos.total,
            "cumplidos": compromisos.cumplidos,
            "en_progreso": compromisos.en_progreso,
            "en_riesgo": compromisos.en_riesgo,
            "retrasados": compromisos.retrasados,
            "avance_promedio": compromisos.avance_promedio,
            "pct_cumplimiento": compromisos.pct_cumplimiento,
            "en_riesgo_detalle": [
                {"titulo": i.titulo, "avance_pct": i.avance_pct, "area": i.area_label}
                for i in compromisos.items
                if i.en_riesgo
            ][:8],
        },
        "sentimiento": {
            "indice_global": sentimiento.indice_global,
            "etiqueta": sentimiento.etiqueta,
            "muestra": sentimiento.muestra,
            "areas_mas_negativas": [
                {"area": a.label, "indice": a.indice}
                for a in sentimiento.por_area[:3]
            ],
        },
    }
    return (
        "# CONTEXTO (datos reales de la alcaldía — responde solo con esto)\n"
        + json.dumps(payload, ensure_ascii=False, default=str)
    )


async def _recopilar_contexto(tenant_id: str, db: AsyncSession, llm: LLMClient):
    kpis = await kpis_globales(tenant_id, db)
    desempeno = await desempeno_por_direccion(tenant_id, db)
    compromisos = await compromiso_service.resumen_compromisos(tenant_id, db)
    sentimiento = await analizar_sentimiento(tenant_id, db, llm=llm)
    return kpis, desempeno, compromisos, sentimiento


# ─── Casos de uso ────────────────────────────────────────────────────────────


async def responder_chat(
    db: AsyncSession,
    user: User,
    mensaje: str,
    historial: list[Message] | None = None,
    *,
    llm: LLMClient | None = None,
) -> EjecutivoChatResponse:
    """Responde una pregunta del Alcalde con visión cross-direcciones.

    Recopila el contexto completo (KPIs globales, desempeño por dirección,
    compromisos, sentimiento), lo inyecta como bloque de sistema y deja que el
    LLM (DeepSeek) sintetice en lenguaje natural.
    """
    historial = historial or []
    llm = llm or get_llm_client()
    tenant_id = user.tenant_id

    kpis, desempeno, compromisos, sentimiento = await _recopilar_contexto(tenant_id, db, llm)

    mensajes: list[Message] = [
        {"role": "system", "content": SYSTEM_PROMPT_EJECUTIVO},
        {"role": "system", "content": _bloque_contexto(kpis, desempeno, compromisos, sentimiento)},
    ]
    mensajes.extend(historial)
    mensajes.append({"role": "user", "content": mensaje})

    texto = await llm.chat(mensajes, max_tokens=settings.LLM_MAX_TOKENS)

    sin_info = kpis.get("total", 0) == 0 and compromisos.total == 0
    return EjecutivoChatResponse(
        respuesta=texto,
        datos={
            "kpis_globales": kpis,
            "desempeno_por_direccion": [d.model_dump() for d in desempeno],
            "compromisos": compromisos.model_dump(),
            "sentimiento": sentimiento.model_dump(),
        },
        sin_informacion=sin_info,
    )


async def resumen_ejecutivo(
    db: AsyncSession,
    user: User,
    *,
    llm: LLMClient | None = None,
) -> ResumenEjecutivo:
    """Síntesis ejecutiva cross-direcciones: una lectura priorizada del estado."""
    llm = llm or get_llm_client()
    tenant_id = user.tenant_id

    kpis, desempeno, compromisos, sentimiento = await _recopilar_contexto(tenant_id, db, llm)

    instruccion = (
        "Genera una SÍNTESIS EJECUTIVA breve (máximo 6 líneas) para el Alcalde a "
        "partir de los datos. Empieza con la conclusión general del estado de la "
        "alcaldía; luego 2 o 3 puntos prioritarios (cifras concretas, direcciones, "
        "compromisos en riesgo, ánimo ciudadano) y cierra con 1 recomendación "
        "accionable. Tono ejecutivo, en español, sin inventar cifras."
    )
    mensajes: list[Message] = [
        {"role": "system", "content": SYSTEM_PROMPT_EJECUTIVO},
        {"role": "system", "content": _bloque_contexto(kpis, desempeno, compromisos, sentimiento)},
        {"role": "user", "content": instruccion},
    ]
    try:
        sintesis = await llm.chat(mensajes, max_tokens=settings.LLM_MAX_TOKENS)
    except LLMError:
        sintesis = (
            f"Resumen operativo: {kpis.get('activos', 0)} reportes activos, "
            f"{kpis.get('en_riesgo_sla', 0)} en riesgo de SLA; "
            f"{compromisos.pct_cumplimiento}% de compromisos cumplidos; "
            f"ánimo ciudadano {sentimiento.etiqueta}."
        )

    return ResumenEjecutivo(
        sintesis=sintesis,
        kpis_globales=kpis,
        desempeno_por_area=desempeno,
        compromisos=compromisos,
        sentimiento=sentimiento,
        generado_en=datetime.now(UTC),
    )
