"""Verificación de identidad *verify-and-discard*.

Patrón de privacidad por diseño: para acreditar la identidad de una persona se
consulta a un proveedor externo, se obtiene un veredicto (verificado sí/no) y se
**descartan inmediatamente** los datos sensibles. NUNCA se persisten documentos
de identidad (INE), CURP, pasaportes ni datos biométricos.

En esta demo la verificación está SIMULADA y es determinista para que el flujo
sea reproducible. En producción, :func:`verify_identity` se conectaría a un
proveedor acreditado (p.ej. INE/RENAPO o un buró de identidad certificado),
enviando los datos por un canal cifrado y conservando únicamente el resultado.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# Tipos de documento aceptados por el flujo de verificación.
DOCUMENTOS_SOPORTADOS: frozenset[str] = frozenset({"ine", "curp", "pasaporte"})


def verify_identity(documento_tipo: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Verifica una identidad y descarta los datos sensibles.

    Args:
        documento_tipo: ``ine`` | ``curp`` | ``pasaporte``.
        payload: datos que el proveedor necesita para verificar (p.ej. dígitos
            de un documento). Se usan SOLO en memoria; esta función no los
            retorna ni los guarda en ningún lado.

    Returns:
        ``{"verificado": bool, "metodo": str, "timestamp": datetime}`` — únicamente
        el veredicto y metadatos no sensibles. Jamás incluye el contenido del
        documento ni biométricos.

    Nota de producción: aquí se haría la llamada HTTPS al proveedor acreditado.
    Tras recibir su respuesta, el ``payload`` queda fuera de alcance (no se
    persiste, no se loguea) — de ahí el nombre *verify-and-discard*.
    """
    tipo = (documento_tipo or "").strip().lower()
    metodo = (
        f"proveedor-externo-simulado:{tipo}"
        if tipo in DOCUMENTOS_SOPORTADOS
        else "no-soportado"
    )

    # Simulación determinista: se considera verificado si el proveedor recibe
    # los campos mínimos esperados y el tipo es soportado. No se inspecciona ni
    # se conserva el valor real de ningún dato sensible.
    verificado = (
        tipo in DOCUMENTOS_SOPORTADOS
        and isinstance(payload, dict)
        and bool(payload)
        and all(_es_no_vacio(v) for v in payload.values())
    )

    resultado = {
        "verificado": verificado,
        "metodo": metodo,
        "timestamp": datetime.now(UTC),
    }

    # verify-and-discard: liberamos toda referencia a los datos sensibles.
    payload = {}
    del payload

    return resultado


def _es_no_vacio(valor: Any) -> bool:
    if valor is None:
        return False
    if isinstance(valor, str):
        return bool(valor.strip())
    return True
