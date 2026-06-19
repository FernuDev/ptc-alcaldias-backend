"""Servicio de cierres viales de Tu Alcald.IA (REQ-02).

Dos responsabilidades:

1. :func:`cierres_activos` — lista, para el banner ciudadano público, las calles
   afectadas (``ObraCalleAfectada``) que están **cerradas y vigentes**: estado de
   cierre activo y ``fecha_fin_estimada`` aún en el futuro. Une cada cierre con su
   obra para dar contexto (folio, nombre, categoría) y resuelve un punto en el
   mapa (coordenadas de la calle o, en su defecto, el centro de la obra).

2. :func:`publicar_cierre` — marca un cierre como publicado y **notifica por
   cercanía**: calcula qué colonias del tenant caen dentro de un radio (geocerca)
   alrededor del cierre y, para esas colonias afectadas, crea ``Notificacion`` de
   tipo ``cierre`` para los responsables del área vía ``notificacion_service``.

Geocerca (demo): la distancia se calcula con la fórmula de haversine sobre los
centroides de colonia. En producción, el mismo punto de extensión enrutaría a un
proveedor de **push real** (FCM/APNs/Web-Push) hacia los tokens de los
dispositivos de ciudadanos suscritos dentro de la geocerca; ver el gancho
documentado al final de :func:`publicar_cierre`.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError
from app.models.colonia import Colonia
from app.models.obra import Obra, ObraCalleAfectada
from app.models.tenant import Tenant
from app.schemas.cierres import (
    CierreActivo,
    CierreObra,
    CierresActivosResponse,
    ColoniaNotificada,
    PublicarCierreResponse,
)
from app.services import notificacion_service

# Alcaldía usada cuando el banner público no especifica destino (demo).
DEFAULT_TENANT_ID = "magdalena-contreras"

# Estados de ``ObraCalleAfectada`` que representan un cierre vigente. El seed usa
# estos valores (ver scripts/seed.py CIERRE_ESTADOS); cualquier calle en uno de
# ellos y con vigencia futura aparece en el banner ciudadano.
ESTADOS_CIERRE_ACTIVO = ("cerrada_total", "cerrada_parcial", "desvio")

# Mapeo estado de cierre -> tipo_afectacion canónico, como respaldo cuando la
# columna ``tipo_afectacion`` aún no fue backfileada en una fila concreta.
_ESTADO_A_TIPO = {
    "cerrada_total": "total",
    "cerrada_parcial": "parcial",
    "desvio": "desvio",
}

# Radio por defecto de la geocerca de notificación (km).
RADIO_DEFAULT_KM = 2.0

_RADIO_TIERRA_KM = 6371.0


async def _resolver_tenant(
    db: AsyncSession,
    *,
    tenant_id: str | None = None,
    clave_geo: str | None = None,
) -> Tenant:
    """Determina la alcaldía a partir de ``tenant_id`` o ``clave_geo``.

    Orden de preferencia: ``tenant_id`` > ``clave_geo`` > tenant por defecto >
    primer tenant existente. Espeja la resolución del canal público para que el
    banner ciudadano funcione con cualquiera de las dos claves o sin ninguna.
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

    tenant = (await db.execute(select(Tenant).limit(1))).scalar_one_or_none()
    if tenant is None:
        raise NotFoundError("Alcaldía", DEFAULT_TENANT_ID)
    return tenant


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Distancia en km entre dos puntos (lat/lng) por la fórmula de haversine."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * _RADIO_TIERRA_KM * math.asin(math.sqrt(a))


def _tipo_afectacion(calle: ObraCalleAfectada) -> str | None:
    """Tipo de afectación de la calle: la columna si existe, o el derivado del estado."""
    if calle.tipo_afectacion:
        return calle.tipo_afectacion
    return _ESTADO_A_TIPO.get(calle.estado or "")


