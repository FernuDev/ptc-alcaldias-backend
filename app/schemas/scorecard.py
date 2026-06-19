"""Schemas de los scorecards de desempeño (REQ-06).

Tarjetas de rendimiento por cuadrilla y por persona (integrante de campo). Las
métricas se calculan vía agregación SQL en :mod:`app.services.scorecard_service`
y se sirven respetando la visibilidad jerárquica del rol del usuario:

* admin → todo el tenant.
* director_area / supervisor → su equipo (cuadrillas/personal de su área).
* jefe_cuadrilla / inspector → solo lo suyo (su cuadrilla / su persona).

Nadie ve a sus pares. El tenant SIEMPRE proviene del JWT.
"""

from pydantic import BaseModel


class ScorecardMetricas(BaseModel):
    """Bloque común de métricas de desempeño (cuadrilla o persona)."""

    # Volumen de trabajo cerrado en el periodo.
    reportes_resueltos: int = 0
    tareas_resueltas: int = 0
    resueltos_total: int = 0

    # Tiempo medio de atención (horas) de los reportes cerrados.
    tiempo_medio_horas: float = 0.0

    # Cumplimiento de SLA (% de reportes cerrados dentro del límite por prioridad).
    sla_cumplimiento_pct: float = 0.0
    sla_dentro: int = 0
    sla_total: int = 0

    # Carga vs capacidad operativa.
    tareas_activas: int = 0
    capacidad: int = 0  # nº de integrantes activos (personas) que dan capacidad
    carga_pct: float = 0.0  # tareas_activas / capacidad * 100

    # Reaperturas / reincidencias: reportes que volvieron a abrirse tras 'resuelto'.
    reaperturas: int = 0
    reincidencia_pct: float = 0.0


class CuadrillaScorecard(BaseModel):
    """Scorecard de una cuadrilla completa."""

    cuadrilla_id: str
    nombre: str
    integrantes: int = 0  # capacidad: nº de integrantes activos
    metricas: ScorecardMetricas


class PersonaScorecard(BaseModel):
    """Scorecard de una persona (integrante de campo)."""

    integrante_id: str
    nombre: str
    rol_campo: str  # jefe | integrante
    cuadrilla_id: str
    cuadrilla_nombre: str | None = None
    user_id: str | None = None
    metricas: ScorecardMetricas


class ScorecardScope(BaseModel):
    """Describe el alcance de visibilidad aplicado a la respuesta."""

    rol: str
    nivel: str  # global | area | propio
    areas: list[str] = []
