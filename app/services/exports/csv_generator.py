"""CSV export generators — flat data tables."""

from __future__ import annotations

import csv
import io


def generate_reportes_csv(reportes: list[dict]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "folio", "categoria", "estado", "prioridad", "fuente",
        "colonia", "titulo", "descripcion", "ciudadano",
        "lng", "lat", "cuadrilla", "fecha_creacion", "fecha_cierre",
        "tiempo_atencion_horas", "costo_estimado", "gasto_real",
    ])
    for r in reportes:
        writer.writerow([
            r.get("folio", ""),
            r.get("categoria_id", ""),
            r.get("estado", ""),
            r.get("prioridad", ""),
            r.get("fuente", ""),
            r.get("colonia_nombre", ""),
            r.get("titulo", ""),
            r.get("descripcion", ""),
            r.get("ciudadano_nombre", ""),
            r.get("lng", ""),
            r.get("lat", ""),
            r.get("cuadrilla_id", ""),
            str(r.get("fecha_creacion", ""))[:19],
            str(r.get("fecha_cierre", "") or "")[:19],
            r.get("tiempo_atencion_horas", ""),
            r.get("costo_estimado", ""),
            r.get("gasto_real", ""),
        ])
    return buf.getvalue().encode("utf-8-sig")


def generate_obras_csv(obras: list[dict]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "folio", "nombre", "categoria", "estado", "prioridad",
        "colonia", "contratista", "avance_pct",
        "presupuesto_autorizado", "presupuesto_ejercido",
        "fecha_inicio", "fecha_fin_estimada", "fecha_fin_real",
        "responsable",
    ])
    for o in obras:
        writer.writerow([
            o.get("folio", ""),
            o.get("nombre", ""),
            o.get("categoria_id", ""),
            o.get("estado", ""),
            o.get("prioridad", ""),
            o.get("colonia_nombre", ""),
            o.get("contratista_id", ""),
            o.get("avance_pct", ""),
            o.get("presupuesto_autorizado", ""),
            o.get("presupuesto_ejercido", ""),
            str(o.get("fecha_inicio", ""))[:10],
            str(o.get("fecha_fin_estimada", ""))[:10],
            str(o.get("fecha_fin_real", "") or "")[:10],
            o.get("responsable_nombre", ""),
        ])
    return buf.getvalue().encode("utf-8-sig")