def _punto_cierre(calle: ObraCalleAfectada, obra: Obra) -> tuple[float | None, float | None]:
    """Mejor (lat, lng) para ubicar el cierre: la calle si tiene, o el centro de la obra.

    ``ObraCalleAfectada.coordenadas`` es un JSONB libre; si trae ``lat``/``lng``
    (o ``center_lat``/``center_lng``) se usa, de lo contrario se cae al centro de
    la obra, que siempre está disponible para una obra activa con cierre.
    """
    coords = calle.coordenadas
    if isinstance(coords, dict):
        lat = coords.get("lat", coords.get("center_lat"))
        lng = coords.get("lng", coords.get("center_lng"))
        if isinstance(lat, (int, float)) and isinstance(lng, (int, float)):
            return float(lat), float(lng)
    return obra.center_lat, obra.center_lng


async def cierres_activos(
    db: AsyncSession,
    *,
    tenant_id: str | None = None,
    clave_geo: str | None = None,
) -> CierresActivosResponse:
    """Lista las calles cerradas vigentes del tenant para el banner ciudadano.

    Una calle entra en el banner si su ``estado`` es un cierre activo y su
    ``fecha_fin_estimada`` es nula o futura (sigue cerrada hoy). El resultado se
    ordena por fecha de fin más próxima para que la UI muestre primero lo que
    está por reabrirse.
    """
    tenant = await _resolver_tenant(db, tenant_id=tenant_id, clave_geo=clave_geo)
    now = datetime.now(UTC)

    stmt = (
        select(ObraCalleAfectada)
        .join(Obra, ObraCalleAfectada.obra_id == Obra.id)
        .where(Obra.tenant_id == tenant.id)
        .where(ObraCalleAfectada.estado.in_(ESTADOS_CIERRE_ACTIVO))
        .options(selectinload(ObraCalleAfectada.obra))
    )
    calles = (await db.execute(stmt)).scalars().all()

    vigentes = [
        c for c in calles if c.fecha_fin_estimada is None or c.fecha_fin_estimada >= now
    ]
    vigentes.sort(key=lambda c: c.fecha_fin_estimada or datetime.max.replace(tzinfo=UTC))

    cierres: list[CierreActivo] = []
    for calle in vigentes:
        obra = calle.obra
        lat, lng = _punto_cierre(calle, obra)
        cierres.append(
            CierreActivo(
                id=calle.id,
                nombre=calle.nombre,
                estado=calle.estado,
                tipo_afectacion=_tipo_afectacion(calle),
                lat=lat,
                lng=lng,
                coordenadas=calle.coordenadas,
                fecha_inicio=calle.fecha_inicio,
                fecha_fin_estimada=calle.fecha_fin_estimada,
                alternativas_viales=calle.alternativas_viales,
                colonia_id=obra.colonia_id,
                colonia_nombre=obra.colonia_nombre,
                obra=CierreObra(
                    id=obra.id,
                    folio=obra.folio,
                    nombre=obra.nombre,
                    categoria_id=obra.categoria_id,
                ),
            )
        )

    return CierresActivosResponse(
        tenant_id=tenant.id,
        total=len(cierres),
        cierres=cierres,
    )


