"""Detección de crisis para el Agente Cívico.

Se ejecuta ANTES de la respuesta normal, sobre cada mensaje entrante.
Si detecta indicios de violencia de género, riesgo a la vida o emergencia
médica, se anteponen los recursos de emergencia y se marca la respuesta.
"""

import re

# Patrones de crisis organizados por categoría.
# Cada tupla: (categoría, lista de palabras/frases).
_CRISIS_PATTERNS: list[tuple[str, list[str]]] = [
    (
        "violencia_genero",
        [
            "me golpea", "me pega", "me maltrata", "violencia doméstica",
            "violencia domestica", "violencia de género", "violencia de genero",
            "mi pareja me", "me amenaza", "me obliga", "abuso sexual",
            "acoso sexual", "me viola", "me violó", "tocamientos",
            "violencia familiar", "feminicidio", "me lastima",
        ],
    ),
    (
        "riesgo_vida",
        [
            "me quiero morir", "quiero matarme", "suicid", "no quiero vivir",
            "me voy a matar", "ya no puedo más", "ya no puedo mas",
            "quiero acabar con todo", "me van a matar", "amenaza de muerte",
            "secuestro", "secuestrado", "me tienen", "privado de mi libertad",
            "balacera", "disparos", "arma de fuego", "arma blanca",
            "me apuñal", "me están siguiendo", "me estan siguiendo",
            "incendio", "fuego", "explosión", "explosion",
            "muerto", "cadáver", "cadaver", "ahogad",
        ],
    ),
    (
        "emergencia_medica",
        [
            "infarto", "no respira", "se desmayó", "se desmayo",
            "convulsiones", "mucha sangre", "hemorragia", "envenenamiento",
            "intoxicación", "intoxicacion", "quemadura grave", "fractura expuesta",
            "accidente grave", "atropell", "persona herida", "herido de bala",
        ],
    ),
]

# Compilar un solo regex por categoría para eficiencia.
_COMPILED_PATTERNS: list[tuple[str, re.Pattern]] = [
    (cat, re.compile("|".join(re.escape(p) for p in pats), re.IGNORECASE))
    for cat, pats in _CRISIS_PATTERNS
]

# Mensajes de respuesta por categoría de crisis.
_RESPUESTAS_CRISIS: dict[str, str] = {
    "violencia_genero": (
        "**Tu seguridad es lo primero.**\n\n"
        "Si estás en peligro inmediato, llama al **911**.\n\n"
        "Puedes comunicarte a la **Línea LUNAS** para orientación y apoyo "
        "especializado en violencia de género. También puedes acudir al "
        "**Canal de Igualdad** de la alcaldía.\n\n"
        "No estás sola/solo. Hay personas capacitadas para ayudarte.\n\n"
        "Si prefieres hablar con alguien directamente, puedo conectarte "
        "con un funcionario de la alcaldía."
    ),
    "riesgo_vida": (
        "**Esto es importante. Tu vida vale mucho.**\n\n"
        "Si tú o alguien está en peligro inmediato, llama al **911** ahora.\n\n"
        "Si estás pasando por un momento muy difícil, la **Línea de la Vida** "
        "está disponible las 24 horas: **800 911 2000**.\n\n"
        "No tienes que enfrentar esto solo/sola. Hay ayuda disponible.\n\n"
        "Si necesitas hablar con un funcionario de la alcaldía, puedo "
        "conectarte ahora mismo."
    ),
    "emergencia_medica": (
        "**Esto suena como una emergencia médica.**\n\n"
        "Llama al **911** de inmediato para solicitar una ambulancia.\n\n"
        "Mientras llega la ayuda:\n"
        "- No muevas a la persona herida a menos que esté en peligro.\n"
        "- Mantén la calma y quédate con la persona.\n\n"
        "Si necesitas más orientación, puedo conectarte con un "
        "funcionario de Protección Civil de la alcaldía."
    ),
}


class CrisisResult:
    """Resultado de la detección de crisis."""

    def __init__(self, es_crisis: bool, categoria: str | None = None, respuesta: str | None = None):
        self.es_crisis = es_crisis
        self.categoria = categoria
        self.respuesta = respuesta


def detectar_crisis(mensaje: str) -> CrisisResult:
    """Analiza el mensaje del usuario en busca de señales de crisis.

    Se ejecuta de forma síncrona y rápida (solo regex) antes de cualquier
    llamada al LLM o RAG.

    Returns:
        CrisisResult con es_crisis=True si se detectó una crisis.
    """
    for categoria, patron in _COMPILED_PATTERNS:
        if patron.search(mensaje):
            return CrisisResult(
                es_crisis=True,
                categoria=categoria,
                respuesta=_RESPUESTAS_CRISIS[categoria],
            )
    return CrisisResult(es_crisis=False)
