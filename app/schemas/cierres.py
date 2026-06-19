"""Schemas (request/response) de cierres viales de Tu Alcald.IA.

Modelan dos superficies:

- El **banner ciudadano** (público, sin auth): lista de calles cerradas activas
  con su tipo de afectación, ubicación, vigencia, obra de origen y alternativas
  viales. Solo expone información de utilidad pública, sin datos del personal.
- La **publicación de un cierre** (protegida): dispara la notificación por
  cercanía (geocerca) a responsables/área de las colonias dentro del radio.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

# Tipo de afectación de la vía (espeja ObraCalleAfectada.tipo_afectacion).
TipoAfectacion = Literal["total", "parcial", "desvio"]


class CierreObra(BaseModel):
    """Datos mínimos de la obra que origina el cierre (contexto para el banner)."""

    id: str
    folio: str | None = None
    nombre: str | None = None
    categoria_id: str | None = None


class CierreActivo(BaseModel):
    """Una calle cerrada vigente, lista para el banner ciudadano.

    ``lat``/``lng`` son el mejor punto disponible para ubicar el cierre en el
    mapa: las propias coordenadas de la calle si existen, o el centro de la obra
    como aproximación. ``tipo_afectacion`` permite al frontend pintar el color y
    el ícono (cerrado total / parcial / desvío).
    """

    id: str
    nombre: str | None = None
    estado: str | None = None
    tipo_afectacion: TipoAfectacion | None = None
    lat: float | None = None
    lng: float | None = None
    coordenadas: Any | None = None
    fecha_inicio: datetime | None = None
    fecha_fin_estimada: datetime | None = None
    alternativas_viales: Any | None = None
    colonia_id: str | None = None
    colonia_nombre: str | None = None
    obra: CierreObra | None = None


class CierresActivosResponse(BaseModel):
    """Respuesta del banner: cierres activos del tenant + acuse de la fuente."""

    tenant_id: str
    total: int
    cierres: list[CierreActivo] = []


class PublicarCierreRequest(BaseModel):
    """Parámetros de la publicación de un cierre (geocerca de notificación).

    ``radio_km`` define el radio de la geocerca: las colonias cuyo centro caiga
    dentro de ese radio respecto al cierre se consideran afectadas y disparan la
    notificación. Es opcional (default operativo) para que la demo no exija
    configurarlo en cada llamada.
    """

    radio_km: float = Field(2.0, gt=0, le=50)
    mensaje: str | None = Field(None, max_length=300)


class ColoniaNotificada(BaseModel):
    """Colonia dentro de la geocerca que motivó el aviso (traza de la cercanía)."""

    id: str
    nombre: str
    distancia_km: float


class PublicarCierreResponse(BaseModel):
    """Acuse de la publicación: a quién se notificó y por qué cercanía."""

    calle_id: str
    obra_id: str
    tipo_afectacion: TipoAfectacion | None = None
    radio_km: float
    colonias_en_cercania: list[ColoniaNotificada] = []
    notificaciones_enviadas: int
    mensaje: str = "Cierre publicado y notificado por cercanía."