async def publicar_cierre(
    db: AsyncSession,
    *,
    calle_id: str,
    tenant_id: str,
    radio_km: float = RADIO_DEFAULT_KM,
    mensaje: str | None = None,
    excluir_user_id: str | None = None,
) -> PublicarCierreResponse:
    """Publica un cierre y notifica por cercanía (geocerca) a los responsables.

    Pasos:

    1. Carga la calle (acotada al ``tenant_id`` del JWT vía su obra) — multi-tenant.
    2. Marca la calle como cierre publicado/activo (estado coherente con el tipo).
    3. Calcula la geocerca: colonias del tenant cuyo centroide está dentro de
       ``radio_km`` del punto del cierre (haversine).
    4. Por cada notificación de área crea ``Notificacion`` tipo ``cierre`` para
       los responsables del tenant (acotados por la categoría/área de la obra),
       vía :func:`notificacion_service.notificar_responsables`.

    Devuelve el acuse con las colonias en cercanía y el conteo de notificaciones.
    """
    calle = (
        await db.execute(
            select(ObraCalleAfectada)
            .join(Obra, ObraCalleAfectada.obra_id == Obra.id)
            .where(ObraCalleAfectada.id == calle_id)
            .where(Obra.tenant_id == tenant_id)
            .options(selectinload(ObraCalleAfectada.obra))
        )
    ).scalar_one_or_none()
    if calle is None:
        raise NotFoundError("Cierre", calle_id)

    obra = calle.obra

    # ── 2. Marcar como cierre publicado/activo ─────────────────────────────────
    # Si la calle no traía un estado de cierre, se promueve a uno coherente con
    # su tipo de afectación (publicar = declarar el cierre vigente).
    if calle.estado not in ESTADOS_CIERRE_ACTIVO:
        tipo = _tipo_afectacion(calle) or "parcial"
        calle.estado = {
            "total": "cerrada_total",
            "parcial": "cerrada_parcial",
            "desvio": "desvio",
        }.get(tipo, "cerrada_parcial")
    tipo_afectacion = _tipo_afectacion(calle)

    # ── 3. Geocerca: colonias del tenant dentro del radio ──────────────────────
    lat, lng = _punto_cierre(calle, obra)
    colonias_en_cercania: list[ColoniaNotificada] = []
    if lat is not None and lng is not None:
        colonias = (
            await db.execute(select(Colonia).where(Colonia.tenant_id == tenant_id))
        ).scalars().all()
        for col in colonias:
            dist = _haversine_km(lat, lng, col.center_lat, col.center_lng)
            if dist <= radio_km:
                colonias_en_cercania.append(
                    ColoniaNotificada(
                        id=col.id,
                        nombre=col.nombre,
                        distancia_km=round(dist, 3),
                    )
                )
        colonias_en_cercania.sort(key=lambda c: c.distancia_km)

    # ── 4. Notificar por área a los responsables (in-app, tipo 'cierre') ───────
    nombre_via = calle.nombre or "una vía"
    detalle_tipo = {
        "total": "cierre total",
        "parcial": "cierre parcial",
        "desvio": "desvío",
    }.get(tipo_afectacion or "", "afectación vial")
    zonas = ", ".join(c.nombre for c in colonias_en_cercania[:5])
    cuerpo = mensaje or (
        f"{detalle_tipo.capitalize()} en {nombre_via} por la obra {obra.nombre}."
        + (f" Colonias en cercanía: {zonas}." if zonas else "")
    )

    enviadas = await notificacion_service.notificar_responsables(
        db,
        tenant_id=tenant_id,
        tipo="cierre",
        titulo=f"Cierre vial: {nombre_via}",
        cuerpo=cuerpo,
        href=f"/obras/{obra.id}",
        entity_type="obra",
        entity_id=obra.id,
        categoria_id=obra.categoria_id,
        excluir_user_id=excluir_user_id,
    )

    await db.flush()

    # ── Punto de extensión: PUSH REAL por geocerca ─────────────────────────────
    # En producción, además de la notificación in-app a responsables, aquí se
    # enrutaría un push a los dispositivos de ciudadanos suscritos cuya ubicación
    # caiga dentro de `colonias_en_cercania` (o dentro del radio sobre su última
    # ubicación conocida). El adaptador (FCM/APNs/Web-Push) tomaría los tokens y
    # entregaría el aviso. Se mantiene defensivo: un fallo de push nunca debe
    # abortar la transacción del cierre. Ejemplo del gancho:
    #
    #   await push_geocerca.deliver(
    #       tenant_id=tenant_id,
    #       centro=(lat, lng),
    #       radio_km=radio_km,
    #       payload={"titulo": ..., "cuerpo": cuerpo, "href": f"/obras/{obra.id}"},
    #   )
    #
    # Para la demo, la entrega real es in-app (la UI hace polling sobre
    # /notificaciones) y el banner público /cierres refleja el cierre de inmediato.

    return PublicarCierreResponse(
        calle_id=calle.id,
        obra_id=obra.id,
        tipo_afectacion=tipo_afectacion,
        radio_km=radio_km,
        colonias_en_cercania=colonias_en_cercania,
        notificaciones_enviadas=enviadas,
    )
