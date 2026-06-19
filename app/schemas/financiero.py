"""Esquemas del tablero financiero ejecutivo (REQ-16).

Consolida el presupuesto de obra en tres líneas comparables:

  - ``autorizado``    techo presupuestal aprobado (``Obra.presupuesto_autorizado``).
  - ``ejercido``      gasto efectivamente devengado (``Obra.presupuesto_ejercido``).
  - ``comprometido``  saldo del techo aún no ejercido en obras vivas (heurística
                      documentada en ``financiero_service``).

Además cruza avance FÍSICO (``Obra.avance_pct``) contra avance FINANCIERO
(``ejercido / autorizado``) y expone las alertas de control presupuestal.
"""

from decimal import Decimal

from pydantic import BaseModel


class ResumenFinanciero(BaseModel):
    """Consolidado global del tenant (o del universo de obras del director)."""

    autorizado: Decimal
    ejercido: Decimal
    comprometido: Decimal
    disponible: Decimal
    pct_ejercido: float
    pct_comprometido: float
    avance_fisico_pond: float
    avance_financiero: float
    desfase_pp: float
    total_obras: int
    obras_activas: int
    obras_sobreejercidas: int
    obras_en_riesgo: int


class DireccionFinanciero(BaseModel):
    """Línea presupuestal agregada por dirección (categoría de obra)."""

    categoria_id: str
    label: str
    color: str
    autorizado: Decimal
    ejercido: Decimal
    comprometido: Decimal
    disponible: Decimal
    pct_ejercido: float
    avance_fisico_pond: float
    avance_financiero: float
    desfase_pp: float
    total_obras: int


class ProyectoFinanciero(BaseModel):
    """Línea presupuestal por proyecto (obra individual)."""

    obra_id: str
    folio: str
    nombre: str
    categoria_id: str
    estado: str
    autorizado: Decimal
    ejercido: Decimal
    comprometido: Decimal
    disponible: Decimal
    pct_ejercido: float
    avance_fisico: int
    avance_financiero: float
    desfase_pp: float
    nivel_riesgo: str  # ninguno | bajo | medio | alto


class AlertaFinanciera(BaseModel):
    """Alerta de control presupuestal calculada en vivo (sin persistencia)."""

    tipo: str  # sobreejercicio | riesgo_avance | comprometido_alto
    severidad: str  # alta | media | baja
    obra_id: str
    folio: str
    nombre: str
    titulo: str
    detalle: str
    autorizado: Decimal
    ejercido: Decimal
    avance_fisico: int
    avance_financiero: float
