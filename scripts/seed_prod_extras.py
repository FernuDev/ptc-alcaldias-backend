"""Siembra IDEMPOTENTE de las secciones V5 nuevas, sin tocar reportes/obras/users.

Pensado para una BD ya poblada con la base (tenants, users, categorías, colonias,
cuadrillas, reportes, obras) a la que solo le faltan las secciones añadidas en V5:
campo (integrantes/turnos/tareas/ubicaciones), compromisos, trámites, avisos,
tipo_afectacion, configuración del tenant, y Plan.IA (proyectos + coordinación).

Uso:
    DATABASE_URL=postgresql+asyncpg://... .venv/bin/python scripts/seed_prod_extras.py

Reutiliza las constantes y `seed_campo` de scripts/seed.py. Todas las inserciones
usan IDs deterministas + ON CONFLICT DO NOTHING (o guards), así que correrlo
varias veces es seguro.
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone

# Permitir importar `seed` (scripts/) y `app` (raíz del backend).
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(_HERE))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402

from seed import (  # noqa: E402
    AVISOS_BASE,
    CIERRE_TO_TIPO_AFECTACION,
    COMPROMISOS_BASE,
    DAY_MS,
    NOW_MS,
    TENANTS,
    TRAMITES_BASE,
    _ms_to_dt,
    seed_campo,
)

NOW = datetime.now(timezone.utc)


def _prefix(tenant_id: str) -> str:
    return "MC" if tenant_id == "magdalena-contreras" else "TL"


# ── Plan.IA: portafolio + plan de trabajo ───────────────────────────────────
PROYECTOS = [
    # nombre, tipo, estado, prioridad, avance, presupuesto, pdm_eje, area_id, liga_compromiso
    ("Programa de Bacheo Permanente 2026", "obra", "en_ejecucion", "alta", 62, 3_500_000,
     "Eje 1 · Ciudad Segura y Servicios", "bacheo", True),
    ("Rehabilitación de Luminarias LED", "obra", "en_ejecucion", "media", 45, 2_100_000,
     "Eje 2 · Servicios Urbanos", "alumbrado", False),
    ("Jornadas de Salud y Bienestar", "programa", "planeacion", "media", 10, 800_000,
     "Eje 3 · Bienestar Social", None, False),
    ("Festival Cultural de Barrios", "evento", "planeacion", "baja", 5, 450_000,
     "Eje 4 · Cultura y Comunidad", None, False),
    ("Modernización Digital de Ventanillas", "iniciativa", "en_ejecucion", "alta", 30, 1_200_000,
     "Eje 5 · Gobierno Digital", None, False),
]
TAREAS_PRY = [
    "Diagnóstico y levantamiento",
    "Proyecto ejecutivo y presupuesto",
    "Licitación / asignación",
    "Ejecución en campo",
    "Supervisión y cierre",
]
APROBACIONES = [
    ("Validación técnica", "Dirección de Obras"),
    ("Suficiencia presupuestal", "Finanzas"),
    ("Autorización del Alcalde", "Alcaldía"),
]


async def seed_compromisos(session) -> int:
    n = 0
    for t in TENANTS:
        prefix = _prefix(t["id"])
        for idx, c in enumerate(COMPROMISOS_BASE):
            cid = f"{prefix}-CMP-{str(idx + 1).zfill(2)}"
            await session.execute(text("""
                INSERT INTO compromisos (id, tenant_id, titulo, descripcion,
                    area_id, meta, avance_pct, estado, fecha_objetivo)
                VALUES (:id, :tenant_id, :titulo, :descripcion,
                    :area_id, :meta, :avance_pct, :estado, :fecha_objetivo)
                ON CONFLICT (id) DO NOTHING
            """), {
                "id": cid, "tenant_id": t["id"], "titulo": c["titulo"][:200],
                "descripcion": c["descripcion"], "area_id": c["area_id"],
                "meta": c["meta"][:300] if c["meta"] else None,
                "avance_pct": c["avance_pct"], "estado": c["estado"],
                "fecha_objetivo": _ms_to_dt(NOW_MS + c["dias_objetivo"] * DAY_MS),
            })
            n += 1
    await session.commit()
    return n


async def seed_tramites(session) -> int:
    n = 0
    for t in TENANTS:
        prefix = _prefix(t["id"])
        for idx, tr in enumerate(TRAMITES_BASE):
            tid = f"{prefix}-TRM-{str(idx + 1).zfill(2)}"
            await session.execute(text("""
                INSERT INTO tramites (id, tenant_id, nombre, dependencia, area_id,
                    descripcion, requisitos, costo, tiempo_estimado, vigencia,
                    documentos, donde_acudir, horarios)
                VALUES (:id, :tenant_id, :nombre, :dependencia, :area_id,
                    :descripcion, CAST(:requisitos AS jsonb), :costo, :tiempo_estimado,
                    :vigencia, CAST(:documentos AS jsonb), :donde_acudir, :horarios)
                ON CONFLICT (id) DO NOTHING
            """), {
                "id": tid, "tenant_id": t["id"], "nombre": tr["nombre"][:200],
                "dependencia": f"{tr['dependencia']} · {t['nombre_corto']}"[:160],
                "area_id": tr.get("area_id"), "descripcion": tr.get("descripcion"),
                "requisitos": json.dumps(tr.get("requisitos", [])),
                "costo": tr.get("costo"), "tiempo_estimado": tr.get("tiempo_estimado"),
                "vigencia": tr.get("vigencia"),
                "documentos": json.dumps(tr.get("documentos", [])),
                "donde_acudir": tr.get("donde_acudir") or None, "horarios": tr.get("horarios"),
            })
            n += 1
    await session.commit()
    return n


async def seed_avisos(session) -> int:
    n = 0
    for t in TENANTS:
        prefix = _prefix(t["id"])
        for idx, av in enumerate(AVISOS_BASE):
            aid = f"{prefix}-AVI-{str(idx + 1).zfill(2)}"
            await session.execute(text("""
                INSERT INTO avisos (id, tenant_id, titulo, cuerpo, tipo, area_id,
                    segmento, fecha, activo)
                VALUES (:id, :tenant_id, :titulo, :cuerpo, :tipo, :area_id,
                    :segmento, :fecha, :activo)
                ON CONFLICT (id) DO NOTHING
            """), {
                "id": aid, "tenant_id": t["id"], "titulo": av["titulo"][:200],
                "cuerpo": av["cuerpo"], "tipo": av["tipo"], "area_id": av.get("area_id"),
                "segmento": av.get("segmento") or None,
                "fecha": _ms_to_dt(NOW_MS + av["dias_offset"] * DAY_MS),
                "activo": av.get("activo", True),
            })
            n += 1
    await session.commit()
    return n


async def seed_tipo_afectacion(session) -> int:
    n = 0
    for from_estado, tipo in CIERRE_TO_TIPO_AFECTACION.items():
        res = await session.execute(text("""
            UPDATE obra_calles_afectadas SET tipo_afectacion = :tipo
            WHERE estado = :estado AND tipo_afectacion IS NULL
        """), {"tipo": tipo, "estado": from_estado})
        n += res.rowcount or 0
    res = await session.execute(text("""
        UPDATE obra_calles_afectadas SET tipo_afectacion = 'parcial'
        WHERE tipo_afectacion IS NULL
    """))
    n += res.rowcount or 0
    await session.commit()
    return n


async def seed_config(session) -> int:
    flujos = [
        {"nombre": "Atención estándar", "pasos": ["Recepción", "Clasificación",
            "Asignación a cuadrilla", "Ejecución", "Cierre con evidencia"]},
        {"nombre": "Obra pública", "pasos": ["Diagnóstico", "Proyecto", "Licitación",
            "Ejecución", "Entrega"]},
    ]
    checklists = {
        "bacheo": ["Delimitar área", "Retiro de material", "Bacheo", "Compactación",
                   "Foto antes/después"],
        "alumbrado": ["Verificar suministro", "Sustituir luminaria", "Prueba de encendido",
                      "Foto antes/después"],
    }
    res = await session.execute(text("""
        UPDATE tenants SET
            titular_nombre = COALESCE(titular_nombre, 'C. Titular de la Alcaldía'),
            titular_cargo  = COALESCE(titular_cargo, 'Alcalde'),
            contacto       = COALESCE(contacto, 'atencion@' || id || '.gob.mx'),
            sla_dias       = COALESCE(sla_dias, CAST(:sla AS jsonb)),
            flujos         = COALESCE(flujos, CAST(:flujos AS jsonb)),
            checklists     = COALESCE(checklists, CAST(:checklists AS jsonb))
        WHERE sla_dias IS NULL OR flujos IS NULL OR checklists IS NULL
    """), {
        "sla": json.dumps({"critica": 1, "alta": 3, "media": 7, "baja": 15}),
        "flujos": json.dumps(flujos), "checklists": json.dumps(checklists),
    })
    await session.commit()
    return res.rowcount or 0


async def seed_plania(session) -> tuple[int, int]:
    ya = (await session.execute(text("SELECT count(*) FROM proyectos"))).scalar() or 0
    if ya:
        print(f"         proyectos ya existen ({ya}), se omite Plan.IA.")
        return 0, 0
    tenants = (await session.execute(
        text("SELECT id FROM tenants ORDER BY id"))).scalars().all()
    n_pry = n_tareas = 0
    for tid in tenants:
        prefix = _prefix(tid)
        for i, (nombre, tipo, estado, prio, avance, pres, pdm, area, liga) in enumerate(PROYECTOS):
            pid = f"{prefix}-PRY-{str(i + 1).zfill(2)}"
            await session.execute(text("""
                INSERT INTO proyectos (id, tenant_id, nombre, tipo, descripcion, estado,
                    prioridad, avance_pct, responsable_nombre, area_id, compromiso_id,
                    pdm_eje, presupuesto_estimado, fecha_inicio, fecha_fin_estimada,
                    created_at, updated_at)
                VALUES (:id, :tenant_id, :nombre, :tipo, :descripcion, :estado, :prioridad,
                    :avance, :resp, :area, :comp, :pdm, :pres, :ini, :fin, :now, :now)
                ON CONFLICT (id) DO NOTHING
            """), {
                "id": pid, "tenant_id": tid, "nombre": nombre, "tipo": tipo,
                "descripcion": f"{nombre} de la alcaldía.", "estado": estado,
                "prioridad": prio, "avance": avance, "resp": "Dirección de Obras",
                "area": area, "comp": f"{prefix}-CMP-01" if liga else None, "pdm": pdm,
                "pres": pres, "ini": NOW - timedelta(days=60),
                "fin": NOW + timedelta(days=120), "now": NOW,
            })
            n_pry += 1
            for j, tnombre in enumerate(TAREAS_PRY):
                estt = "completada" if (j + 1) * 20 <= avance else (
                    "en_progreso" if j * 20 < avance else "pendiente")
                await session.execute(text("""
                    INSERT INTO proyecto_tareas (id, proyecto_id, tenant_id, nombre, estado,
                        avance_pct, fecha_inicio, fecha_fin, depende_de, responsable, orden)
                    VALUES (:id, :pid, :tid, :nombre, :estado, :avance, :ini, :fin,
                        NULL, :resp, :orden)
                    ON CONFLICT (id) DO NOTHING
                """), {
                    "id": f"{pid}-T{j + 1}", "pid": pid, "tid": tid, "nombre": tnombre,
                    "estado": estt, "avance": min(100, max(0, avance - j * 20)),
                    "ini": NOW - timedelta(days=60 - j * 20),
                    "fin": NOW - timedelta(days=40 - j * 20),
                    "resp": "Cuadrilla/Área", "orden": j + 1,
                })
                n_tareas += 1
            # Coordinación: stakeholders, riesgo, flujo de aprobación.
            await session.execute(text("""
                INSERT INTO proyecto_stakeholders (id, proyecto_id, tenant_id, nombre,
                    organizacion, rol, postura, contacto)
                VALUES (:id, :pid, :tid, 'Dirección de Obras', 'Alcaldía', 'responsable',
                    'a_favor', 'obras@alcaldia.gob.mx')
                ON CONFLICT (id) DO NOTHING
            """), {"id": f"{pid}-S1", "pid": pid, "tid": tid})
            await session.execute(text("""
                INSERT INTO proyecto_stakeholders (id, proyecto_id, tenant_id, nombre,
                    organizacion, rol, postura)
                VALUES (:id, :pid, :tid, 'Comité Vecinal', 'Comunidad', 'afectado', 'neutral')
                ON CONFLICT (id) DO NOTHING
            """), {"id": f"{pid}-S2", "pid": pid, "tid": tid})
            await session.execute(text("""
                INSERT INTO proyecto_riesgos (id, proyecto_id, tenant_id, descripcion,
                    probabilidad, impacto, mitigacion, estado)
                VALUES (:id, :pid, :tid, 'Retraso por temporada de lluvias', 'media', 'alto',
                    'Calendarizar trabajos críticos fuera de temporada', 'abierto')
                ON CONFLICT (id) DO NOTHING
            """), {"id": f"{pid}-R1", "pid": pid, "tid": tid})
            for k, (etapa, resp) in enumerate(APROBACIONES):
                estado_ap = "aprobado" if (avance > 0 and k == 0) else "pendiente"
                await session.execute(text("""
                    INSERT INTO proyecto_aprobaciones (id, proyecto_id, tenant_id, etapa,
                        responsable, estado, orden, fecha_resolucion)
                    VALUES (:id, :pid, :tid, :etapa, :resp, :estado, :orden, :fres)
                    ON CONFLICT (id) DO NOTHING
                """), {
                    "id": f"{pid}-A{k + 1}", "pid": pid, "tid": tid, "etapa": etapa,
                    "resp": resp, "estado": estado_ap, "orden": k + 1,
                    "fres": NOW if estado_ap == "aprobado" else None,
                })
    await session.commit()
    return n_pry, n_tareas


_CHECKLIST = [
    {"paso": "Revisar el sitio", "hecho": False},
    {"paso": "Ejecutar el trabajo", "hecho": False},
    {"paso": "Capturar evidencia antes/después", "hecho": False},
]
_TAREA_ESTADO = {"asignado": ["pendiente"], "en_proceso": ["en_ruta", "en_sitio"]}


async def seed_tareas_desde_reportes(session, por_tenant: int = 60) -> int:
    """Fallback de tareas de campo cuando `seed_campo` no encontró reportes ya
    turnados: turna una muestra de reportes 'asignado'/'en_proceso' a una
    cuadrilla y crea su tarea. Idempotente (no corre si ya hay tareas; ids
    de tarea deterministas TK-<reporte_id>).
    """
    if (await session.execute(text("SELECT count(*) FROM tareas"))).scalar():
        return 0
    tenants = (await session.execute(
        text("SELECT id FROM tenants ORDER BY id"))).scalars().all()
    n = 0
    for tid in tenants:
        cuads = (await session.execute(
            text("SELECT id FROM cuadrillas WHERE tenant_id=:t ORDER BY id"),
            {"t": tid})).scalars().all()
        if not cuads:
            continue
        jefe = {}
        for cid in cuads:
            jefe[cid] = (await session.execute(text(
                "SELECT id FROM integrantes WHERE cuadrilla_id=:c AND rol_campo='jefe' LIMIT 1"
            ), {"c": cid})).scalar()
        reps = (await session.execute(text("""
            SELECT id, estado, titulo, lat, lng, colonia_id, prioridad FROM reportes
            WHERE tenant_id=:t AND estado IN ('asignado','en_proceso') AND cuadrilla_id IS NULL
            ORDER BY fecha_creacion DESC LIMIT :lim
        """), {"t": tid, "lim": por_tenant})).fetchall()
        for i, (rid, estado, titulo, lat, lng, col, prio) in enumerate(reps):
            cid = cuads[i % len(cuads)]
            await session.execute(
                text("UPDATE reportes SET cuadrilla_id=:c WHERE id=:r"),
                {"c": cid, "r": rid})
            opts = _TAREA_ESTADO.get(estado, ["pendiente"])
            await session.execute(text("""
                INSERT INTO tareas (id, tenant_id, cuadrilla_id, integrante_id, origen_tipo,
                    reporte_id, obra_id, titulo, descripcion, prioridad, estado, orden_ruta,
                    lat, lng, colonia_id, instrucciones, checklist, created_at, updated_at)
                VALUES (:id,:t,:c,:ig,'reporte',:r,NULL,:tit,NULL,:p,:est,:ord,:lat,:lng,:col,NULL,
                    CAST(:chk AS jsonb),:now,:now)
                ON CONFLICT (id) DO NOTHING
            """), {
                "id": f"TK-{rid}", "t": tid, "c": cid, "ig": jefe.get(cid), "r": rid,
                "tit": (titulo or "Tarea de campo")[:200], "p": prio or "media",
                "est": opts[i % len(opts)], "ord": i + 1, "lat": lat, "lng": lng,
                "col": col, "chk": json.dumps(_CHECKLIST), "now": NOW,
            })
            n += 1
    await session.commit()
    return n


async def main() -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("Define DATABASE_URL (postgresql+asyncpg://...)")
    engine = create_async_engine(url)
    async with AsyncSession(engine) as session:
        print("[campo]        integrantes/turnos/tareas/ubicaciones...")
        await seed_campo(session, [])  # lee cuadrillas/reportes de la DB; commitea solo
        n_tk = await seed_tareas_desde_reportes(session)
        if n_tk:
            print(f"[campo]        +{n_tk} tareas creadas (reportes turnados a cuadrilla)")
        print("[compromisos] ", await seed_compromisos(session))
        print("[tramites]    ", await seed_tramites(session))
        print("[avisos]      ", await seed_avisos(session))
        print("[tipo_afect.] ", await seed_tipo_afectacion(session), "calles")
        print("[config]       tenants actualizados:", await seed_config(session))
        n_pry, n_tar = await seed_plania(session)
        print(f"[plania]       {n_pry} proyectos, {n_tar} tareas (+ coordinación)")
    await engine.dispose()
    print("\nSeed de extras V5 completo.")


if __name__ == "__main__":
    asyncio.run(main())
