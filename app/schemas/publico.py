"""Schemas (request/response) del canal público de Tu Alcald.IA.

Estos esquemas alimentan endpoints SIN autenticación: reporte ciudadano con
identidad mínima, consulta de seguimiento por folio, aviso de privacidad,
verificación de identidad (verify-and-discard) y ejercicio de derechos ARCO.

Principio rector de privacidad: el canal público pide la MENOR cantidad de
datos personales posible y NUNCA persiste documentos de identidad ni
biométricos.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

# ─── Reporte sin cuenta (identidad mínima) ─────────────────────────────────


class ReportePublicoCreate(BaseModel):
    """Reporte ciudadano enviado sin necesidad de crear cuenta.

    El ``tenant_id`` y/o ``clave_geo`` permiten dirigir el reporte a la alcaldía
    correcta; si se omiten ambos se usa la alcaldía por defecto (demo). El nombre
    del ciudadano es OPCIONAL: se puede reportar de forma anónima.
    """

    categoria_id: str = Field(max_length=30)
    titulo: str = Field(min_length=3, max_length=200)
    descripcion: str | None = Field(None, max_length=4000)
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    colonia_id: str | None = Field(None, max_length=60)
    # Selección de alcaldía destino (cualquiera de las dos, o ninguna -> default).
    tenant_id: str | None = Field(None, max_length=50)
    clave_geo: str | None = Field(None, max_length=10)
    # Identidad mínima — totalmente opcional (reporte anónimo permitido).
    ciudadano_nombre: str | None = Field(None, max_length=100)
    evidencia_url: str | None = Field(None, max_length=500)


class ReportePublicoCreado(BaseModel):
    """Acuse de recibo del reporte: el folio es la llave de seguimiento."""

    folio: str
    estado: str
    mensaje: str = (
        "Reporte recibido. Guarda tu folio para dar seguimiento sin necesidad "
        "de cuenta."
    )


class TimelinePublicoItem(BaseModel):
    """Evento del seguimiento público (sin datos sensibles del personal)."""

    fecha: datetime
    tipo: str
    titulo: str
    descripcion: str | None = None


class ReportePublicoEstado(BaseModel):
    """Estado y seguimiento mínimo de un reporte, consultable por folio.

    No expone datos del ciudadano ni del personal interno (solo el rol/área
    pública del autor del evento), respetando la minimización de datos.
    """

    folio: str
    estado: str
    categoria_id: str
    titulo: str
    colonia_nombre: str | None = None
    fecha_creacion: datetime
    fecha_actualizacion: datetime
    timeline: list[TimelinePublicoItem] = []


# ─── Aviso de privacidad ───────────────────────────────────────────────────


class AvisoPrivacidad(BaseModel):
    titulo: str
    version: str
    actualizado: str
    en_lenguaje_llano: list[str]
    leyenda_no_electoral: str
    derechos_arco: str
    contacto: str


# ─── Verify-and-discard ────────────────────────────────────────────────────


class VerificacionRequest(BaseModel):
    """Solicitud de verificación de identidad.

    El ``payload`` lleva los datos que el proveedor externo necesita para
    verificar (p.ej. dígitos de un documento). NUNCA se almacenan: se usan en
    memoria y se descartan tras obtener el resultado.
    """

    documento_tipo: Literal["ine", "curp", "pasaporte"] = "ine"
    payload: dict = Field(default_factory=dict)


class VerificacionResultado(BaseModel):
    """Resultado de verificación. Solo el veredicto; sin datos del documento."""

    verificado: bool
    metodo: str
    timestamp: datetime


# ─── Derechos ARCO ─────────────────────────────────────────────────────────


class SolicitudArcoCreate(BaseModel):
    tipo: Literal["acceso", "rectificacion", "cancelacion", "oposicion"]
    email: EmailStr
    descripcion: str = Field(min_length=10, max_length=4000)
    # Alcaldía destino (opcional; default si se omite).
    tenant_id: str | None = Field(None, max_length=50)
    clave_geo: str | None = Field(None, max_length=10)


class SolicitudArcoCreada(BaseModel):
    folio: str
    tipo: str
    estado: str
    mensaje: str = (
        "Tu solicitud fue registrada. Te contactaremos al correo indicado dentro "
        "de los plazos de ley."
    )


# ─── Trámites y servicios (catálogo público) ───────────────────────────────


class DocumentoTramite(BaseModel):
    """Formato/documento descargable asociado a un trámite."""

    nombre: str
    url: str


class TramiteResumen(BaseModel):
    """Tarjeta de trámite para el listado público."""

    id: str
    nombre: str
    dependencia: str
    descripcion: str | None = None
    costo: str | None = None
    tiempo_estimado: str | None = None


class TramitesResponse(BaseModel):
    """Listado de trámites del catálogo público de una alcaldía."""

    tenant_id: str
    total: int
    tramites: list[TramiteResumen] = []


class TramiteDetalle(BaseModel):
    """Ficha completa de un trámite: requisitos, costos, tiempos, documentos."""

    id: str
    nombre: str
    dependencia: str
    descripcion: str | None = None
    requisitos: list[str] = []
    costo: str | None = None
    tiempo_estimado: str | None = None
    vigencia: str | None = None
    documentos: list[DocumentoTramite] = []
    donde_acudir: str | None = None
    horarios: str | None = None


# ─── Obras públicas (subconjunto sin datos sensibles) ──────────────────────


class ObraPublicaResumen(BaseModel):
    """Obra georreferenciada para el mapa/listado ciudadano.

    Subconjunto PÚBLICO: nunca incluye presupuesto, contratista ni equipo.
    """

    id: str
    nombre: str
    categoria_id: str
    categoria_label: str | None = None
    categoria_color: str | None = None
    estado: str
    avance_pct: int
    colonia_id: str | None = None
    colonia_nombre: str | None = None
    lat: float | None = None
    lng: float | None = None


class ObrasPublicasResponse(BaseModel):
    """Listado de obras públicas (subconjunto seguro) de una alcaldía."""

    tenant_id: str
    total: int
    obras: list[ObraPublicaResumen] = []


class ObraPublicaTimelineItem(BaseModel):
    """Hito público del avance de la obra (sin datos del personal interno)."""

    fecha: datetime
    tipo: str
    titulo: str
    descripcion: str | None = None


class ObraPublicaDetalle(BaseModel):
    """Ficha pública de una obra. NADA de presupuesto/contratista/equipo."""

    id: str
    folio: str
    nombre: str
    descripcion: str | None = None
    categoria_id: str
    categoria_label: str | None = None
    categoria_color: str | None = None
    estado: str
    avance_pct: int
    colonia_id: str | None = None
    colonia_nombre: str | None = None
    lat: float | None = None
    lng: float | None = None
    fecha_inicio: datetime | None = None
    fecha_fin_estimada: datetime | None = None
    timeline: list[ObraPublicaTimelineItem] = []


# ─── Indicadores públicos (KPIs no sensibles) ──────────────────────────────


class IndicadoresPublicos(BaseModel):
    """KPIs ciudadanos no sensibles de la alcaldía.

    Cifras agregadas de transparencia: no exponen montos, costos ni datos de
    personas. Pensadas para una tira de indicadores en el portal público.
    """

    tenant_id: str
    reportes_resueltos: int
    reportes_total: int
    pct_atencion: float
    tiempo_promedio_atencion_h: float
    total_obras_activas: int


# ─── Avisos y campañas activos ─────────────────────────────────────────────


class AvisoPublico(BaseModel):
    """Aviso/campaña institucional activo difundido a la ciudadanía."""

    id: str
    titulo: str
    cuerpo: str
    tipo: str  # aviso | campania
    segmento: str | None = None
    fecha: datetime


class AvisosResponse(BaseModel):
    """Listado de avisos/campañas activos de una alcaldía."""

    tenant_id: str
    total: int
    avisos: list[AvisoPublico] = []


# ─── Pagos (config estática NO transaccional) ──────────────────────────────


class ConceptoPago(BaseModel):
    """Concepto de pago con redirección a la caja oficial (NO transaccional).

    Tu Alcald.IA NO procesa pagos: solo informa y redirige al portal oficial
    de Tesorería/Finanzas de la CDMX. El campo ``url`` es el destino externo.
    """

    id: str
    concepto: str
    descripcion: str
    dependencia: str
    url: str


class PagosResponse(BaseModel):
    """Catálogo informativo de pagos con aviso de solo-redirección."""

    tenant_id: str
    transaccional: bool = False
    aviso: str = (
        "Tu Alcald.IA no procesa pagos. Estos enlaces te redirigen al portal "
        "oficial de la Tesorería/Secretaría de Finanzas de la CDMX, donde se "
        "realiza el pago de forma segura."
    )
    conceptos: list[ConceptoPago] = []
