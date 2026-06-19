"""Router público de Tu Alcald.IA — SIN autenticación.

Canal ciudadano de identidad mínima:

- ``POST /publico/reportes``        crear reporte sin cuenta (devuelve folio)
- ``GET  /publico/reportes/{folio}`` consultar estado/seguimiento por folio
- ``GET  /publico/aviso-privacidad`` aviso en lenguaje llano
- ``POST /publico/verificar``        verify-and-discard de identidad
- ``POST /publico/arco``             ejercer derechos ARCO (devuelve folio)

Ningún endpoint requiere token. El tenant se determina por el body
(``tenant_id``/``clave_geo``) o, en su defecto, por la alcaldía por defecto.
"""

from fastapi import APIRouter, Query

from app.core.dependencies import DB
from app.core.verification import verify_identity
from app.schemas.publico import (
    AvisoPrivacidad,
    AvisosResponse,
    IndicadoresPublicos,
    ObraPublicaDetalle,
    ObrasPublicasResponse,
    PagosResponse,
    ReportePublicoCreado,
    ReportePublicoCreate,
    ReportePublicoEstado,
    SolicitudArcoCreada,
    SolicitudArcoCreate,
    TramiteDetalle,
    TramitesResponse,
    VerificacionRequest,
    VerificacionResultado,
)
from app.services import publico_service

router = APIRouter(prefix="/publico", tags=["publico"])


@router.post("/reportes", response_model=ReportePublicoCreado, status_code=201)
async def crear_reporte_publico(data: ReportePublicoCreate, db: DB):
    """Crea un reporte ciudadano sin cuenta y devuelve el folio de seguimiento."""
    folio = await publico_service.crear_reporte_publico(
        db,
        tenant_id=data.tenant_id,
        clave_geo=data.clave_geo,
        categoria_id=data.categoria_id,
        titulo=data.titulo,
        descripcion=data.descripcion,
        lat=data.lat,
        lng=data.lng,
        colonia_id=data.colonia_id,
        ciudadano_nombre=data.ciudadano_nombre,
        evidencia_url=data.evidencia_url,
    )
    return ReportePublicoCreado(folio=folio, estado="nuevo")


@router.get("/reportes/{folio}", response_model=ReportePublicoEstado)
async def consultar_reporte_publico(folio: str, db: DB):
    """Consulta el estado y el seguimiento mínimo de un reporte por su folio."""
    return await publico_service.consultar_reporte_publico(db, folio)


@router.get("/aviso-privacidad", response_model=AvisoPrivacidad)
async def aviso_privacidad():
    """Devuelve el aviso de privacidad en lenguaje llano.

    Incluye la leyenda explícita de que los datos NO se usan con fines
    electorales, conforme al principio de finalidad.
    """
    return AvisoPrivacidad(
        titulo="Aviso de privacidad — Tu Alcald.IA",
        version="1.0",
        actualizado="2026-06-18",
        en_lenguaje_llano=[
            "Usamos tus datos solo para atender y dar seguimiento a tu reporte "
            "ciudadano.",
            "Puedes reportar de forma anónima: el nombre es opcional.",
            "Tu ubicación se usa únicamente para ubicar el problema que reportas.",
            "Guardamos tu reporte el tiempo necesario para resolverlo y para "
            "rendir cuentas, conforme a la ley.",
            "No vendemos ni compartimos tus datos con terceros para publicidad.",
            "Si verificamos tu identidad, lo hacemos contra un proveedor "
            "acreditado y NO almacenamos tu INE ni datos biométricos.",
            "Puedes ejercer tus derechos ARCO (Acceso, Rectificación, "
            "Cancelación y Oposición) cuando quieras.",
        ],
        leyenda_no_electoral=(
            "Tus datos NO se usan para fines electorales, partidistas ni de "
            "promoción personalizada de personas servidoras públicas."
        ),
        derechos_arco=(
            "Para ejercer tus derechos ARCO usa el canal POST /publico/arco o "
            "acude a la Unidad de Transparencia de tu alcaldía."
        ),
        contacto="Unidad de Transparencia de la Alcaldía.",
    )


