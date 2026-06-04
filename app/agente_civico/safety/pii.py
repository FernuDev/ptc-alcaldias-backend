"""Protección de datos personales para el Agente Cívico.

Garantiza que ninguna respuesta exponga datos personales de terceros.
Para usuarios autenticados, los datos solo se recuperan por su propio
usuario_id — nunca se inyectan datos de otros ciudadanos.
"""

import re

# Patrones que intentan solicitar datos de terceros.
_SOLICITUD_TERCEROS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"(dame|dime|muéstrame|muestrame|cuál es|cual es|pásame|pasame)\s.*(teléfono|telefono|dirección|direccion|correo|email|nombre|datos|información|informacion|domicilio|curp|rfc|ine)\s.*(vecino|ciudadano|persona|reportó|reporto|denunci|otro|otra)",
        r"(quién|quien)\s+(reportó|reporto|denunció|denuncio|vive en|hizo)",
        r"datos\s+(personales|del vecino|de la persona|del ciudadano)",
        r"(nombre|teléfono|telefono|dirección|direccion)\s+(del|de la)\s+(vecino|ciudadano|persona|denunciante|reportante)",
    ]
]

# Respuesta estándar cuando se detecta solicitud de datos de terceros.
RESPUESTA_PII_DENEGADA = (
    "No puedo compartir datos personales de otros ciudadanos. "
    "Tu privacidad y la de todos los vecinos es una prioridad.\n\n"
    "Si necesitas contactar a alguien relacionado con un reporte o "
    "trámite, te sugiero acudir directamente a la dependencia responsable "
    "o llamar al **55 5449 6300**."
)


class PIICheckResult:
    """Resultado de la verificación de PII."""

    def __init__(self, bloqueado: bool, respuesta: str | None = None):
        self.bloqueado = bloqueado
        self.respuesta = respuesta


def verificar_solicitud_pii(mensaje: str) -> PIICheckResult:
    """Verifica si el mensaje del usuario solicita datos personales de terceros.

    Se ejecuta antes de la respuesta del LLM para bloquear intentos de
    obtener información personal de otros ciudadanos.

    Returns:
        PIICheckResult con bloqueado=True si se detectó solicitud de PII.
    """
    for patron in _SOLICITUD_TERCEROS:
        if patron.search(mensaje):
            return PIICheckResult(bloqueado=True, respuesta=RESPUESTA_PII_DENEGADA)
    return PIICheckResult(bloqueado=False)
