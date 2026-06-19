"""PDF export generator with branded slides and visual dashboard.

Uses ReportLab for PDF layout and Matplotlib for chart images.
Each export produces a multi-page landscape PDF:
  1. Portada membretada (logo, titulo, fecha, alcaldia)
  2. KPIs slide (big numbers)
  3. Chart slides (distribuciones, top colonias, volumen)
  4. Data table slides (paginated)
"""

from __future__ import annotations

import io
from datetime import UTC, datetime
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch, mm
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

PAGE = landscape(letter)
W, H = PAGE
MARGIN = 0.6 * inch

# Brand colors
GUINDA = colors.HexColor("#9F2241")
VERDE = colors.HexColor("#2D7A4F")
DORADO = colors.HexColor("#BC955C")
GRIS = colors.HexColor("#6B7280")
DARK = colors.HexColor("#1E293B")
LIGHT_BG = colors.HexColor("#F8FAFC")

CHART_COLORS = [
    "#9F2241", "#BC955C", "#2D7A4F", "#3A8DC0", "#C03A3A",
    "#6B2D8E", "#3F7D44", "#4A4A6B", "#D97706", "#7A5C2E",
]


def _make_chart_image(fig: plt.Figure) -> Image:
    """Render a matplotlib figure to a ReportLab Image."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    buf.seek(0)
    img = Image(buf)
    return img


def _styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle(
        "SlideTitle", parent=ss["Heading1"], fontSize=22, textColor=DARK,
        spaceAfter=12, alignment=TA_LEFT, fontName="Helvetica-Bold",
    ))
    ss.add(ParagraphStyle(
        "SlideSubtitle", parent=ss["Normal"], fontSize=11, textColor=GRIS,
        spaceAfter=6,
    ))
    ss.add(ParagraphStyle(
        "CoverTitle", parent=ss["Heading1"], fontSize=28, textColor=colors.white,
        alignment=TA_CENTER, fontName="Helvetica-Bold", spaceAfter=8,
    ))
    ss.add(ParagraphStyle(
        "CoverSub", parent=ss["Normal"], fontSize=14, textColor=colors.white,
        alignment=TA_CENTER, spaceAfter=4,
    ))
    ss.add(ParagraphStyle(
        "KpiValue", parent=ss["Normal"], fontSize=32, textColor=GUINDA,
        alignment=TA_CENTER, fontName="Helvetica-Bold",
    ))
    ss.add(ParagraphStyle(
        "KpiLabel", parent=ss["Normal"], fontSize=10, textColor=GRIS,
        alignment=TA_CENTER,
    ))
    ss.add(ParagraphStyle(
        "TableCell", parent=ss["Normal"], fontSize=7, leading=9,
    ))
    ss.add(ParagraphStyle(
        "TableHeader", parent=ss["Normal"], fontSize=7, leading=9,
        textColor=colors.white, fontName="Helvetica-Bold",
    ))
    return ss


# ─── Cover page ───────────────────────────────────────────────────────────

def _draw_cover(canvas, doc, tenant_name: str, title: str, subtitle: str, color: str):
    """Draw a full-bleed branded cover page."""
    c = canvas
    brand = colors.HexColor(color)
    c.setFillColor(brand)
    c.rect(0, 0, W, H, fill=1, stroke=0)

    # Accent stripe
    c.setFillColor(colors.HexColor("#00000033"))
    c.rect(0, H * 0.38, W, 4, fill=1, stroke=0)

    # Title block
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 32)
    c.drawCentredString(W / 2, H * 0.58, title)

    c.setFont("Helvetica", 16)
    c.drawCentredString(W / 2, H * 0.50, subtitle)

    c.setFont("Helvetica", 14)
    c.drawCentredString(W / 2, H * 0.42, tenant_name)

    # Date
    now = datetime.now(UTC).strftime("%d/%m/%Y %H:%M UTC")
    c.setFont("Helvetica", 11)
    c.setFillColor(colors.HexColor("#FFFFFFBB"))
    c.drawCentredString(W / 2, H * 0.28, f"Generado: {now}")

    # Footer line
    c.setFillColor(colors.HexColor("#FFFFFF44"))
    c.setFont("Helvetica", 9)
    c.drawCentredString(W / 2, 30, "Plataforma Ciudadana · Gobierno de la Ciudad de México")


def _header_footer(canvas, doc, tenant_name: str, color: str):
    """Standard slide header/footer."""
    c = canvas
    brand = colors.HexColor(color)
    # Top stripe
    c.setFillColor(brand)
    c.rect(0, H - 3 * mm, W, 3 * mm, fill=1, stroke=0)
    # Footer
    c.setFillColor(GRIS)
    c.setFont("Helvetica", 7)
    c.drawString(MARGIN, 18, f"Plataforma Ciudadana · {tenant_name}")
    now = datetime.now(UTC).strftime("%d/%m/%Y")
    c.drawRightString(W - MARGIN, 18, now)


# ─── KPI slide ────────────────────────────────────────────────────────────

def _build_kpi_table(kpis: dict[str, Any], ss) -> Table:
    """Build a 2x3 or 1x4 grid of KPI cards."""
    cards = [
        (str(kpis.get("activos", 0)), "Reportes activos"),
        (str(kpis.get("resueltos", 0)), "Resueltos"),
        (f'{kpis.get("tiempo_promedio_dias", 0):.1f} d', "Tiempo promedio"),
        (str(kpis.get("en_riesgo_sla", 0)), "En riesgo SLA"),
        (str(kpis.get("total_rango", 0)), "Total periodo"),
        (f'{kpis.get("pct_resueltos", 0):.1f}%', "Tasa resolución"),
    ]
    rows = []
    row = []
    for val, label in cards:
        cell = [
            Paragraph(val, ss["KpiValue"]),
            Spacer(1, 4),
            Paragraph(label, ss["KpiLabel"]),
        ]
        row.append(cell)
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        while len(row) < 3:
            row.append("")
        rows.append(row)

    col_w = (W - 2 * MARGIN) / 3
    t = Table(rows, colWidths=[col_w] * 3, rowHeights=[80] * len(rows))
    t.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BG),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
    ]))
    return t


# ─── Charts ───────────────────────────────────────────────────────────────

def _pie_chart(data: list[dict], title: str, w_inch: float = 4.5, h_inch: float = 3.0) -> Image:
    fig, ax = plt.subplots(figsize=(w_inch, h_inch))
    labels = [d["label"][:18] for d in data[:8]]
    values = [d["count"] for d in data[:8]]
    chart_colors = [d.get("color", CHART_COLORS[i % len(CHART_COLORS)]) for i, d in enumerate(data[:8])]

    wedges, texts, autotexts = ax.pie(
        values, labels=None, autopct="%1.0f%%", startangle=90,
        colors=chart_colors, pctdistance=0.8,
        textprops={"fontsize": 7, "color": "white", "weight": "bold"},
    )
    ax.legend(labels, loc="center left", bbox_to_anchor=(1, 0.5), fontsize=7, frameon=False)
    ax.set_title(title, fontsize=10, fontweight="bold", color="#1E293B", pad=8)
    fig.tight_layout()
    img = _make_chart_image(fig)
    img.drawWidth = w_inch * inch
    img.drawHeight = h_inch * inch
    return img


def _bar_chart(data: list[dict], title: str, key_x: str, key_y: str,
               w_inch: float = 5.0, h_inch: float = 2.8, horizontal: bool = False) -> Image:
    fig, ax = plt.subplots(figsize=(w_inch, h_inch))
    labels = [str(d[key_x])[:20] for d in data[:12]]
    values = [d[key_y] for d in data[:12]]
    chart_colors = [d.get("color", CHART_COLORS[i % len(CHART_COLORS)]) for i, d in enumerate(data[:12])]

    if horizontal:
        ax.barh(labels[::-1], values[::-1], color=chart_colors[::-1], height=0.6)
        ax.set_xlabel(key_y.replace("_", " ").title(), fontsize=8)
    else:
        ax.bar(labels, values, color=chart_colors, width=0.6)
        ax.set_ylabel(key_y.replace("_", " ").title(), fontsize=8)
        plt.xticks(rotation=35, ha="right", fontsize=7)

    ax.set_title(title, fontsize=10, fontweight="bold", color="#1E293B", pad=8)
    ax.tick_params(labelsize=7)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    img = _make_chart_image(fig)
    img.drawWidth = w_inch * inch
    img.drawHeight = h_inch * inch
    return img


def _line_chart(data: list[dict], title: str,
                w_inch: float = 8.0, h_inch: float = 2.5) -> Image:
    fig, ax = plt.subplots(figsize=(w_inch, h_inch))
    fechas = [d.get("fecha", d.get("dia", ""))[:10] for d in data]
    recibidos = [d.get("recibidos", 0) for d in data]
    atendidos = [d.get("atendidos", 0) for d in data]

    ax.fill_between(range(len(fechas)), recibidos, alpha=0.3, color=CHART_COLORS[0])
    ax.plot(range(len(fechas)), recibidos, color=CHART_COLORS[0], linewidth=1.5, label="Recibidos")
    ax.fill_between(range(len(fechas)), atendidos, alpha=0.3, color=CHART_COLORS[2])
    ax.plot(range(len(fechas)), atendidos, color=CHART_COLORS[2], linewidth=1.5, label="Atendidos")

    step = max(1, len(fechas) // 10)
    ax.set_xticks(range(0, len(fechas), step))
    ax.set_xticklabels([fechas[i] for i in range(0, len(fechas), step)], rotation=35, fontsize=6)
    ax.set_title(title, fontsize=10, fontweight="bold", color="#1E293B", pad=8)
    ax.legend(fontsize=7, frameon=False)
    ax.tick_params(labelsize=7)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    img = _make_chart_image(fig)
    img.drawWidth = w_inch * inch
    img.drawHeight = h_inch * inch
    return img


# ─── Data tables ──────────────────────────────────────────────────────────

def _build_data_table(
    headers: list[str],
    rows: list[list[str]],
    col_widths: list[float],
    ss,
) -> list:
    """Build paginated data tables. Returns list of Table flowables."""
    ROWS_PER_PAGE = 18
    tables = []

    for page_start in range(0, len(rows), ROWS_PER_PAGE):
        page_rows = rows[page_start : page_start + ROWS_PER_PAGE]
        header_row = [Paragraph(h, ss["TableHeader"]) for h in headers]
        data = [header_row]
        for row in page_rows:
            data.append([Paragraph(str(c), ss["TableCell"]) for c in row])

        t = Table(data, colWidths=col_widths, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), GUINDA),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E2E8F0")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_BG]),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ]))
        tables.append(t)
        if page_start + ROWS_PER_PAGE < len(rows):
            tables.append(PageBreak())

    return tables


# ═══════════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════════

def generate_reportes_pdf(
    *,
    tenant_name: str,
    tenant_color: str,
    kpis: dict,
    dist_categoria: list[dict],
    dist_estado: list[dict],
    top_colonias: list[dict],
    volumen: list[dict],
    reportes: list[dict],
) -> bytes:
    buf = io.BytesIO()
    ss = _styles()

    doc = SimpleDocTemplate(
        buf, pagesize=PAGE,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN + 10, bottomMargin=MARGIN,
    )

    story: list = []

    # --- Cover (drawn directly on canvas via onFirstPage) ---
    story.append(Spacer(1, 1))  # blank first page
    story.append(PageBreak())

    # --- KPIs ---
    story.append(Paragraph("Indicadores clave", ss["SlideTitle"]))
    story.append(Paragraph("Resumen operativo del periodo", ss["SlideSubtitle"]))
    story.append(Spacer(1, 12))
    story.append(_build_kpi_table(kpis, ss))
    story.append(PageBreak())

    # --- Charts page 1: categoria + estado ---
    story.append(Paragraph("Distribución de reportes", ss["SlideTitle"]))
    story.append(Spacer(1, 8))
    chart_row = []
    if dist_categoria:
        chart_row.append(_pie_chart(dist_categoria, "Por categoría"))
    if dist_estado:
        chart_row.append(_pie_chart(dist_estado, "Por estado"))
    if chart_row:
        ct = Table([chart_row], colWidths=[(W - 2 * MARGIN) / len(chart_row)] * len(chart_row))
        ct.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        story.append(ct)
    story.append(PageBreak())

    # --- Charts page 2: top colonias + volumen ---
    story.append(Paragraph("Análisis geográfico y temporal", ss["SlideTitle"]))
    story.append(Spacer(1, 8))
    if top_colonias:
        story.append(_bar_chart(
            [{"label": c["colonia_nombre"], "count": c["count"], "color": CHART_COLORS[i % len(CHART_COLORS)]}
             for i, c in enumerate(top_colonias)],
            "Top colonias por incidencia", "label", "count", horizontal=True, w_inch=4.5, h_inch=2.5,
        ))
    if volumen:
        story.append(Spacer(1, 8))
        story.append(_line_chart(volumen, "Volumen diario: recibidos vs atendidos"))
    story.append(PageBreak())

    # --- Data table ---
    story.append(Paragraph(f"Detalle de reportes ({len(reportes)} registros)", ss["SlideTitle"]))
    story.append(Spacer(1, 6))

    headers = ["Folio", "Categoría", "Estado", "Prioridad", "Colonia", "Título", "Fecha"]
    avail = W - 2 * MARGIN
    col_w = [avail * 0.10, avail * 0.12, avail * 0.10, avail * 0.08, avail * 0.18, avail * 0.30, avail * 0.12]
    rows = []
    for r in reportes:
        rows.append([
            r.get("folio", ""),
            r.get("categoria_id", ""),
            r.get("estado", ""),
            r.get("prioridad", ""),
            r.get("colonia_nombre", ""),
            r.get("titulo", "")[:50],
            str(r.get("fecha_creacion", ""))[:10],
        ])
    story.extend(_build_data_table(headers, rows, col_w, ss))

    def first_page(canvas, doc):
        _draw_cover(canvas, doc, tenant_name, "Reporte de Incidencias", "Plataforma Ciudadana", tenant_color)

    def later_pages(canvas, doc):
        _header_footer(canvas, doc, tenant_name, tenant_color)

    doc.build(story, onFirstPage=first_page, onLaterPages=later_pages)
    return buf.getvalue()


def generate_obras_pdf(
    *,
    tenant_name: str,
    tenant_color: str,
    obras: list[dict],
    stats: dict,
) -> bytes:
    buf = io.BytesIO()
    ss = _styles()
    doc = SimpleDocTemplate(buf, pagesize=PAGE, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=MARGIN + 10, bottomMargin=MARGIN)
    story: list = []

    # Cover
    story.append(Spacer(1, 1))
    story.append(PageBreak())

    # KPIs
    total = len(obras)
    activas = sum(1 for o in obras if o.get("estado") not in ("concluida", "suspendida"))
    pres_total = sum(float(o.get("presupuesto_autorizado") or 0) for o in obras)
    avg_avance = sum(o.get("avance_pct", 0) for o in obras) / max(total, 1)

    story.append(Paragraph("Programa de obra pública", ss["SlideTitle"]))
    story.append(Spacer(1, 12))
    cards_data = [
        (str(activas), "Obras activas"),
        (str(total), "Total obras"),
        (f"${pres_total:,.0f}", "Presupuesto autorizado"),
        (f"{avg_avance:.0f}%", "Avance promedio"),
    ]
    card_rows = []
    row = []
    for val, label in cards_data:
        cell = [Paragraph(val, ss["KpiValue"]), Spacer(1, 4), Paragraph(label, ss["KpiLabel"])]
        row.append(cell)
        if len(row) == 2:
            card_rows.append(row)
            row = []
    if row:
        while len(row) < 2:
            row.append("")
        card_rows.append(row)
    col_w = (W - 2 * MARGIN) / 2
    t = Table(card_rows, colWidths=[col_w] * 2, rowHeights=[80] * len(card_rows))
    t.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BG),
    ]))
    story.append(t)
    story.append(PageBreak())

    # Distribution by state
    estado_counts: dict[str, int] = {}
    for o in obras:
        st = o.get("estado", "?")
        estado_counts[st] = estado_counts.get(st, 0) + 1
    if estado_counts:
        story.append(Paragraph("Distribución por estado", ss["SlideTitle"]))
        story.append(Spacer(1, 8))
        dist = [{"label": k, "count": v} for k, v in estado_counts.items()]
        story.append(_pie_chart(dist, "Estado de obras", w_inch=5, h_inch=3.2))
        story.append(PageBreak())

    # Data table
    story.append(Paragraph(f"Detalle de obras ({total} registros)", ss["SlideTitle"]))
    story.append(Spacer(1, 6))
    headers = ["Folio", "Nombre", "Categoría", "Estado", "Avance", "Presupuesto", "Inicio"]
    avail = W - 2 * MARGIN
    col_w_list = [avail * 0.10, avail * 0.28, avail * 0.12, avail * 0.12, avail * 0.08, avail * 0.15, avail * 0.12]
    rows = []
    for o in obras:
        rows.append([
            o.get("folio", ""), o.get("nombre", "")[:40], o.get("categoria_id", ""),
            o.get("estado", ""), f'{o.get("avance_pct", 0)}%',
            f'${float(o.get("presupuesto_autorizado") or 0):,.0f}',
            str(o.get("fecha_inicio", ""))[:10],
        ])
    story.extend(_build_data_table(headers, rows, col_w_list, ss))

    def first_page(canvas, doc):
        _draw_cover(canvas, doc, tenant_name, "Programa de Obra Pública", "Plataforma Ciudadana", tenant_color)

    def later_pages(canvas, doc):
        _header_footer(canvas, doc, tenant_name, tenant_color)

    doc.build(story, onFirstPage=first_page, onLaterPages=later_pages)
    return buf.getvalue()


def generate_stats_pdf(
    *,
    tenant_name: str,
    tenant_color: str,
    kpis: dict,
    dist_categoria: list[dict],
    dist_estado: list[dict],
    top_colonias: list[dict],
    volumen: list[dict],
    ranking_cuadrillas: list[dict],
    costo_operativo: list[dict],
) -> bytes:
    buf = io.BytesIO()
    ss = _styles()
    doc = SimpleDocTemplate(buf, pagesize=PAGE, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=MARGIN + 10, bottomMargin=MARGIN)
    story: list = []

    # Cover
    story.append(Spacer(1, 1))
    story.append(PageBreak())

    # KPIs
    story.append(Paragraph("Resumen ejecutivo", ss["SlideTitle"]))
    story.append(Paragraph("Indicadores clave de gestión ciudadana", ss["SlideSubtitle"]))
    story.append(Spacer(1, 12))
    story.append(_build_kpi_table(kpis, ss))
    story.append(PageBreak())

    # Distribuciones
    story.append(Paragraph("Distribución de incidencias", ss["SlideTitle"]))
    story.append(Spacer(1, 8))
    chart_row = []
    if dist_categoria:
        chart_row.append(_pie_chart(dist_categoria, "Por categoría"))
    if dist_estado:
        chart_row.append(_pie_chart(dist_estado, "Por estado"))
    if chart_row:
        ct = Table([chart_row], colWidths=[(W - 2 * MARGIN) / len(chart_row)] * len(chart_row))
        ct.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        story.append(ct)
    story.append(PageBreak())

    # Top colonias + volumen
    story.append(Paragraph("Análisis geográfico y temporal", ss["SlideTitle"]))
    story.append(Spacer(1, 8))
    if top_colonias:
        story.append(_bar_chart(
            [{"label": c["colonia_nombre"], "count": c["count"], "color": CHART_COLORS[i % len(CHART_COLORS)]}
             for i, c in enumerate(top_colonias)],
            "Top colonias por incidencia", "label", "count", horizontal=True, w_inch=4.5, h_inch=2.5,
        ))
    if volumen:
        story.append(Spacer(1, 8))
        story.append(_line_chart(volumen, "Volumen diario: recibidos vs atendidos"))
    story.append(PageBreak())

    # Ranking cuadrillas
    if ranking_cuadrillas:
        story.append(Paragraph("Desempeño de cuadrillas", ss["SlideTitle"]))
        story.append(Spacer(1, 8))
        story.append(_bar_chart(
            [{"label": c["nombre"][:20], "count": c["resueltos"], "color": CHART_COLORS[i % len(CHART_COLORS)]}
             for i, c in enumerate(ranking_cuadrillas)],
            "Casos resueltos por cuadrilla", "label", "count", w_inch=7, h_inch=2.8,
        ))
        story.append(PageBreak())

    # Costo operativo
    if costo_operativo:
        story.append(Paragraph("Costo operativo por categoría", ss["SlideTitle"]))
        story.append(Spacer(1, 8))
        headers = ["Categoría", "Estimado", "Ejercido", "Diferencia"]
        avail = W - 2 * MARGIN
        col_w = [avail * 0.35, avail * 0.22, avail * 0.22, avail * 0.21]
        rows = []
        for c in costo_operativo:
            est = float(c.get("estimado", 0))
            ej = float(c.get("ejercido", 0))
            rows.append([c["label"], f"${est:,.0f}", f"${ej:,.0f}", f"${est - ej:,.0f}"])
        story.extend(_build_data_table(headers, rows, col_w, ss))

    def first_page(canvas, doc):
        _draw_cover(canvas, doc, tenant_name, "Reporte Ejecutivo", "Estadísticas de Gestión Ciudadana", tenant_color)

    def later_pages(canvas, doc):
        _header_footer(canvas, doc, tenant_name, tenant_color)

    doc.build(story, onFirstPage=first_page, onLaterPages=later_pages)
    return buf.getvalue()