@router.post("/verificar", response_model=VerificacionResultado)
async def verificar(data: VerificacionRequest):
    """Verifica identidad contra un proveedor externo (simulado) y descarta los datos.

    Solo retorna el veredicto: no persiste ni devuelve el documento ni
    biométricos (verify-and-discard).
    """
    resultado = verify_identity(data.documento_tipo, data.payload)
    return VerificacionResultado(**resultado)


@router.post("/arco", response_model=SolicitudArcoCreada, status_code=201)
async def crear_solicitud_arco(data: SolicitudArcoCreate, db: DB):
    """Registra una solicitud de derechos ARCO y devuelve su folio."""
    solicitud = await publico_service.crear_solicitud_arco(
        db,
        tipo=data.tipo,
        email=str(data.email),
        descripcion=data.descripcion,
        tenant_id=data.tenant_id,
        clave_geo=data.clave_geo,
    )
    return SolicitudArcoCreada(
        folio=solicitud.id,
        tipo=solicitud.tipo,
        estado=solicitud.estado,
    )


# ───────────────────────────────────────────────────────────────────────────
# Catálogo ciudadano público (sin auth): trámites, obras, indicadores,
# avisos y pagos. Todos aceptan ``tenant_id`` o ``clave_geo`` para elegir
# la alcaldía; en su defecto usan la alcaldía por defecto.
# ───────────────────────────────────────────────────────────────────────────


@router.get("/tramites", response_model=TramitesResponse)
async def listar_tramites(
    db: DB,
    tenant_id: str | None = Query(None),
    clave_geo: str | None = Query(None),
):
    """Catálogo público de trámites de la alcaldía."""
    return await publico_service.listar_tramites(
        db, tenant_id=tenant_id, clave_geo=clave_geo
    )


@router.get("/tramites/{tramite_id}", response_model=TramiteDetalle)
async def obtener_tramite(tramite_id: str, db: DB):
    """Ficha completa de un trámite (requisitos, costo, dónde acudir, etc.)."""
    return await publico_service.obtener_tramite(db, tramite_id)


@router.get("/obras", response_model=ObrasPublicasResponse)
async def listar_obras_publicas(
    db: DB,
    tenant_id: str | None = Query(None),
    clave_geo: str | None = Query(None),
):
    """Obras georreferenciadas con un subconjunto público de campos."""
    return await publico_service.listar_obras_publicas(
        db, tenant_id=tenant_id, clave_geo=clave_geo
    )


@router.get("/obras/{obra_id}", response_model=ObraPublicaDetalle)
async def obtener_obra_publica(obra_id: str, db: DB):
    """Ficha pública de una obra (avance, ubicación, timeline)."""
    return await publico_service.obtener_obra_publica(db, obra_id)


@router.get("/indicadores", response_model=IndicadoresPublicos)
async def indicadores_publicos(
    db: DB,
    tenant_id: str | None = Query(None),
    clave_geo: str | None = Query(None),
):
    """KPIs ciudadanos no sensibles (transparencia)."""
    return await publico_service.indicadores_publicos(
        db, tenant_id=tenant_id, clave_geo=clave_geo
    )


@router.get("/avisos", response_model=AvisosResponse)
async def listar_avisos(
    db: DB,
    tenant_id: str | None = Query(None),
    clave_geo: str | None = Query(None),
):
    """Avisos y campañas institucionales activos."""
    return await publico_service.listar_avisos(
        db, tenant_id=tenant_id, clave_geo=clave_geo
    )


@router.get("/pagos", response_model=PagosResponse)
async def config_pagos(
    db: DB,
    tenant_id: str | None = Query(None),
    clave_geo: str | None = Query(None),
):
    """Catálogo informativo de pagos (NO transaccional, solo redirección oficial)."""
    return await publico_service.config_pagos(
        db, tenant_id=tenant_id, clave_geo=clave_geo
    )
