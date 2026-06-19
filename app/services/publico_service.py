"""Servicio del canal público (sin cuenta) de Tu Alcald.IA.

Implementa la creación y consulta de reportes ciudadanos sin requerir usuario
autenticado, además del registro de solicitudes ARCO. Para no acoplarse a
``reporte_service`` (que asume un ``User`` autenticado), aquí se manipulan los
modelos directamente, replicando el formato de folio ``{acronimo}-RC-{NNNN}``.

Privacidad: se piden los datos mínimos. El nombre del ciudadano es opcional;
la consulta de seguimiento no expone datos personales.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError
from app.models.categoria import Categoria, ObraCategoria
from app.models.colonia import Colonia
from app.models.obra import Obra
from app.models.reporte import Reporte, ReporteEvento
from app.models.solicitud_arco import SolicitudARCO
from app.models.tenant import Tenant
from app.models.tramite import Aviso, Tramite
from app.schemas.publico import (
    AvisoPublico,
    AvisosResponse,
    ConceptoPago,
    DocumentoTramite,
    IndicadoresPublicos,
    ObraPublicaDetalle,
    ObraPublicaResumen,
    ObraPublicaTimelineItem,
    ObrasPublicasResponse,
    PagosResponse,
    ReportePublicoEstado,
    TimelinePublicoItem,
    TramiteDetalle,
    TramiteResumen,
    TramitesResponse,
)

# Alcaldía usada cuando el reporte público no especifica destino (demo).
DEFAULT_TENANT_ID = "magdalena-contreras"


async def _resolver_tenant(
    db: AsyncSession,
    *,
    tenant_id: str | None = None,
    clave_geo: str | None = None,
) -> Tenant:
    """Determina la alcaldía destino a partir de tenant_id o clave_geo.

    Orden de preferencia: ``tenant_id`` explícito > ``clave_geo`` > tenant por
    defecto > primer/único tenant existente. Nunca confía en datos del body para
    el filtrado interno: solo selecciona a qué alcaldía se dirige el reporte.
    """
    if tenant_id:
        tenant = await db.get(Tenant, tenant_id)
        if tenant is None:
            raise NotFoundError("Alcaldía", tenant_id)
        return tenant

    if clave_geo:
        tenant = (
            await db.execute(select(Tenant).where(Tenant.clave_geo == clave_geo))
        ).scalar_one_or_none()
        if tenant is None:
            raise NotFoundError("Alcaldía (clave_geo)", clave_geo)
        return tenant

    tenant = await db.get(Tenant, DEFAULT_TENANT_ID)
    if tenant is not None:
        return tenant

    # Fallback final: la primera alcaldía registrada (demo de un solo tenant).
    tenant = (await db.execute(select(Tenant).limit(1))).scalar_one_or_none()
    if tenant is None:
        raise NotFoundError("Alcaldía", DEFAULT_TENANT_ID)
    return tenant


def _iniciales(nombre: str | None) -> str | None:
    """Calcula iniciales (máx. 2) del nombre del ciudadano para mostrar sin PII."""
    if not nombre:
        return None
    partes = [p for p in nombre.strip().split() if p]
    if not partes:
        return None
    return "".join(p[0] for p in partes[:2]).upper()[:5]


async def _colonia_mas_cercana(
    db: AsyncSession, tenant_id: str, *, lat: float, lng: float
) -> Colonia | None:
    """Devuelve la colonia de la alcaldía más cercana al punto reportado.

    Distancia euclidiana sobre lat/lng (suficiente a escala de alcaldía); se usa
    cuando el reporte público no especifica colonia. Garantiza asociar el reporte
    a una colonia válida (la columna es NOT NULL en la BD).
    """
    colonias = (
        await db.execute(select(Colonia).where(Colonia.tenant_id == tenant_id))
    ).scalars().all()
    if not colonias:
        return None
    return min(
        colonias,
        key=lambda c: (c.center_lat - lat) ** 2 + (c.center_lng - lng) ** 2,
    )


async def _generar_folio(db: AsyncSession, tenant: Tenant) -> str:
    """Genera el folio con el mismo formato que ``reporte_service``.

    Formato: ``{acronimo}-RC-{NNNN}`` donde NNNN es el consecutivo del tenant.
    """
    count = (
        await db.execute(
            select(func.count()).select_from(Reporte).where(Reporte.tenant_id == tenant.id)
        )
    ).scalar() or 0
    consecutivo = count + 1
    acronimo = (tenant.acronimo or tenant.id.split("-")[0][:2]).upper()
    return f"{acronimo}-RC-{consecutivo:04d}"


async def crear_reporte_publico(
    db: AsyncSession,
    *,
    tenant_id: str | None = None,
    categoria_id: str,
    titulo: str,
    descripcion: str | None = None,
    lat: float,
    lng: float,
    colonia_id: str | None = None,
    clave_geo: str | None = None,
    ciudadano_nombre: str | None = None,
    evidencia_url: str | None = None,
) -> str:
    """Crea un reporte ciudadano sin cuenta y devuelve su folio.

    Crea el ``Reporte`` (fuente='app', estado='nuevo'), su evento inicial y, si se
    aporta, una evidencia ciudadana. No requiere usuario autenticado.
    """
    tenant = await _resolver_tenant(db, tenant_id=tenant_id, clave_geo=clave_geo)

    # Validar categoría (existe en el catálogo global de categorías).
    categoria = await db.get(Categoria, categoria_id)
    if categoria is None:
        raise NotFoundError("Categoría", categoria_id)

    # Resolver colonia. Si el ciudadano la indica, se valida que pertenezca a la
    # alcaldía; si no (caso común: solo soltó un pin en el mapa), se asigna la
    # colonia más cercana al punto reportado. ``colonia_id`` es NOT NULL en la BD,
    # así que el reporte público SIEMPRE queda asociado a una colonia.
    colonia_nombre: str | None = None
    if colonia_id:
        colonia = (
            await db.execute(
                select(Colonia).where(
                    Colonia.id == colonia_id, Colonia.tenant_id == tenant.id
                )
            )
        ).scalar_one_or_none()
        if colonia is None:
            raise NotFoundError("Colonia", colonia_id)
        colonia_nombre = colonia.nombre
    else:
        colonia = await _colonia_mas_cercana(db, tenant.id, lat=lat, lng=lng)
        if colonia is None:
            raise NotFoundError("Colonia (alcaldía sin colonias)", tenant.id)
        colonia_id = colonia.id
        colonia_nombre = colonia.nombre

    folio = await _generar_folio(db, tenant)
    reporte_id = folio
    now = datetime.now(UTC)

    reporte = Reporte(
        id=reporte_id,
        tenant_id=tenant.id,
        folio=folio,
        categoria_id=categoria_id,
        estado="nuevo",
        prioridad="media",
        fuente="app",
        colonia_id=colonia_id,
        colonia_nombre=colonia_nombre,
        lng=lng,
        lat=lat,
        peso=1,
        titulo=titulo,
        descripcion=descripcion,
        ciudadano_nombre=ciudadano_nombre,
        ciudadano_iniciales=_iniciales(ciudadano_nombre),
        fecha_creacion=now,
        fecha_actualizacion=now,
    )
    db.add(reporte)
    await db.flush()

    evento = ReporteEvento(
        id=f"{reporte_id}-ev-001",
        reporte_id=reporte_id,
        fecha=now,
        tipo="creacion",
        titulo="Reporte recibido",
        descripcion="Reporte ciudadano recibido por el canal público.",
        autor_nombre=ciudadano_nombre or "Ciudadanía",
        autor_iniciales=_iniciales(ciudadano_nombre),
        autor_rol="Ciudadano",
    )
    db.add(evento)

    if evidencia_url:
        # Evidencia ciudadana adjunta al reporte. Import local para evitar
        # ampliar la superficie de imports del módulo.
        from app.models.reporte import ReporteEvidencia

        db.add(
            ReporteEvidencia(
                id=f"{reporte_id}-ev-{uuid.uuid4().hex[:8]}",
                reporte_id=reporte_id,
                url=evidencia_url,
                caption="Evidencia ciudadana",
                fecha=now,
                autor=ciudadano_nombre or "Ciudadanía",
                tipo="ciudadano",
            )
        )

    await db.flush()
    return folio


async def consultar_reporte_publico(db: AsyncSession, folio: str) -> ReportePublicoEstado:
    """Devuelve estado + seguimiento mínimo de un reporte por su folio.

    No expone datos personales del ciudadano ni nombres del personal interno:
    solo el avance público del trámite.
    """
    reporte = (
        await db.execute(select(Reporte).where(Reporte.folio == folio))
    ).scalar_one_or_none()
    if reporte is None:
        raise NotFoundError("Reporte", folio)

    timeline = [
        TimelinePublicoItem(
            fecha=ev.fecha,
            tipo=ev.tipo,
            titulo=ev.titulo,
            descripcion=ev.descripcion,
        )
        for ev in sorted(reporte.eventos, key=lambda e: e.fecha)
    ]

    return ReportePublicoEstado(
        folio=reporte.folio,
        estado=reporte.estado,
        categoria_id=reporte.categoria_id,
        titulo=reporte.titulo,
        colonia_nombre=reporte.colonia_nombre,
        fecha_creacion=reporte.fecha_creacion,
        fecha_actualizacion=reporte.fecha_actualizacion,
        timeline=timeline,
    )


async def crear_solicitud_arco(
    db: AsyncSession,
    *,
    tipo: str,
    email: str,
    descripcion: str,
    tenant_id: str | None = None,
    clave_geo: str | None = None,
) -> SolicitudARCO:
    """Registra una solicitud ARCO y la devuelve (con su folio/id)."""
    tenant = await _resolver_tenant(db, tenant_id=tenant_id, clave_geo=clave_geo)

    solicitud = SolicitudARCO(
        id=str(uuid.uuid4()),
        tenant_id=tenant.id,
        tipo=tipo,
        email_solicitante=email,
        descripcion=descripcion,
        estado="recibida",
        created_at=datetime.now(UTC),
    )
    db.add(solicitud)
    await db.flush()
    return solicitud


# ───────────────────────────────────────────────────────────────────────────
# Trámites y servicios (catálogo público)
# ───────────────────────────────────────────────────────────────────────────


def _docs_tramite(documentos) -> list[DocumentoTramite]:
    """Normaliza la lista JSONB de documentos a ``DocumentoTramite``."""
    out: list[DocumentoTramite] = []
    for d in documentos or []:
        if isinstance(d, dict) and d.get("nombre") and d.get("url"):
            out.append(DocumentoTramite(nombre=d["nombre"], url=d["url"]))
    return out


async def listar_tramites(
    db: AsyncSession,
    *,
    tenant_id: str | None = None,
    clave_geo: str | None = None,
) -> TramitesResponse:
    """Lista el catálogo público de trámites de la alcaldía."""
    tenant = await _resolver_tenant(db, tenant_id=tenant_id, clave_geo=clave_geo)
    rows = (
        await db.execute(
            select(Tramite)
            .where(Tramite.tenant_id == tenant.id)
            .order_by(Tramite.nombre)
        )
    ).scalars().all()
    tramites = [
        TramiteResumen(
            id=t.id,
            nombre=t.nombre,
            dependencia=t.dependencia,
            descripcion=t.descripcion,
            costo=t.costo,
            tiempo_estimado=t.tiempo_estimado,
        )
        for t in rows
    ]
    return TramitesResponse(
        tenant_id=tenant.id, total=len(tramites), tramites=tramites
    )


async def obtener_tramite(db: AsyncSession, tramite_id: str) -> TramiteDetalle:
    """Devuelve la ficha completa de un trámite por su id."""
    tramite = await db.get(Tramite, tramite_id)
    if tramite is None:
        raise NotFoundError("Trámite", tramite_id)
    requisitos = [str(r) for r in (tramite.requisitos or [])]
    return TramiteDetalle(
        id=tramite.id,
        nombre=tramite.nombre,
        dependencia=tramite.dependencia,
        descripcion=tramite.descripcion,
        requisitos=requisitos,
        costo=tramite.costo,
        tiempo_estimado=tramite.tiempo_estimado,
        vigencia=tramite.vigencia,
        documentos=_docs_tramite(tramite.documentos),
        donde_acudir=tramite.donde_acudir,
        horarios=tramite.horarios,
    )


# ───────────────────────────────────────────────────────────────────────────
# Obras públicas (subconjunto seguro, sin presupuesto/contratista)
# ───────────────────────────────────────────────────────────────────────────

# Estados de obra que se consideran "activas" para los indicadores públicos
# (excluye planeación, licitación y obra concluida).
_OBRA_ESTADOS_ACTIVOS = ("en_ejecucion", "suspendida", "en_cierre")


async def listar_obras_publicas(
    db: AsyncSession,
    *,
    tenant_id: str | None = None,
    clave_geo: str | None = None,
) -> ObrasPublicasResponse:
    """Lista las obras de la alcaldía con un subconjunto PÚBLICO de campos.

    No incluye presupuesto, contratista ni equipo: solo lo necesario para
    georreferenciar y mostrar el avance al ciudadano.
    """
    tenant = await _resolver_tenant(db, tenant_id=tenant_id, clave_geo=clave_geo)
    rows = (
        await db.execute(
            select(Obra, ObraCategoria.label, ObraCategoria.color)
            .join(ObraCategoria, Obra.categoria_id == ObraCategoria.id)
            .where(Obra.tenant_id == tenant.id)
            .order_by(Obra.fecha_inicio.desc())
        )
    ).all()
    obras = [
        ObraPublicaResumen(
            id=o.id,
            nombre=o.nombre,
            categoria_id=o.categoria_id,
            categoria_label=label,
            categoria_color=color,
            estado=o.estado,
            avance_pct=o.avance_pct or 0,
            colonia_id=o.colonia_id,
            colonia_nombre=o.colonia_nombre,
            lat=o.center_lat,
            lng=o.center_lng,
        )
        for o, label, color in rows
    ]
    return ObrasPublicasResponse(
        tenant_id=tenant.id, total=len(obras), obras=obras
    )


async def obtener_obra_publica(db: AsyncSession, obra_id: str) -> ObraPublicaDetalle:
    """Ficha pública de una obra: avance, ubicación y timeline; nada sensible."""
    obra = (
        await db.execute(
            select(Obra)
            .where(Obra.id == obra_id)
            .options(selectinload(Obra.timeline))
        )
    ).scalar_one_or_none()
    if obra is None:
        raise NotFoundError("Obra", obra_id)

    categoria = await db.get(ObraCategoria, obra.categoria_id)
    timeline = [
        ObraPublicaTimelineItem(
            fecha=ev.fecha,
            tipo=ev.tipo,
            titulo=ev.titulo,
            descripcion=ev.descripcion,
        )
        for ev in sorted(obra.timeline, key=lambda e: e.fecha)
    ]
    return ObraPublicaDetalle(
        id=obra.id,
        folio=obra.folio,
        nombre=obra.nombre,
        descripcion=obra.descripcion,
        categoria_id=obra.categoria_id,
        categoria_label=categoria.label if categoria else None,
        categoria_color=categoria.color if categoria else None,
        estado=obra.estado,
        avance_pct=obra.avance_pct or 0,
        colonia_id=obra.colonia_id,
        colonia_nombre=obra.colonia_nombre,
        lat=obra.center_lat,
        lng=obra.center_lng,
        fecha_inicio=obra.fecha_inicio,
        fecha_fin_estimada=obra.fecha_fin_estimada,
        timeline=timeline,
    )


# ───────────────────────────────────────────────────────────────────────────
# Indicadores públicos (KPIs no sensibles)
# ───────────────────────────────────────────────────────────────────────────


async def indicadores_publicos(
    db: AsyncSession,
    *,
    tenant_id: str | None = None,
    clave_geo: str | None = None,
) -> IndicadoresPublicos:
    """KPIs ciudadanos no sensibles de la alcaldía.

    Agrega sobre toda la alcaldía (sin filtro de área, a diferencia de
    ``stats_service`` que aísla por usuario): cifras de transparencia que NO
    exponen montos ni datos de personas.
    """
    tenant = await _resolver_tenant(db, tenant_id=tenant_id, clave_geo=clave_geo)
    rfilter = Reporte.tenant_id == tenant.id

    total = (
        await db.execute(select(func.count()).select_from(Reporte).where(rfilter))
    ).scalar() or 0

    resueltos = (
        await db.execute(
            select(func.count())
            .select_from(Reporte)
            .where(rfilter, Reporte.estado.in_(("resuelto", "cerrado")))
        )
    ).scalar() or 0

    avg_h = (
        await db.execute(
            select(func.avg(Reporte.tiempo_atencion_horas)).where(
                rfilter, Reporte.estado.in_(("resuelto", "cerrado"))
            )
        )
    ).scalar() or 0

    obras_activas = (
        await db.execute(
            select(func.count())
            .select_from(Obra)
            .where(Obra.tenant_id == tenant.id, Obra.estado.in_(_OBRA_ESTADOS_ACTIVOS))
        )
    ).scalar() or 0

    return IndicadoresPublicos(
        tenant_id=tenant.id,
        reportes_resueltos=int(resueltos),
        reportes_total=int(total),
        pct_atencion=round(resueltos / total * 100, 1) if total else 0.0,
        tiempo_promedio_atencion_h=round(float(avg_h), 1) if avg_h else 0.0,
        total_obras_activas=int(obras_activas),
    )


# ───────────────────────────────────────────────────────────────────────────
# Avisos y campañas activos
# ───────────────────────────────────────────────────────────────────────────


async def listar_avisos(
    db: AsyncSession,
    *,
    tenant_id: str | None = None,
    clave_geo: str | None = None,
) -> AvisosResponse:
    """Lista los avisos/campañas activos de la alcaldía (más recientes primero)."""
    tenant = await _resolver_tenant(db, tenant_id=tenant_id, clave_geo=clave_geo)
    rows = (
        await db.execute(
            select(Aviso)
            .where(Aviso.tenant_id == tenant.id, Aviso.activo.is_(True))
            .order_by(Aviso.fecha.desc())
        )
    ).scalars().all()
    avisos = [
        AvisoPublico(
            id=a.id,
            titulo=a.titulo,
            cuerpo=a.cuerpo,
            tipo=a.tipo,
            segmento=a.segmento,
            fecha=a.fecha,
        )
        for a in rows
    ]
    return AvisosResponse(tenant_id=tenant.id, total=len(avisos), avisos=avisos)


# ───────────────────────────────────────────────────────────────────────────
# Pagos (config estática NO transaccional; solo redirección oficial)
# ───────────────────────────────────────────────────────────────────────────

# Catálogo informativo de conceptos de pago. Tu Alcald.IA NO procesa pagos:
# cada URL redirige al portal oficial de la Tesorería/Finanzas de la CDMX.
_CONCEPTOS_PAGO: list[dict] = [
    {
        "id": "predial",
        "concepto": "Impuesto Predial",
        "descripcion": (
            "Pago del impuesto predial de tu inmueble. Consulta tu cuenta, "
            "descarga la boleta y paga en línea."
        ),
        "dependencia": "Secretaría de Administración y Finanzas · Tesorería CDMX",
        "url": "https://innovacion.finanzas.cdmx.gob.mx/predial",
    },
    {
        "id": "agua",
        "concepto": "Derechos por Suministro de Agua",
        "descripcion": (
            "Pago de los derechos por el suministro de agua potable y drenaje "
            "de tu toma."
        ),
        "dependencia": "Sistema de Aguas de la Ciudad de México (SACMEX)",
        "url": "https://www.sacmex.cdmx.gob.mx/servicios/linea-sacmex",
    },
    {
        "id": "tenencia",
        "concepto": "Tenencia o Refrendo Vehicular",
        "descripcion": (
            "Pago de la tenencia/refrendo y derechos de control vehicular del "
            "ejercicio fiscal vigente."
        ),
        "dependencia": "Secretaría de Administración y Finanzas · Tesorería CDMX",
        "url": "https://data.finanzas.cdmx.gob.mx/sigaps/",
    },
    {
        "id": "infracciones",
        "concepto": "Multas e Infracciones de Tránsito",
        "descripcion": (
            "Consulta y pago de infracciones de tránsito y fotocívicas "
            "asociadas a tu vehículo."
        ),
        "dependencia": "Secretaría de Movilidad · Tesorería CDMX",
        "url": "https://data.finanzas.cdmx.gob.mx/fotocivicas/",
    },
]


async def config_pagos(
    db: AsyncSession,
    *,
    tenant_id: str | None = None,
    clave_geo: str | None = None,
) -> PagosResponse:
    """Catálogo informativo de pagos (NO transaccional, solo redirección).

    El tenant se resuelve para etiquetar la respuesta, pero los conceptos son
    estáticos a nivel CDMX (predial, agua, tenencia, infracciones).
    """
    tenant = await _resolver_tenant(db, tenant_id=tenant_id, clave_geo=clave_geo)
    conceptos = [ConceptoPago(**c) for c in _CONCEPTOS_PAGO]
    return PagosResponse(tenant_id=tenant.id, conceptos=conceptos)
