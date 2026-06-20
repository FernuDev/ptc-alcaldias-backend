#!/usr/bin/env python3
"""
Deterministic seed script for ptc-alcaldias-backend.

Generates identical data to the TypeScript frontend generators
(reportes.ts, obras.ts, colonias.ts, catalogos.ts) using the same
mulberry32 PRNG ported bit-for-bit from JavaScript.

Usage:
    python scripts/seed.py

Reads DATABASE_URL from .env or environment.  Safe to run repeatedly
(all INSERTs use ON CONFLICT DO NOTHING).
"""

from __future__ import annotations

import asyncio
import math
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure passlib + asyncpg + sqlalchemy are available
# ---------------------------------------------------------------------------
try:
    import bcrypt as _bcrypt
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
except ImportError as exc:
    print(f"Missing dependency: {exc}. Run: pip install bcrypt sqlalchemy[asyncio] asyncpg")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Load .env (lightweight, no extra dependency required)
# ---------------------------------------------------------------------------
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
if _ENV_FILE.exists():
    for line in _ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip())

DATABASE_URL: str = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://ptc:ptc_secret@localhost:5432/ptc_alcaldias",
)

# ---------------------------------------------------------------------------
# Credenciales demo
# ---------------------------------------------------------------------------
# Contraseñas demo. Por defecto cada usuario usa el patrón «<id>.2026», que es lo
# que documenta CREDENCIALES.md (cómodo para la demo local). Si se define la
# variable de entorno SEED_DEMO_PASSWORD se usa ESA contraseña compartida para
# todos (más robusta y no enumerable — recomendada para entornos públicos).
#
#   CREDENCIALES DEMO  ──────────────────────────────────────────────
#   email:    cualquier email de la tabla USERS (p.ej.
#             fernando.mercado@mcontreras.gob.mx  /  admin Magdalena Contreras → mc-admin.2026
#             gabriela.osorio@tlalpan.cdmx.gob.mx /  admin Tlalpan            → tl-admin.2026)
#   password: «<id>.2026»  (o el valor de SEED_DEMO_PASSWORD si está definido)
#   ──────────────────────────────────────────────────────────────────
DEMO_PASSWORD_OVERRIDE: str | None = os.environ.get("SEED_DEMO_PASSWORD")

# Costo de bcrypt unificado con app/core/security.py (BCRYPT_ROUNDS = 12).
BCRYPT_ROUNDS = 12

# ═══════════════════════════════════════════════════════════════════════════
# mulberry32 PRNG  (bit-for-bit identical to the TypeScript version)
# ═══════════════════════════════════════════════════════════════════════════

def _imul(a: int, b: int) -> int:
    """Port of Math.imul -- 32-bit integer multiply."""
    a = a & 0xFFFFFFFF
    b = b & 0xFFFFFFFF
    result = (a * b) & 0xFFFFFFFF
    if result >= 0x80000000:
        result -= 0x100000000
    return result & 0xFFFFFFFF


def mulberry32(seed: int):
    """Port of the TypeScript mulberry32 PRNG."""
    a = seed & 0xFFFFFFFF

    def _next() -> float:
        nonlocal a
        a = (a + 0x6D2B79F5) & 0xFFFFFFFF
        t = a
        t = _imul(t ^ (t >> 15), t | 1) & 0xFFFFFFFF
        t = (t ^ (t + (_imul(t ^ (t >> 7), t | 61) & 0xFFFFFFFF))) & 0xFFFFFFFF
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296

    return _next


# ═══════════════════════════════════════════════════════════════════════════
# Constants matching the TypeScript source
# ═══════════════════════════════════════════════════════════════════════════

NOW_ISO = "2026-05-20T12:00:00.000Z"
NOW_MS = int(datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc).timestamp() * 1000)
DAY_MS = 24 * 3_600_000

REPORTES_SEED = 20260520
REPORTES_TOTAL_MC = 720
REPORTES_TOTAL_TL = 1_280

OBRAS_SEED = 7745312
OBRAS_TOTAL_MC = 38
OBRAS_TOTAL_TL = 52

# ═══════════════════════════════════════════════════════════════════════════
# Catalogos (exact replica of catalogos.ts)
# ═══════════════════════════════════════════════════════════════════════════

CATEGORIAS = [
    {"id": "bacheo",      "label": "Bacheo",                  "color": "#9F2241", "icono": "Construction", "peso": 0.22},
    {"id": "alumbrado",   "label": "Alumbrado público",       "color": "#BC955C", "icono": "Lightbulb",   "peso": 0.16},
    {"id": "limpia",      "label": "Recolección y limpia",    "color": "#2D7A4F", "icono": "Trash2",      "peso": 0.14},
    {"id": "seguridad",   "label": "Seguridad ciudadana",     "color": "#C03A3A", "icono": "ShieldAlert", "peso": 0.12},
    {"id": "agua",        "label": "Fugas y abasto de agua",  "color": "#3A8DC0", "icono": "Droplets",    "peso": 0.10},
    {"id": "parques",     "label": "Áreas verdes y parques",  "color": "#6B2D8E", "icono": "Trees",       "peso": 0.06},
    {"id": "arboles",     "label": "Arbolado urbano",         "color": "#3F7D44", "icono": "TreePine",    "peso": 0.06},
    {"id": "drenaje",     "label": "Drenaje y alcantarillado","color": "#4A4A6B", "icono": "Waves",       "peso": 0.05},
    {"id": "semaforos",   "label": "Semáforos y señalización","color": "#D97706", "icono": "TrafficCone", "peso": 0.05},
    {"id": "comercio_vp", "label": "Comercio en vía pública", "color": "#7A5C2E", "icono": "Store",       "peso": 0.04},
]

OBRA_CATEGORIAS = [
    {"id": "pavimentacion",      "label": "Pavimentación",            "color": "#9F2241", "peso": 0.22},
    {"id": "drenaje",            "label": "Drenaje y alcantarillado", "color": "#4A4A6B", "peso": 0.14},
    {"id": "alumbrado",          "label": "Alumbrado público",        "color": "#BC955C", "peso": 0.12},
    {"id": "agua_potable",       "label": "Agua potable",             "color": "#3A8DC0", "peso": 0.10},
    {"id": "parques",            "label": "Parques y áreas verdes",   "color": "#2D7A4F", "peso": 0.10},
    {"id": "escuelas",           "label": "Escuelas",                 "color": "#6B2D8E", "peso": 0.08},
    {"id": "edificios_publicos", "label": "Edificios públicos",       "color": "#7A5C2E", "peso": 0.06},
    {"id": "vialidad",           "label": "Vialidades y puentes",     "color": "#C03A3A", "peso": 0.10},
    {"id": "imagen_urbana",      "label": "Imagen urbana",            "color": "#D97706", "peso": 0.08},
]

PRIORIDADES = [
    {"id": "baja",    "peso": 0.35, "pesoMin": 1, "pesoMax": 2},
    {"id": "media",   "peso": 0.40, "pesoMin": 2, "pesoMax": 3},
    {"id": "alta",    "peso": 0.20, "pesoMin": 3, "pesoMax": 4},
    {"id": "critica", "peso": 0.05, "pesoMin": 4, "pesoMax": 5},
]

FUENTES = [
    {"id": "app",        "peso": 0.55},
    {"id": "web",        "peso": 0.20},
    {"id": "llamada",    "peso": 0.18},
    {"id": "presencial", "peso": 0.07},
]

CUADRILLAS = [
    {"id": "C01", "nombre": "Cuadrilla 1 \u00b7 Bacheo",                  "especialidad": ["bacheo"],                             "integrantes": 6},
    {"id": "C02", "nombre": "Cuadrilla 2 \u00b7 Alumbrado",              "especialidad": ["alumbrado", "semaforos"],              "integrantes": 4},
    {"id": "C03", "nombre": "Cuadrilla 3 \u00b7 Limpia",                  "especialidad": ["limpia"],                             "integrantes": 8},
    {"id": "C04", "nombre": "Cuadrilla 4 \u00b7 Agua y drenaje",         "especialidad": ["agua", "drenaje"],                    "integrantes": 5},
    {"id": "C05", "nombre": "Cuadrilla 5 \u00b7 \u00c1reas verdes",      "especialidad": ["parques", "arboles"],                 "integrantes": 5},
    {"id": "C06", "nombre": "Cuadrilla 6 \u00b7 Inspecci\u00f3n de v\u00eda", "especialidad": ["comercio_vp"],                   "integrantes": 3},
    {"id": "C07", "nombre": "Cuadrilla 7 \u00b7 Emergencias",            "especialidad": ["seguridad", "agua", "drenaje"],       "integrantes": 7},
    {"id": "C08", "nombre": "Cuadrilla 8 \u00b7 Mantenimiento general",  "especialidad": ["bacheo", "alumbrado", "parques"],     "integrantes": 6},
]

CONTRATISTAS = [
    {"id": "CT01", "razon_social": "Construcciones Tlalpan S.A. de C.V.",    "rfc": "CTL920304A12", "calificacion": 4.6},
    {"id": "CT02", "razon_social": "Pavimentos del Valle S.C.",               "rfc": "PVA850712D87", "calificacion": 4.2},
    {"id": "CT03", "razon_social": "Servicios Hidr\u00e1ulicos Xochimilco",  "rfc": "SHX011024K22", "calificacion": 4.4},
    {"id": "CT04", "razon_social": "Iluminaci\u00f3n Urbana de M\u00e9xico", "rfc": "IUM930115R43", "calificacion": 4.8},
    {"id": "CT05", "razon_social": "Grupo Constructor Magdalena",             "rfc": "GCM030619P54", "calificacion": 4.3},
    {"id": "CT06", "razon_social": "Proyectos Verdes CDMX",                   "rfc": "PVC141005H65", "calificacion": 4.5},
]

# ═══════════════════════════════════════════════════════════════════════════
# Tenants
# ═══════════════════════════════════════════════════════════════════════════

TENANTS = [
    {
        "id": "magdalena-contreras",
        "nombre": "Alcald\u00eda La Magdalena Contreras",
        "nombre_corto": "Magdalena Contreras",
        "clave_geo": "09008",
        "acronimo": "MC",
        "bbox": [-99.323, 19.213, -99.207, 19.338],
        "center": [-99.265, 19.275],
        "polygon_path": "/geo/magdalena-contreras.geojson",
        "escudo_path": "/escudos/magdalena-contreras.svg",
        "primario": "#9F2241",
        "secundario": "#2D7A4F",
        "dorado": "#BC955C",
        "poblacion": 247622,
        "area_km2": Decimal("74.58"),
    },
    {
        "id": "tlalpan",
        "nombre": "Alcald\u00eda Tlalpan",
        "nombre_corto": "Tlalpan",
        "clave_geo": "09012",
        "acronimo": "TL",
        "bbox": [-99.316, 19.089, -99.101, 19.312],
        "center": [-99.209, 19.201],
        "polygon_path": "/geo/tlalpan.geojson",
        "escudo_path": "/escudos/tlalpan.svg",
        "primario": "#235B4E",
        "secundario": "#9F2241",
        "dorado": "#BC955C",
        "poblacion": 699928,
        "area_km2": Decimal("304.99"),
    },
]

# ═══════════════════════════════════════════════════════════════════════════
# Users
# ═══════════════════════════════════════════════════════════════════════════

USERS = [
    # MC
    {"id": "mc-admin",          "tenant_id": "magdalena-contreras", "email": "fernando.mercado@mcontreras.gob.mx",  "nombre": "Fernando Mercado Guaida",   "iniciales": "FM", "cargo": "Alcalde \u00b7 Magdalena Contreras",                "role": "admin",         "areas": [],                             "avatar_tone": "#9F2241"},
    {"id": "mc-dir-obras",      "tenant_id": "magdalena-contreras", "email": "adriana.belmont@mcontreras.gob.mx",   "nombre": "Ing. Adriana Belmont",      "iniciales": "AB", "cargo": "Direcci\u00f3n de Obras y Servicios Urbanos",      "role": "director_area", "areas": ["bacheo"],                     "avatar_tone": None},
    {"id": "mc-dir-alumbrado",  "tenant_id": "magdalena-contreras", "email": "roberto.huerta@mcontreras.gob.mx",    "nombre": "Ing. Roberto Huerta",       "iniciales": "RH", "cargo": "Subdirecci\u00f3n de Alumbrado P\u00fablico",      "role": "director_area", "areas": ["alumbrado", "semaforos"],     "avatar_tone": None},
    {"id": "mc-dir-agua",       "tenant_id": "magdalena-contreras", "email": "patricia.galvan@mcontreras.gob.mx",   "nombre": "Ing. Patricia Galv\u00e1n","iniciales": "PG", "cargo": "Direcci\u00f3n de Agua y Drenaje",                  "role": "director_area", "areas": ["agua", "drenaje"],            "avatar_tone": None},
    {"id": "mc-dir-limpia",     "tenant_id": "magdalena-contreras", "email": "jorge.vargas@mcontreras.gob.mx",      "nombre": "Arq. Jorge Vargas",         "iniciales": "JV", "cargo": "Direcci\u00f3n de Servicios Urbanos \u00b7 Limpia","role": "director_area", "areas": ["limpia", "comercio_vp"],      "avatar_tone": None},
    {"id": "mc-dir-parques",    "tenant_id": "magdalena-contreras", "email": "mariana.ortega@mcontreras.gob.mx",    "nombre": "Ing. Mariana Ortega",       "iniciales": "MO", "cargo": "Direcci\u00f3n de Medio Ambiente \u00b7 \u00c1reas Verdes", "role": "director_area", "areas": ["parques", "arboles"], "avatar_tone": None},
    {"id": "mc-dir-seguridad",  "tenant_id": "magdalena-contreras", "email": "lucia.fernandez@mcontreras.gob.mx",   "nombre": "Mtra. Luc\u00eda Fern\u00e1ndez", "iniciales": "LF", "cargo": "Direcci\u00f3n de Seguridad Ciudadana",     "role": "director_area", "areas": ["seguridad"],                  "avatar_tone": None},
    # TL
    {"id": "tl-admin",          "tenant_id": "tlalpan", "email": "gabriela.osorio@tlalpan.cdmx.gob.mx",  "nombre": "Gabriela Osorio Hern\u00e1ndez",        "iniciales": "GO", "cargo": "Alcaldesa \u00b7 Tlalpan",                             "role": "admin",         "areas": [],                             "avatar_tone": "#235B4E"},
    {"id": "tl-dir-obras",      "tenant_id": "tlalpan", "email": "esteban.morales@tlalpan.cdmx.gob.mx",  "nombre": "Ing. Esteban Morales",                   "iniciales": "EM", "cargo": "Direcci\u00f3n de Obras y Desarrollo Urbano",       "role": "director_area", "areas": ["bacheo"],                     "avatar_tone": None},
    {"id": "tl-dir-alumbrado",  "tenant_id": "tlalpan", "email": "sandra.juarez@tlalpan.cdmx.gob.mx",   "nombre": "Ing. Sandra Ju\u00e1rez",                "iniciales": "SJ", "cargo": "Direcci\u00f3n de Alumbrado P\u00fablico",          "role": "director_area", "areas": ["alumbrado", "semaforos"],     "avatar_tone": None},
    {"id": "tl-dir-agua",       "tenant_id": "tlalpan", "email": "rafael.silva@tlalpan.cdmx.gob.mx",    "nombre": "Ing. Rafael Silva",                      "iniciales": "RS", "cargo": "Direcci\u00f3n de Agua Drenaje y Saneamiento",      "role": "director_area", "areas": ["agua", "drenaje"],            "avatar_tone": None},
    {"id": "tl-dir-limpia",     "tenant_id": "tlalpan", "email": "beatriz.cardenas@tlalpan.cdmx.gob.mx","nombre": "Lic. Beatriz C\u00e1rdenas",             "iniciales": "BC", "cargo": "Direcci\u00f3n de Limpia y Recolecci\u00f3n",       "role": "director_area", "areas": ["limpia", "comercio_vp"],      "avatar_tone": None},
    {"id": "tl-dir-parques",    "tenant_id": "tlalpan", "email": "arturo.benitez@tlalpan.cdmx.gob.mx",  "nombre": "Bi\u00f3l. Arturo Ben\u00edtez",         "iniciales": "AB", "cargo": "Direcci\u00f3n de Medio Ambiente \u00b7 Conservaci\u00f3n", "role": "director_area", "areas": ["parques", "arboles"], "avatar_tone": None},
    {"id": "tl-dir-seguridad",  "tenant_id": "tlalpan", "email": "carmen.lopez@tlalpan.cdmx.gob.mx",    "nombre": "Mtra. Carmen L\u00f3pez",                "iniciales": "CL", "cargo": "Direcci\u00f3n de Seguridad Ciudadana",              "role": "director_area", "areas": ["seguridad"],                  "avatar_tone": None},
    # Nuevos perfiles operativos (RBAC de 6 roles) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
    # MC
    {"id": "mc-supervisor",     "tenant_id": "magdalena-contreras", "email": "patricia.mendoza@mcontreras.gob.mx", "nombre": "Lic. Patricia Mendoza",   "iniciales": "PM", "cargo": "Supervisi\u00f3n CESAC \u00b7 Atenci\u00f3n Ciudadana",     "role": "supervisor",     "areas": [],                        "avatar_tone": None},
    {"id": "mc-jefe-cuadrilla", "tenant_id": "magdalena-contreras", "email": "andres.rivera@mcontreras.gob.mx",    "nombre": "Ing. Andr\u00e9s Rivera",  "iniciales": "AR", "cargo": "Jefatura de Cuadrilla \u00b7 Bacheo",                 "role": "jefe_cuadrilla", "areas": ["bacheo"],                "avatar_tone": None},
    {"id": "mc-inspector",      "tenant_id": "magdalena-contreras", "email": "roberto.sanchez@mcontreras.gob.mx",  "nombre": "Ing. Roberto S\u00e1nchez","iniciales": "RS", "cargo": "Inspecci\u00f3n y Verificaci\u00f3n de Obra",            "role": "inspector",      "areas": [],                        "avatar_tone": None},
    # TL
    {"id": "tl-supervisor",     "tenant_id": "tlalpan", "email": "mariana.cardenas@tlalpan.cdmx.gob.mx", "nombre": "Lic. Mariana C\u00e1rdenas", "iniciales": "MC", "cargo": "Subdirecci\u00f3n de Atenci\u00f3n Ciudadana",            "role": "supervisor",     "areas": [],                        "avatar_tone": None},
    {"id": "tl-jefe-cuadrilla", "tenant_id": "tlalpan", "email": "hugo.ramirez@tlalpan.cdmx.gob.mx",     "nombre": "Hugo Ram\u00edrez",         "iniciales": "HR", "cargo": "Jefatura de Cuadrilla \u00b7 Alumbrado",              "role": "jefe_cuadrilla", "areas": ["alumbrado", "semaforos"],"avatar_tone": None},
    {"id": "tl-inspector",      "tenant_id": "tlalpan", "email": "lourdes.vega@tlalpan.cdmx.gob.mx",     "nombre": "Arq. Lourdes Vega",         "iniciales": "LV", "cargo": "Inspecci\u00f3n de Calidad",                          "role": "inspector",      "areas": [],                        "avatar_tone": None},
]

# ═══════════════════════════════════════════════════════════════════════════
# Colonias  (exact replica of colonias.ts)
# ═══════════════════════════════════════════════════════════════════════════

def _c(id_: str, nombre: str, tipo: str, lng: float, lat: float,
       area_ha: int, poblacion: int, viviendas: int, densidad: int,
       cp: str, servicios: str, factor: float, tenant_id: str) -> dict:
    """Build a colonia dict. servicios is 'agua/drenaje/luz/internet'."""
    s = [int(x) for x in servicios.split("/")]
    return {
        "id": id_, "tenant_id": tenant_id, "nombre": nombre, "tipo": tipo,
        "center_lng": lng, "center_lat": lat, "area_ha": area_ha,
        "poblacion": poblacion, "viviendas": viviendas, "densidad": densidad,
        "codigos_postales": cp, "servicio_agua": s[0], "servicio_drenaje": s[1],
        "servicio_luz": s[2], "servicio_internet": s[3],
        "factor_reportes": factor,
    }

COLONIAS_MC: list[dict] = [
    _c("san-jeronimo-lidice",      "San Jer\u00f3nimo L\u00eddice",    "colonia",  -99.2360, 19.3185, 285, 24800, 6700, 87,  "10200",       "99/99/100/88", 0.95, "magdalena-contreras"),
    _c("san-jeronimo-aculco",      "San Jer\u00f3nimo Aculco",         "pueblo",   -99.2455, 19.3198, 165, 12400, 3350, 75,  "10400",       "98/97/99/78",  1.05, "magdalena-contreras"),
    _c("la-otra-banda",            "La Otra Banda",                     "colonia",  -99.2304, 19.3252,  78,  7900, 2100, 101, "10200",       "99/99/100/90", 0.80, "magdalena-contreras"),
    _c("tlacopac",                 "Tlacopac",                          "colonia",  -99.2240, 19.3303,  62,  6200, 1700, 100, "10100",       "100/100/100/92",0.75,"magdalena-contreras"),
    _c("magdalena-atlitic",        "Pueblo Magdalena Atlitic",          "pueblo",   -99.2553, 19.2858, 132, 10100, 2780, 76,  "10010;10300", "96/94/99/72",  1.20, "magdalena-contreras"),
    _c("barros-sierra",            "Barros Sierra",                     "colonia",  -99.2602, 19.2901,  48,  4900, 1330, 102, "10300",       "97/96/99/75",  1.05, "magdalena-contreras"),
    _c("la-concepcion",            "La Concepci\u00f3n",               "barrio",   -99.2483, 19.2887,  56,  6700, 1820, 120, "10010",       "95/94/99/70",  1.15, "magdalena-contreras"),
    _c("las-cruces",               "Las Cruces",                        "colonia",  -99.2474, 19.2882,  70,  7600, 2050, 109, "10300",       "96/95/99/71",  1.10, "magdalena-contreras"),
    _c("la-cruz",                  "La Cruz",                           "barrio",   -99.2521, 19.2820,  41,  5400, 1450, 132, "10300",       "94/92/98/65",  1.18, "magdalena-contreras"),
    _c("san-bernabe-ocotepec",     "San Bernab\u00e9 Ocotepec",        "pueblo",   -99.2705, 19.2968, 380, 29600, 7950, 78,  "10300;10350", "93/90/99/64",  1.30, "magdalena-contreras"),
    _c("lomas-de-san-bernabe",     "Lomas de San Bernab\u00e9",        "colonia",  -99.2752, 19.2933, 145, 12100, 3280, 83,  "10350",       "91/89/98/60",  1.25, "magdalena-contreras"),
    _c("el-rosal",                 "El Rosal",                          "colonia",  -99.2719, 19.3018,  58,  5900, 1590, 102, "10330",       "92/90/98/62",  1.10, "magdalena-contreras"),
    _c("tierra-unida",             "Tierra Unida",                      "colonia",  -99.2812, 19.3061,  92,  9700, 2610, 105, "10380",       "90/87/97/58",  1.22, "magdalena-contreras"),
    _c("pueblo-nuevo-alto",        "Pueblo Nuevo Alto",                 "barrio",   -99.2826, 19.2881,  64,  7000, 1880, 109, "10650",       "89/86/97/55",  1.20, "magdalena-contreras"),
    _c("pueblo-nuevo-bajo",        "Pueblo Nuevo Bajo",                 "barrio",   -99.2823, 19.2826,  72,  8900, 2400, 124, "10650",       "90/87/98/57",  1.18, "magdalena-contreras"),
    _c("cerro-del-judio",          "Cerro del Jud\u00edo",             "colonia",  -99.2787, 19.3141,  88,  8200, 2210, 93,  "10380",       "87/83/96/52",  1.30, "magdalena-contreras"),
    _c("la-carbonera",             "La Carbonera",                      "colonia",  -99.2615, 19.2705,  64,  6900, 1860, 108, "10500",       "92/90/98/66",  1.10, "magdalena-contreras"),
    _c("el-tanque",                "El Tanque",                         "colonia",  -99.2682, 19.2725,  30,  7784, 2038, 262, "10320",       "95/93/100/70", 1.15, "magdalena-contreras"),
    _c("el-toro",                  "El Toro",                           "colonia",  -99.2654, 19.2602,  38,  4900, 1320, 129, "10610",       "91/89/98/63",  1.05, "magdalena-contreras"),
    _c("la-malinche",              "La Malinche",                       "colonia",  -99.2701, 19.2554,  27,  3100,  850, 115, "10630",       "89/86/97/55",  1.10, "magdalena-contreras"),
    _c("las-huertas",              "Las Huertas",                       "colonia",  -99.2628, 19.2645,  33,  3800, 1020, 115, "10610",       "92/90/98/64",  1.00, "magdalena-contreras"),
    _c("atacaxco",                 "Atacaxco",                          "barrio",   -99.2763, 19.2582,  52,  5700, 1530, 110, "10720",       "87/84/96/51",  1.20, "magdalena-contreras"),
    _c("heroes-de-padierna",       "H\u00e9roes de Padierna",          "colonia",  -99.2678, 19.2451, 150, 12300, 3310, 82,  "10700",       "89/86/97/58",  1.20, "magdalena-contreras"),
    _c("lomas-quebradas",          "Lomas Quebradas",                   "colonia",  -99.2895, 19.2752,  78,  6300, 1700, 81,  "10000",       "88/85/97/56",  1.15, "magdalena-contreras"),
    _c("san-nicolas-totolapan",    "San Nicol\u00e1s Totolapan",       "pueblo",   -99.2722, 19.2356, 240, 15400, 4150, 64,  "10900",       "86/82/96/50",  1.25, "magdalena-contreras"),
    _c("plazuela-del-pedregal",    "Plazuela del Pedregal",             "colonia",  -99.2787, 19.2253,  34,  3300,  890, 97,  "10900",       "84/80/95/47",  1.10, "magdalena-contreras"),
    _c("el-ermitano",              "El Ermita\u00f1o",                  "colonia",  -99.2954, 19.2702,  42,  4200, 1130, 100, "10840",       "86/83/96/52",  1.18, "magdalena-contreras"),
    _c("barrio-las-calles",        "Barrio Las Calles",                 "barrio",   -99.2602, 19.2812,  25,  3100,  830, 124, "10300",       "95/93/99/68",  1.00, "magdalena-contreras"),
    _c("pedregal-i",               "Pedregal I",                        "unidad_habitacional", -99.2651, 19.2882, 28, 3900, 1050, 139, "10580", "96/95/100/73", 0.95, "magdalena-contreras"),
    _c("pedregal-ii",              "Pedregal II",                       "unidad_habitacional", -99.2620, 19.2904, 24, 3100,  830, 129, "10580", "96/95/100/75", 0.90, "magdalena-contreras"),
]

COLONIAS_TL: list[dict] = [
    _c("tl-villa-olimpica",        "Villa Ol\u00edmpica",              "unidad_habitacional", -99.196, 19.305,  62,  7400, 2010, 119, "14020", "98/97/100/86", 0.85, "tlalpan"),
    _c("tl-cantil-pedregal",       "Cantil del Pedregal",              "colonia",  -99.19,  19.31,  110, 13200, 3550, 120, "14600", "97/96/100/82", 0.95, "tlalpan"),
    _c("tl-pedregal-san-nicolas",  "Pedregal de San Nicol\u00e1s",    "colonia",  -99.158, 19.305, 240, 28400, 7500, 118, "14100;14108", "93/90/99/66", 1.20, "tlalpan"),
    _c("tl-vista-valle",           "Vista del Valle",                   "colonia",  -99.175, 19.29,   88,  9600, 2580, 109, "14640", "95/93/99/72", 1.05, "tlalpan"),
    _c("tl-centro",                "Tlalpan Centro",                    "colonia",  -99.169, 19.293, 145, 16800, 4510, 116, "14000", "99/99/100/88", 1.15, "tlalpan"),
    _c("tl-san-lorenzo-huipulco",  "San Lorenzo Huipulco",             "pueblo",   -99.169, 19.31,  168, 17200, 4620, 102, "14370", "95/93/99/71", 1.20, "tlalpan"),
    _c("tl-toriello-guerrero",     "Toriello Guerra",                   "colonia",  -99.18,  19.288, 110, 11400, 3060, 104, "14050", "98/97/100/86", 0.95, "tlalpan"),
    _c("tl-cuauhtemoc-tlalpan",    "Cuauht\u00e9moc Tlalpan",         "colonia",  -99.155, 19.28,   95, 10400, 2790, 109, "14080", "96/94/99/75", 1.05, "tlalpan"),
    _c("tl-pueblo-nuevo",          "Pueblo Nuevo",                      "pueblo",   -99.175, 19.297,  88,  9700, 2610, 110, "14110", "92/89/98/65", 1.15, "tlalpan"),
    _c("tl-lomas-padierna",        "Lomas de Padierna",                 "colonia",  -99.205, 19.29,  152, 13900, 3730, 91,  "14240", "90/87/97/60", 1.25, "tlalpan"),
    _c("tl-belisario-dominguez",   "Belisario Dom\u00ednguez",        "colonia",  -99.18,  19.275,  75,  8200, 2200, 109, "14070", "94/92/99/70", 1.05, "tlalpan"),
    _c("tl-las-aguilas-tlalpan",   "Las \u00c1guilas (Tlalpan)",      "colonia",  -99.215, 19.295,  90,  9400, 2530, 104, "14290", "92/90/98/66", 1.10, "tlalpan"),
    _c("tl-bosques-pedregal",      "Bosques del Pedregal",              "colonia",  -99.195, 19.275, 130, 13200, 3540, 102, "14210", "96/95/100/78", 1.00, "tlalpan"),  # orig idx 13 -> tl-bosques-pedregal
    _c("tl-villa-coapa",           "Villa Coapa",                       "unidad_habitacional", -99.14, 19.29, 96, 11800, 3170, 123, "14390", "98/97/100/85", 0.90, "tlalpan"),
    _c("tl-avante",                "Avante",                            "colonia",  -99.135, 19.295,  58,  6100, 1640, 105, "14330", "96/94/100/76", 1.00, "tlalpan"),
    _c("tl-heroes-padierna-tl",    "H\u00e9roes de Padierna (Tlalpan)","colonia",  -99.205, 19.305, 168, 18400, 4940, 110, "14200", "88/85/97/56", 1.25, "tlalpan"),
    _c("tl-miguel-hidalgo",        "Miguel Hidalgo (Tlalpan)",          "colonia",  -99.165, 19.31,  120, 12400, 3320, 103, "14250", "90/87/98/62", 1.20, "tlalpan"),
    _c("tl-san-andres-totoltepec", "San Andr\u00e9s Totoltepec",      "pueblo",   -99.18,  19.26,  250, 14200, 3810, 57,  "14400", "86/82/96/50", 1.20, "tlalpan"),
    _c("tl-magdalena-petlacalco",  "La Magdalena Petlacalco",           "pueblo",   -99.205, 19.24,  180,  8900, 2390, 49,  "14450", "84/80/95/46", 1.20, "tlalpan"),
    _c("tl-san-miguel-xicalco",    "San Miguel Xicalco",                "pueblo",   -99.19,  19.215, 145,  7200, 1930, 50,  "14490", "82/78/94/42", 1.25, "tlalpan"),
    _c("tl-san-miguel-ajusco",     "San Miguel Ajusco",                 "pueblo",   -99.22,  19.195, 320, 18500, 4960, 58,  "14700", "80/76/93/40", 1.30, "tlalpan"),
    _c("tl-santo-tomas-ajusco",    "Santo Tom\u00e1s Ajusco",          "pueblo",   -99.23,  19.215, 220, 12400, 3320, 56,  "14720", "82/78/94/42", 1.25, "tlalpan"),
    _c("tl-san-miguel-topilejo",   "San Miguel Topilejo",               "pueblo",   -99.18,  19.15,  380, 19600, 5250, 52,  "14500", "78/73/92/38", 1.30, "tlalpan"),
    _c("tl-parres-guarda",         "Parres El Guarda",                  "pueblo",   -99.17,  19.115, 290,  8100, 2170, 28,  "14900", "70/65/90/30", 1.35, "tlalpan"),
    _c("tl-fuentes-brotantes",     "Fuentes Brotantes",                 "colonia",  -99.16,  19.282,  78,  8600, 2310, 110, "14410", "94/92/99/68", 1.05, "tlalpan"),
]

ALL_COLONIAS = COLONIAS_MC + COLONIAS_TL

# ═══════════════════════════════════════════════════════════════════════════
# Reporte generator  (exact port of reportes.ts)
# ═══════════════════════════════════════════════════════════════════════════

TITULOS = {
    "bacheo":      ["Bache en vialidad principal", "Hundimiento de pavimento", "Bache de gran tama\u00f1o", "Carpeta asf\u00e1ltica da\u00f1ada"],
    "alumbrado":   ["Luminaria sin funcionar", "Poste de luz parpadeante", "Luminaria fundida", "Tablero el\u00e9ctrico expuesto"],
    "limpia":      ["Acumulaci\u00f3n de residuos", "Falta recolecci\u00f3n programada", "Tiradero clandestino", "Contenedor desbordado"],
    "seguridad":   ["Acto vand\u00e1lico reportado", "Persona sospechosa en zona", "Veh\u00edculo abandonado", "Ri\u00f1a entre vecinos"],
    "agua":        ["Fuga de agua en banqueta", "Falta de suministro", "Toma clandestina detectada", "Agua sucia o turbia"],
    "parques":     ["Mobiliario urbano da\u00f1ado", "Juego infantil roto", "Falta mantenimiento jard\u00edn", "Bebedero descompuesto"],
    "arboles":     ["\u00c1rbol con ramas peligrosas", "Tala clandestina", "\u00c1rbol ca\u00eddo por viento", "Poda urgente requerida"],
    "drenaje":     ["Coladera tapada", "Hundimiento de banqueta", "Olor en alcantarilla", "Rejilla pluvial faltante"],
    "semaforos":   ["Sem\u00e1foro en intermitente", "Se\u00f1alizaci\u00f3n borrada", "Cruce peatonal sin pintar", "Sem\u00e1foro sin funci\u00f3n"],
    "comercio_vp": ["Comerciante invade banqueta", "Puesto sin permiso", "Bloqueo de paso peatonal", "Venta irregular en v\u00eda"],
}

DESCRIPCIONES = {
    "bacheo":      ["Vecinos reportan bache que afecta circulaci\u00f3n vehicular y pone en riesgo a motociclistas. Requiere inspecci\u00f3n y reparaci\u00f3n de carpeta asf\u00e1ltica.", "Hundimiento progresivo del pavimento en cruce de alta afluencia. Se solicita evaluaci\u00f3n estructural.", "Bache de aproximadamente 80 cm de di\u00e1metro, con varilla expuesta. Atenci\u00f3n prioritaria."],
    "alumbrado":   ["Luminaria sin encender desde hace varias noches, afectando seguridad nocturna en la zona.", "Falla intermitente que ya caus\u00f3 cortocircuito a luminarias adyacentes.", "Poste de luz con cableado descubierto, riesgo el\u00e9ctrico para peatones."],
    "limpia":      ["Acumulaci\u00f3n de residuos s\u00f3lidos urbanos pendiente de recolecci\u00f3n, se requiere ruta extraordinaria.", "Tiradero clandestino reportado por colonos, principalmente cascajo y muebles.", "Contenedor p\u00fablico desbordado generando malos olores en v\u00eda p\u00fablica."],
    "seguridad":   ["Vecinos solicitan presencia de elementos por incidencia recurrente en horario nocturno. Se canaliz\u00f3 a SSC-CDMX.", "Veh\u00edculo abandonado con varios d\u00edas sin moverse, posible relaci\u00f3n con incidentes recientes.", "Reporte de actos vand\u00e1licos sobre mobiliario urbano, ya se levant\u00f3 folio de seguimiento."],
    "agua":        ["Fuga sobre banqueta con flujo constante, desperdicia agua potable. Atenci\u00f3n urgente solicitada.", "Suspensi\u00f3n de suministro reportada por 14 viviendas. SACMEX notificado.", "Olor inusual y turbidez del agua en tomas domiciliarias. Pendiente an\u00e1lisis."],
    "parques":     ["Mobiliario urbano (bancas, botes) deteriorado por uso y vandalismo. Requiere mantenimiento.", "Juegos infantiles oxidados con riesgo para menores. Solicitan reemplazo.", "Pasto crecido y poda de setos pendiente. Imagen urbana afectada."],
    "arboles":     ["Ramas con riesgo de caer sobre cableado el\u00e9ctrico. Necesaria poda preventiva por personal certificado.", "\u00c1rbol ca\u00eddo tras viento fuerte, obstruye paso peatonal. Levantamiento requerido.", "Tala irregular reportada por colonos, posible afectaci\u00f3n a \u00e1rea de conservaci\u00f3n."],
    "drenaje":     ["Coladera obstruida provoca encharcamiento permanente, riesgo en temporada de lluvias.", "Hundimiento de banqueta sobre l\u00ednea de drenaje, posible colapso interno.", "Olor f\u00e9tido en alcantarilla y emisi\u00f3n de gases, requiere inspecci\u00f3n urgente."],
    "semaforos":   ["Sem\u00e1foro opera en intermitente, generando confusi\u00f3n y conflictos viales.", "Se\u00f1alizaci\u00f3n horizontal borrada en cruce escolar, prioridad de pintura.", "Sem\u00e1foro sin operaci\u00f3n, vialidad sin control durante hora pico."],
    "comercio_vp": ["Comerciantes invaden por completo la banqueta, impidiendo paso a peatones y personas con movilidad reducida.", "Puesto sin permiso vigente, ya se notific\u00f3 a inspecci\u00f3n general.", "Venta de productos no permitidos en v\u00eda p\u00fablica, vecinos solicitan operativo."],
}

NOMBRES = [
    "Adriana B.", "Luis \u00c1.", "Mariana O.", "Jorge V.", "Patricia G.",
    "Roberto H.", "Sof\u00eda D.", "Carlos M.", "Luc\u00eda F.", "Enrique T.",
    "Daniela R.", "Andr\u00e9s C.", "Beatriz L.", "Fernando S.", "Karla P.",
    "Hugo R.", "Diana M.", "Sergio J.", "Yolanda N.", "Iv\u00e1n Q.",
    "Norma E.", "Pablo A.", "Roc\u00edo V.", "Tom\u00e1s L.", "Ver\u00f3nica O.",
    "Miguel \u00c1.", "Renata P.", "Cristina G.", "Octavio R.", "Alma J.",
]

SUPERVISORES = [
    {"nombre": "Lic. Patricia Mendoza",  "iniciales": "PM", "rol": "Supervisi\u00f3n CESAC"},
    {"nombre": "Ing. Andr\u00e9s Rivera","iniciales": "AR", "rol": "Coordinaci\u00f3n operativa"},
    {"nombre": "Lic. Mariana C\u00e1rdenas", "iniciales": "MC", "rol": "Subdirecci\u00f3n de atenci\u00f3n ciudadana"},
]

INSPECTORES = [
    {"nombre": "Ing. Roberto S\u00e1nchez", "iniciales": "RS", "rol": "Verificaci\u00f3n de obra"},
    {"nombre": "Arq. Lourdes Vega",          "iniciales": "LV", "rol": "Inspecci\u00f3n de calidad"},
]

EVIDENCIA_URLS = ["/placeholder.jpg", "/placeholder.svg", "/placeholder-logo.png", "/placeholder-user.jpg"]

COSTO_BASE = {
    "bacheo": 9_500, "alumbrado": 4_200, "limpia": 2_800, "agua": 14_500,
    "seguridad": 0, "parques": 6_800, "arboles": 4_500, "drenaje": 11_800,
    "semaforos": 9_800, "comercio_vp": 1_800,
}

REPORTE_TO_OBRA_CATS = {
    "bacheo":    ["pavimentacion", "vialidad"],
    "alumbrado": ["alumbrado"],
    "agua":      ["agua_potable", "drenaje"],
    "drenaje":   ["drenaje"],
    "parques":   ["parques"],
    "arboles":   ["parques"],
    "semaforos":  ["vialidad"],
}


def _weighted_pick(items: list[dict], rand) -> dict:
    total = sum(i["peso"] for i in items)
    target = rand() * total
    for item in items:
        target -= item["peso"]
        if target <= 0:
            return item
    return items[-1]


def _pick_colonia(rand, colonias: list[dict]) -> dict:
    total = sum(c["poblacion"] * c["factor_reportes"] for c in colonias)
    target = rand() * total
    for c in colonias:
        target -= c["poblacion"] * c["factor_reportes"]
        if target <= 0:
            return c
    return colonias[-1]


def _jitter_coord(center_lng: float, center_lat: float, area_ha: float, rand, factor: float = 1.0) -> tuple[float, float]:
    radius = min(0.014, 0.0009 + math.sqrt(area_ha) * 0.00045) * factor
    theta = rand() * math.pi * 2
    r = math.sqrt(rand()) * radius
    return (center_lng + math.cos(theta) * r, center_lat + math.sin(theta) * r * 0.78)


def _pick_timestamp(rand, max_days: int = 90) -> int:
    u = rand()
    day_offset = u ** 2.2 * max_days
    hour_offset = rand() * 24
    minute_offset = rand() * 60
    return NOW_MS - round((day_offset * 24 + hour_offset) * 3_600_000 + minute_offset * 60_000)


def _pick_estado(age_hours: float, rand) -> str:
    if age_hours < 24:
        weights = [("nuevo", 0.60), ("asignado", 0.25), ("en_proceso", 0.13), ("resuelto", 0.02), ("cerrado", 0.00)]
    elif age_hours < 24 * 7:
        weights = [("nuevo", 0.12), ("asignado", 0.28), ("en_proceso", 0.35), ("resuelto", 0.20), ("cerrado", 0.05)]
    elif age_hours < 24 * 30:
        weights = [("nuevo", 0.04), ("asignado", 0.12), ("en_proceso", 0.20), ("resuelto", 0.52), ("cerrado", 0.12)]
    else:
        weights = [("nuevo", 0.01), ("asignado", 0.04), ("en_proceso", 0.08), ("resuelto", 0.72), ("cerrado", 0.15)]
    target = rand()
    for id_, w in weights:
        target -= w
        if target <= 0:
            return id_
    return "resuelto"


def _pick_cuadrilla(categoria: str, rand, tenant_prefix: str) -> str:
    compatibles = [c for c in CUADRILLAS if categoria in c["especialidad"]]
    pool = compatibles if compatibles else CUADRILLAS
    base_id = pool[math.floor(rand() * len(pool))]["id"]
    return f"{tenant_prefix}-{base_id}"


def _pick_name(rand) -> dict:
    nombre = NOMBRES[math.floor(rand() * len(NOMBRES))]
    parts = nombre.split()
    iniciales = (parts[0][0] if parts else "A") + (parts[1][0] if len(parts) > 1 else "B")
    return {"nombre": nombre, "iniciales": iniciales}


def _estimar_costo(categoria: str, peso: int, rand) -> int:
    base = COSTO_BASE[categoria]
    if base == 0:
        return 0
    factor = 0.55 + (peso - 1) * 0.45
    jitter = 0.85 + rand() * 0.30
    return round(base * factor * jitter)


def _ms_to_iso(ms: int) -> str:
    dt = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def _ms_to_dt(ms: int | float) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


def _generate_evidencias(reporte_id: str, estado: str, creacion_ms: int, cierre_ms: int | None, rand) -> list[dict]:
    ev = []
    if rand() < 0.9:
        ev.append({
            "id": f"{reporte_id}-EV1",
            "url": EVIDENCIA_URLS[math.floor(rand() * len(EVIDENCIA_URLS))],
            "caption": "Foto aportada al reportar",
            "fecha": _ms_to_dt(creacion_ms + rand() * 60_000),
            "autor": "Ciudadano",
            "tipo": "ciudadano",
        })
    if estado in ("en_proceso", "resuelto", "cerrado") and rand() < 0.45:
        ev.append({
            "id": f"{reporte_id}-EV2",
            "url": EVIDENCIA_URLS[math.floor(rand() * len(EVIDENCIA_URLS))],
            "caption": "Inspecci\u00f3n de la cuadrilla en sitio",
            "fecha": _ms_to_dt(creacion_ms + ((cierre_ms or creacion_ms) - creacion_ms) * 0.5),
            "autor": "Cuadrilla asignada",
            "tipo": "cuadrilla",
        })
    if estado == "resuelto" and cierre_ms and rand() < 0.85:
        ev.append({
            "id": f"{reporte_id}-EV3",
            "url": EVIDENCIA_URLS[math.floor(rand() * len(EVIDENCIA_URLS))],
            "caption": "Estado al cierre de la atenci\u00f3n",
            "fecha": _ms_to_dt(cierre_ms - rand() * 600_000),
            "autor": "Cuadrilla asignada",
            "tipo": "cuadrilla",
        })
    return ev


def _cuadrilla_nombre_by_id(cuadrilla_id: str | None) -> str:
    """Resolve cuadrilla nombre from a tenant-prefixed id like MC-C01."""
    if not cuadrilla_id:
        return "Cuadrilla"
    base = cuadrilla_id.split("-", 1)[-1] if "-" in cuadrilla_id else cuadrilla_id
    for c in CUADRILLAS:
        if c["id"] == base:
            return c["nombre"]
    return "Cuadrilla"


def _generate_timeline(reporte_id: str, estado: str, creacion_ms: int,
                        actualizacion_ms: int, cierre_ms: int | None,
                        ciudadano: dict, cuadrilla_id: str | None, rand) -> list[dict]:
    events = []
    events.append({
        "id": f"{reporte_id}-T1",
        "fecha": _ms_to_dt(creacion_ms),
        "tipo": "creacion",
        "titulo": "Reporte recibido",
        "descripcion": "Captura inicial por canal ciudadano.",
        "autor_nombre": ciudadano["nombre"],
        "autor_iniciales": ciudadano["iniciales"],
        "autor_rol": "Ciudadano",
    })

    if estado == "cerrado":
        validacion_ms = creacion_ms + (rand() * 4 + 1) * 3_600_000
        if validacion_ms <= (cierre_ms or NOW_MS):
            sup = SUPERVISORES[math.floor(rand() * len(SUPERVISORES))]
            events.append({
                "id": f"{reporte_id}-T2",
                "fecha": _ms_to_dt(validacion_ms),
                "tipo": "rechazo",
                "titulo": "Reporte clasificado como no procedente",
                "descripcion": "Tras revisi\u00f3n, el caso no corresponde a la competencia de la alcald\u00eda o ya fue atendido por otra dependencia.",
                "autor_nombre": sup["nombre"],
                "autor_iniciales": sup["iniciales"],
                "autor_rol": sup["rol"],
            })
        return events

    if estado in ("asignado", "en_proceso", "resuelto"):
        sup = SUPERVISORES[math.floor(rand() * len(SUPERVISORES))]
        asignacion_ms = creacion_ms + (1 + rand() * 6) * 3_600_000
        cuad_nombre = _cuadrilla_nombre_by_id(cuadrilla_id)
        events.append({
            "id": f"{reporte_id}-T2",
            "fecha": _ms_to_dt(asignacion_ms),
            "tipo": "asignacion",
            "titulo": f"Asignado a {cuad_nombre}" if cuadrilla_id else "Asignaci\u00f3n pendiente",
            "descripcion": "Se canaliza al equipo operativo competente.",
            "autor_nombre": sup["nombre"],
            "autor_iniciales": sup["iniciales"],
            "autor_rol": sup["rol"],
        })

    if estado in ("en_proceso", "resuelto"):
        cuad_nombre = _cuadrilla_nombre_by_id(cuadrilla_id)
        ms = creacion_ms + (actualizacion_ms - creacion_ms) * 0.35
        events.append({
            "id": f"{reporte_id}-T3",
            "fecha": _ms_to_dt(ms),
            "tipo": "inicio",
            "titulo": "Inicio de atenci\u00f3n en sitio",
            "descripcion": "La cuadrilla acude al lugar, valida el caso y comienza los trabajos.",
            "autor_nombre": cuad_nombre,
            "autor_iniciales": "CU",
            "autor_rol": "Cuadrilla en campo",
        })
        if rand() < 0.45:
            insp_ms = creacion_ms + (actualizacion_ms - creacion_ms) * 0.6
            insp = INSPECTORES[math.floor(rand() * len(INSPECTORES))]
            events.append({
                "id": f"{reporte_id}-T4",
                "fecha": _ms_to_dt(insp_ms),
                "tipo": "inspeccion",
                "titulo": "Inspecci\u00f3n de supervisi\u00f3n",
                "descripcion": "Verificaci\u00f3n de avance y calidad de la atenci\u00f3n.",
                "autor_nombre": insp["nombre"],
                "autor_iniciales": insp["iniciales"],
                "autor_rol": insp["rol"],
            })

    if estado == "resuelto" and cierre_ms:
        cuad_nombre = _cuadrilla_nombre_by_id(cuadrilla_id)
        events.append({
            "id": f"{reporte_id}-T5",
            "fecha": _ms_to_dt(cierre_ms),
            "tipo": "cierre",
            "titulo": "Reporte resuelto",
            "descripcion": "Atenci\u00f3n concluida, evidencia documentada y caso cerrado.",
            "autor_nombre": cuad_nombre,
            "autor_iniciales": "CU",
            "autor_rol": "Cuadrilla en campo",
        })

    return events


def generate_reportes_for_tenant(tenant_id: str, seed: int, total: int) -> list[dict]:
    """Generate all reportes for a tenant. Returns list of reporte dicts."""
    rand = mulberry32(seed)
    colonias = COLONIAS_MC if tenant_id == "magdalena-contreras" else COLONIAS_TL
    prefix = "TL" if tenant_id == "tlalpan" else "MC"
    reportes = []

    for i in range(total):
        colonia = _pick_colonia(rand, colonias)
        categoria = _weighted_pick(CATEGORIAS, rand)["id"]
        fuente = _weighted_pick(FUENTES, rand)["id"]
        prioridad_cfg = _weighted_pick(PRIORIDADES, rand)
        peso = prioridad_cfg["pesoMin"] + math.floor(rand() * (prioridad_cfg["pesoMax"] - prioridad_cfg["pesoMin"] + 1))

        creacion_ms = _pick_timestamp(rand)
        age_hours = (NOW_MS - creacion_ms) / 3_600_000
        estado = _pick_estado(age_hours, rand)

        cuadrilla_id = None if estado == "nuevo" else _pick_cuadrilla(categoria, rand, prefix)

        fecha_cierre = None
        tiempo_atencion_horas = None
        actualizacion_ms = creacion_ms

        if estado in ("resuelto", "cerrado"):
            if prioridad_cfg["id"] == "critica":
                horas_atencion = 2 + rand() * 22
            elif prioridad_cfg["id"] == "alta":
                horas_atencion = 6 + rand() * 60
            elif prioridad_cfg["id"] == "media":
                horas_atencion = 24 + rand() * 120
            else:
                horas_atencion = 48 + rand() * 240
            cierre_ms = min(NOW_MS - rand() * 3_600_000 * 12, creacion_ms + horas_atencion * 3_600_000)
            fecha_cierre = _ms_to_dt(cierre_ms)
            tiempo_atencion_horas = round((cierre_ms - creacion_ms) / 360_000) / 10
            actualizacion_ms = cierre_ms
        elif estado in ("en_proceso", "asignado"):
            actualizacion_ms = creacion_ms + rand() * (NOW_MS - creacion_ms)

        titulos = TITULOS[categoria]
        descripciones = DESCRIPCIONES[categoria]
        ciudadano = _pick_name(rand)
        id_num = str(i + 1).zfill(4)
        reporte_id = f"{prefix}-RC-{id_num}"

        cierre_ms_val = int(fecha_cierre.timestamp() * 1000) if fecha_cierre else None
        evidencias = _generate_evidencias(reporte_id, estado, creacion_ms, cierre_ms_val, rand)
        timeline = _generate_timeline(reporte_id, estado, creacion_ms, actualizacion_ms, cierre_ms_val, ciudadano, cuadrilla_id, rand)

        costo_estimado = None
        if categoria not in ("seguridad", "comercio_vp"):
            costo_estimado = _estimar_costo(categoria, peso, rand)

        gasto_real = None
        if estado == "resuelto" and costo_estimado is not None:
            gasto_real = round(costo_estimado * (0.82 + rand() * 0.32))

        lng, lat = _jitter_coord(colonia["center_lng"], colonia["center_lat"], colonia["area_ha"], rand)

        reportes.append({
            "id": reporte_id,
            "tenant_id": tenant_id,
            "folio": f"{prefix}-2026-{id_num}",
            "categoria_id": categoria,
            "estado": estado,
            "prioridad": prioridad_cfg["id"],
            "fuente": fuente,
            "cuadrilla_id": cuadrilla_id,
            "colonia_id": colonia["id"],
            "colonia_nombre": colonia["nombre"],
            "lng": lng,
            "lat": lat,
            "peso": peso,
            "titulo": titulos[math.floor(rand() * len(titulos))],
            "descripcion": descripciones[math.floor(rand() * len(descripciones))],
            "fecha_creacion": _ms_to_dt(creacion_ms),
            "fecha_actualizacion": _ms_to_dt(actualizacion_ms),
            "fecha_cierre": fecha_cierre,
            "tiempo_atencion_horas": tiempo_atencion_horas,
            "costo_estimado": costo_estimado,
            "gasto_real": gasto_real,
            "ciudadano_nombre": ciudadano["nombre"],
            "ciudadano_iniciales": ciudadano["iniciales"],
            "evidencias": evidencias,
            "timeline": timeline,
            "obras_relacionadas_ids": [],
        })

    return reportes


# ═══════════════════════════════════════════════════════════════════════════
# Obras generator  (exact port of obras.ts)
# ═══════════════════════════════════════════════════════════════════════════

NOMBRES_OBRA = {
    "pavimentacion":      ["Repavimentaci\u00f3n integral Av. San Bernab\u00e9", "Bacheo profundo eje Cda. Independencia", "Reencarpetado de Av. Luis Cabrera", "Rehabilitaci\u00f3n de carpeta asf\u00e1ltica"],
    "drenaje":            ["Sustituci\u00f3n de colector pluvial", "Rehabilitaci\u00f3n de red de drenaje sanitario", "Desazolve de barranca y atarjeas", "Construcci\u00f3n de pozo de absorci\u00f3n"],
    "alumbrado":          ["Modernizaci\u00f3n a luminarias LED", "Reemplazo de luminarias en cabecera", "Instalaci\u00f3n de balastros en parque"],
    "agua_potable":       ["Sustituci\u00f3n de red de agua potable", "Renovaci\u00f3n de toma domiciliaria sectorial", "Instalaci\u00f3n de macromedidor"],
    "parques":            ["Rehabilitaci\u00f3n de Parque Tarango", "Acondicionamiento de cancha multiusos", "Reforestaci\u00f3n urbana programa MC", "Mejora de andadores y mobiliario"],
    "escuelas":           ["Mantenimiento mayor Escuela Primaria Benito Ju\u00e1rez", "Renovaci\u00f3n de ba\u00f1os Secundaria 35", "Reparaci\u00f3n de techumbre escolar"],
    "edificios_publicos": ["Remodelaci\u00f3n de Centro de Salud T-III", "Rehabilitaci\u00f3n del CESAC Magdalena", "Mantenimiento integral Mercado Padierna"],
    "vialidad":           ["Construcci\u00f3n de puente peatonal", "Ampliaci\u00f3n de banquetas accesibles", "Rehabilitaci\u00f3n de guarniciones", "Reubicaci\u00f3n de parada de transporte"],
    "imagen_urbana":      ["Rescate de fachadas patrimoniales", "Renovaci\u00f3n de mobiliario urbano", "Pintura de murales comunitarios"],
}

DESCRIPCIONES_OBRA = {
    "pavimentacion":      "Trabajos de retiro de carpeta asf\u00e1ltica existente, recompactaci\u00f3n de base y aplicaci\u00f3n de capa nueva de concreto asf\u00e1ltico AC-20 con sellado y se\u00f1alizaci\u00f3n horizontal.",
    "drenaje":            "Sustituci\u00f3n de tuber\u00eda de drenaje en operaci\u00f3n con tuber\u00eda de polietileno de alta densidad y rehabilitaci\u00f3n de pozos de visita conforme a NOM-001-CONAGUA.",
    "alumbrado":          "Reemplazo de luminarias de vapor de sodio por luminarias LED 100 W con telegesti\u00f3n, ahorro energ\u00e9tico estimado del 58% y nueva configuraci\u00f3n fotom\u00e9trica.",
    "agua_potable":       "Renovaci\u00f3n de red secundaria de agua potable con tuber\u00eda de PEAD 2-6 pulgadas, sustituci\u00f3n de tomas domiciliarias y reposici\u00f3n de pavimento afectado.",
    "parques":            "Acondicionamiento integral con poda, riego, rehabilitaci\u00f3n de juegos infantiles, sustituci\u00f3n de pisos seguros y nueva iluminaci\u00f3n LED solar.",
    "escuelas":           "Mantenimiento mayor: impermeabilizaci\u00f3n de azoteas, sustituci\u00f3n de luminarias, rehabilitaci\u00f3n de ba\u00f1os, pintura general y revisi\u00f3n de instalaciones el\u00e9ctricas.",
    "edificios_publicos": "Remodelaci\u00f3n integral con sustituci\u00f3n de pisos, pintura, sistema el\u00e9ctrico, climatizaci\u00f3n y accesibilidad universal conforme a NOM-008-SSA2.",
    "vialidad":           "Construcci\u00f3n/rehabilitaci\u00f3n de infraestructura vial con cumplimiento de accesibilidad universal, drenaje pluvial y se\u00f1alizaci\u00f3n horizontal/vertical.",
    "imagen_urbana":      "Intervenci\u00f3n en fachadas, mobiliario urbano y \u00e1reas comunes para fortalecer identidad de barrio y mejorar la percepci\u00f3n de seguridad y limpieza.",
}

NOMBRES_RESPONSABLES = [
    {"nombre": "Ing. Adriana Belmont",     "iniciales": "AB", "cargo": "Subdirecci\u00f3n de Obras"},
    {"nombre": "Arq. Luis \u00c1ngel Reyes","iniciales": "LR", "cargo": "Jefatura de Proyectos"},
    {"nombre": "Ing. Mariana Ortega",        "iniciales": "MO", "cargo": "Direcci\u00f3n de Servicios Urbanos"},
    {"nombre": "Arq. Jorge Vargas",          "iniciales": "JV", "cargo": "Jefatura de Pavimentaci\u00f3n"},
    {"nombre": "Ing. Patricia Galv\u00e1n",  "iniciales": "PG", "cargo": "Coordinaci\u00f3n de Obras Hidr\u00e1ulicas"},
    {"nombre": "Ing. Roberto Huerta",        "iniciales": "RH", "cargo": "Subdirecci\u00f3n de Alumbrado"},
]

PRESUPUESTO_CONCEPTOS = {
    "pavimentacion":      [{"concepto": "Retiro de carpeta asf\u00e1ltica", "unidad": "m\u00b2"}, {"concepto": "Suministro y colocaci\u00f3n AC-20", "unidad": "ton"}, {"concepto": "Recompactaci\u00f3n de base", "unidad": "m\u00b2"}, {"concepto": "Se\u00f1alizaci\u00f3n horizontal", "unidad": "ml"}],
    "drenaje":            [{"concepto": "Suministro de tuber\u00eda PEAD 30\"", "unidad": "ml"}, {"concepto": "Excavaci\u00f3n con maquinaria", "unidad": "m\u00b3"}, {"concepto": "Pozos de visita prefabricados", "unidad": "pza"}, {"concepto": "Reposici\u00f3n de pavimento", "unidad": "m\u00b2"}],
    "alumbrado":          [{"concepto": "Luminaria LED 100W con telegesti\u00f3n", "unidad": "pza"}, {"concepto": "Instalaci\u00f3n y conexi\u00f3n", "unidad": "pza"}, {"concepto": "Cable THW-LS 8 AWG", "unidad": "ml"}, {"concepto": "Tablero de control", "unidad": "pza"}],
    "agua_potable":       [{"concepto": "Tuber\u00eda PEAD 6\"", "unidad": "ml"}, {"concepto": "Toma domiciliaria completa", "unidad": "pza"}, {"concepto": "Pruebas hidr\u00e1ulicas", "unidad": "global"}],
    "parques":            [{"concepto": "Sustituci\u00f3n de pisos seguros", "unidad": "m\u00b2"}, {"concepto": "Juegos infantiles inclusivos", "unidad": "set"}, {"concepto": "Mobiliario urbano (bancas, botes)", "unidad": "pza"}, {"concepto": "Riego programado", "unidad": "global"}],
    "escuelas":           [{"concepto": "Impermeabilizaci\u00f3n de azoteas", "unidad": "m\u00b2"}, {"concepto": "Sustituci\u00f3n de muebles de ba\u00f1o", "unidad": "pza"}, {"concepto": "Pintura general", "unidad": "m\u00b2"}],
    "edificios_publicos": [{"concepto": "Pintura interior", "unidad": "m\u00b2"}, {"concepto": "Renovaci\u00f3n instalaci\u00f3n el\u00e9ctrica", "unidad": "global"}, {"concepto": "Climatizaci\u00f3n", "unidad": "pza"}, {"concepto": "Mobiliario administrativo", "unidad": "set"}],
    "vialidad":           [{"concepto": "Banquetas con accesibilidad universal", "unidad": "m\u00b2"}, {"concepto": "Guarniciones de concreto", "unidad": "ml"}, {"concepto": "Se\u00f1alizaci\u00f3n vertical", "unidad": "pza"}],
    "imagen_urbana":      [{"concepto": "Pintura de fachadas", "unidad": "m\u00b2"}, {"concepto": "Mobiliario urbano", "unidad": "pza"}, {"concepto": "Murales comunitarios", "unidad": "pza"}],
}

ROLES_EQUIPO = [
    "Residente de obra", "Supervisor de obra", "Coordinador t\u00e9cnico",
    "Auxiliar administrativo", "Operador de maquinaria", "Verificador externo",
    "Enlace ciudadano",
]

NOMBRES_EQUIPO = [
    {"nombre": "Carlos M\u00e9ndez",   "iniciales": "CM"},
    {"nombre": "Sof\u00eda Dom\u00ednguez", "iniciales": "SD"},
    {"nombre": "Enrique Torres",        "iniciales": "ET"},
    {"nombre": "Daniela Reyes",         "iniciales": "DR"},
    {"nombre": "Andr\u00e9s Cruz",      "iniciales": "AC"},
    {"nombre": "Beatriz L\u00f3pez",    "iniciales": "BL"},
    {"nombre": "Hugo Ram\u00edrez",     "iniciales": "HR"},
    {"nombre": "Ver\u00f3nica Olvera",  "iniciales": "VO"},
    {"nombre": "Renata P\u00e9rez",     "iniciales": "RP"},
    {"nombre": "Octavio Ramos",          "iniciales": "OR"},
]

CIERRE_ESTADOS = ["cerrada_total", "cerrada_parcial", "desvio"]

# Mapeo determinista CIERRE_ESTADOS -> tipo_afectacion del modelo
# ('total' | 'parcial' | 'desvio'), aplicado a las calles ya sembradas.
CIERRE_TO_TIPO_AFECTACION = {
    "cerrada_total": "total",
    "cerrada_parcial": "parcial",
    "desvio": "desvio",
}

# ═══════════════════════════════════════════════════════════════════════════
# Compromisos de gobierno (metas públicas con avance medible)
# Plantilla compartida por ambos tenants; id determinista "{prefix}-CMP-NN".
# Estados válidos: en_progreso | cumplido | en_riesgo | retrasado
# ═══════════════════════════════════════════════════════════════════════════

COMPROMISOS_BASE = [
    {
        "titulo": "Rehabilitar 50 km de vialidades primarias",
        "descripcion": "Programa anual de bacheo y repavimentación de las vías de mayor afluencia para reducir incidentes viales.",
        "area_id": "bacheo",
        "meta": "50 km de carpeta asfáltica renovada",
        "avance_pct": 62,
        "estado": "en_progreso",
        "dias_objetivo": 90,
    },
    {
        "titulo": "Modernizar el alumbrado público a tecnología LED",
        "descripcion": "Sustitución de luminarias por tecnología LED de bajo consumo en colonias con mayor índice de inseguridad.",
        "area_id": "alumbrado",
        "meta": "8,000 luminarias LED instaladas",
        "avance_pct": 100,
        "estado": "cumplido",
        "dias_objetivo": -20,
    },
    {
        "titulo": "Eliminar tiraderos clandestinos prioritarios",
        "descripcion": "Operativos de limpieza y vigilancia en los puntos críticos de acumulación de residuos detectados por la ciudadanía.",
        "area_id": "limpia",
        "meta": "40 tiraderos erradicados",
        "avance_pct": 35,
        "estado": "en_riesgo",
        "dias_objetivo": 45,
    },
    {
        "titulo": "Reducir fugas en la red de agua potable",
        "descripcion": "Detección y reparación de fugas en la red secundaria para abatir pérdidas y mejorar la presión de suministro.",
        "area_id": "agua",
        "meta": "Reducir pérdidas físicas al 15%",
        "avance_pct": 48,
        "estado": "retrasado",
        "dias_objetivo": 120,
    },
    {
        "titulo": "Rehabilitar parques y áreas verdes vecinales",
        "descripcion": "Recuperación de mobiliario, juegos infantiles y arbolado en parques con mayor uso comunitario.",
        "area_id": "parques",
        "meta": "25 parques rehabilitados",
        "avance_pct": 78,
        "estado": "en_progreso",
        "dias_objetivo": 60,
    },
    {
        "titulo": "Programa permanente de poda y arbolado urbano",
        "descripcion": "Poda preventiva y censo de arbolado de riesgo para evitar caídas durante la temporada de lluvias.",
        "area_id": "arboles",
        "meta": "3,500 árboles atendidos",
        "avance_pct": 22,
        "estado": "retrasado",
        "dias_objetivo": 150,
    },
]

# ═══════════════════════════════════════════════════════════════════════════
# Trámites y servicios (catálogo público por tenant)
# Plantilla compartida por ambos tenants; id determinista "{prefix}-TRM-NN".
# La dependencia se resuelve por tenant: "{Dependencia} · {Alcaldía}".
# ═══════════════════════════════════════════════════════════════════════════

TRAMITES_BASE = [
    {
        "nombre": "Licencia de Funcionamiento para Establecimiento Mercantil",
        "dependencia": "Dirección de Gobierno y Reglamentos",
        "area_id": "comercio_vp",
        "descripcion": "Permiso para operar un establecimiento mercantil de bajo impacto (giro de comercio o servicios) dentro de la demarcación.",
        "requisitos": [
            "Identificación oficial vigente del solicitante",
            "Comprobante de domicilio del establecimiento (no mayor a 3 meses)",
            "Constancia de alineamiento y número oficial",
            "Aviso de declaración de apertura ante la Tesorería",
            "RFC y CURP del titular",
        ],
        "costo": "Gratuito (giros de bajo impacto)",
        "tiempo_estimado": "3 a 5 días hábiles",
        "vigencia": "Indefinida con refrendo anual",
        "documentos": [
            {"nombre": "Formato de declaración de apertura", "url": "/formatos/declaracion-apertura.pdf"},
            {"nombre": "Guía de giros de bajo impacto", "url": "/formatos/giros-bajo-impacto.pdf"},
        ],
        "horarios": "Lunes a viernes de 9:00 a 14:00 h",
    },
    {
        "nombre": "Constancia de Residencia",
        "dependencia": "Dirección Ejecutiva de Atención Ciudadana",
        "area_id": None,
        "descripcion": "Documento oficial que acredita que una persona reside dentro de la demarcación territorial.",
        "requisitos": [
            "Identificación oficial vigente con fotografía",
            "Comprobante de domicilio reciente (no mayor a 3 meses)",
            "CURP",
            "Dos testigos con identificación (en caso de no contar con comprobante)",
        ],
        "costo": "Gratuito",
        "tiempo_estimado": "Mismo día",
        "vigencia": "90 días naturales",
        "documentos": [
            {"nombre": "Formato de solicitud de constancia", "url": "/formatos/solicitud-constancia-residencia.pdf"},
        ],
        "horarios": "Lunes a viernes de 9:00 a 15:00 h",
    },
    {
        "nombre": "Solicitud de Poda o Derribo de Árbol",
        "dependencia": "Dirección de Medio Ambiente y Servicios Urbanos",
        "area_id": "arboles",
        "descripcion": "Trámite para solicitar la poda, balanceo o derribo de arbolado en vía pública que represente riesgo o interfiera con servicios.",
        "requisitos": [
            "Identificación oficial del solicitante",
            "Domicilio o ubicación exacta del árbol (calle y referencias)",
            "Fotografía del árbol y su entorno",
            "Motivo de la solicitud (riesgo, plaga, interferencia)",
        ],
        "costo": "Gratuito",
        "tiempo_estimado": "10 a 15 días hábiles (previa inspección)",
        "vigencia": "No aplica",
        "documentos": [
            {"nombre": "Formato de solicitud de poda", "url": "/formatos/solicitud-poda-arbol.pdf"},
        ],
        "donde_acudir": "Ventanilla de Medio Ambiente",
        "horarios": "Lunes a viernes de 9:00 a 14:00 h",
    },
    {
        "nombre": "Reporte de Bache en Vía Pública",
        "dependencia": "Dirección de Obras y Servicios Urbanos",
        "area_id": "bacheo",
        "descripcion": "Reporte ciudadano para la reparación de baches y deterioro de la carpeta asfáltica en calles secundarias.",
        "requisitos": [
            "Ubicación exacta del bache (calle, esquina y colonia)",
            "Fotografía del deterioro (opcional pero recomendado)",
            "Datos de contacto para seguimiento (opcional)",
        ],
        "costo": "Gratuito",
        "tiempo_estimado": "5 a 10 días hábiles",
        "vigencia": "No aplica",
        "documentos": [],
        "donde_acudir": "CESAC o app Tu Alcald.IA",
        "horarios": "Atención en línea 24/7",
    },
    {
        "nombre": "Constancia de Alineamiento y Número Oficial",
        "dependencia": "Dirección de Desarrollo Urbano",
        "area_id": None,
        "descripcion": "Documento que fija la alineación del predio respecto a la vía pública y asigna o ratifica el número oficial del inmueble.",
        "requisitos": [
            "Escritura o título de propiedad del predio",
            "Boleta predial al corriente",
            "Identificación oficial del propietario",
            "Croquis de localización del predio",
        ],
        "costo": "$420.00 (cuota vigente)",
        "tiempo_estimado": "5 a 8 días hábiles",
        "vigencia": "1 año",
        "documentos": [
            {"nombre": "Formato de solicitud de alineamiento", "url": "/formatos/solicitud-alineamiento.pdf"},
        ],
        "donde_acudir": "Ventanilla Única de Desarrollo Urbano",
        "horarios": "Lunes a viernes de 9:00 a 14:00 h",
    },
    {
        "nombre": "Apoyo de Pipa de Agua Potable",
        "dependencia": "Dirección de Agua y Drenaje",
        "area_id": "agua",
        "descripcion": "Solicitud de suministro de agua potable mediante pipa para colonias con desabasto temporal o sin red.",
        "requisitos": [
            "Identificación oficial del solicitante",
            "Comprobante de domicilio dentro de la demarcación",
            "Ubicación accesible para la pipa",
        ],
        "costo": "Gratuito (zonas sin red)",
        "tiempo_estimado": "24 a 72 horas según demanda",
        "vigencia": "No aplica",
        "documentos": [],
        "donde_acudir": "CESAC o módulo de Agua",
        "horarios": "Lunes a domingo de 8:00 a 18:00 h",
    },
    {
        "nombre": "Registro al Programa de Apoyos Sociales",
        "dependencia": "Dirección de Desarrollo Social",
        "area_id": None,
        "descripcion": "Inscripción a los programas sociales de la alcaldía (becas, apoyo a adultos mayores y personas con discapacidad).",
        "requisitos": [
            "Acta de nacimiento",
            "CURP actualizada",
            "Comprobante de domicilio reciente",
            "Identificación oficial",
            "Comprobante que acredite el supuesto del programa",
        ],
        "costo": "Gratuito",
        "tiempo_estimado": "Sujeto a convocatoria",
        "vigencia": "Ciclo del programa",
        "documentos": [
            {"nombre": "Formato único de registro", "url": "/formatos/registro-apoyos-sociales.pdf"},
            {"nombre": "Reglas de operación", "url": "/formatos/reglas-operacion-social.pdf"},
        ],
        "donde_acudir": "Dirección de Desarrollo Social",
        "horarios": "Lunes a viernes de 9:00 a 15:00 h",
    },
    {
        "nombre": "Reporte de Luminaria Apagada o Dañada",
        "dependencia": "Subdirección de Alumbrado Público",
        "area_id": "alumbrado",
        "descripcion": "Reporte para el mantenimiento o sustitución de luminarias de alumbrado público fundidas, intermitentes o dañadas.",
        "requisitos": [
            "Ubicación de la luminaria (calle, número de poste si es visible)",
            "Descripción de la falla (apagada, intermitente, cableado expuesto)",
            "Datos de contacto para seguimiento (opcional)",
        ],
        "costo": "Gratuito",
        "tiempo_estimado": "3 a 7 días hábiles",
        "vigencia": "No aplica",
        "documentos": [],
        "donde_acudir": "CESAC o app Tu Alcald.IA",
        "horarios": "Atención en línea 24/7",
    },
]

# ═══════════════════════════════════════════════════════════════════════════
# Avisos y campañas institucionales (por tenant)
# id determinista "{prefix}-AVI-NN". tipo: aviso | campania.
# ═══════════════════════════════════════════════════════════════════════════

AVISOS_BASE = [
    {
        "titulo": "Suspensión programada de agua potable",
        "cuerpo": "Por mantenimiento a la red de distribución, el suministro de agua potable se verá afectado en colonias de la zona alta. Se recomienda almacenar agua con anticipación. El servicio se restablecerá de forma gradual.",
        "tipo": "aviso",
        "area_id": "agua",
        "segmento": "Zona alta de la demarcación",
        "dias_offset": -2,
        "activo": True,
    },
    {
        "titulo": "Campaña de Descacharrización 2026",
        "cuerpo": "Saca los cacharros que acumulan agua y previene el dengue. Las unidades recolectoras recorrerán las colonias según calendario. Participa y mantén tu hogar libre de criaderos de mosco.",
        "tipo": "campania",
        "area_id": "limpia",
        "segmento": "Todas las colonias",
        "dias_offset": -5,
        "activo": True,
    },
    {
        "titulo": "Jornada de Vacunación Antirrábica Canina y Felina",
        "cuerpo": "Vacuna gratis a tu perro o gato en los módulos instalados en plazas y mercados públicos. Lleva a tu mascota con correa o en transportadora. No requiere cita.",
        "tipo": "campania",
        "area_id": None,
        "segmento": "Población general",
        "dias_offset": 3,
        "activo": True,
    },
    {
        "titulo": "Cierre vial por obra de repavimentación",
        "cuerpo": "Por trabajos de repavimentación habrá cierre parcial a la circulación en vialidades primarias durante horario diurno. Se habilitarán rutas alternas señalizadas. Maneja con precaución y respeta los desvíos.",
        "tipo": "aviso",
        "area_id": "bacheo",
        "segmento": "Automovilistas y transporte público",
        "dias_offset": -1,
        "activo": True,
    },
    {
        "titulo": "Convocatoria a Presupuesto Participativo",
        "cuerpo": "Decide en qué se invierten los recursos de tu colonia. Registra y vota por los proyectos de mejora de tu comunidad. Consulta los requisitos y fechas en los módulos de atención ciudadana.",
        "tipo": "campania",
        "area_id": None,
        "segmento": "Vecinas y vecinos registrados",
        "dias_offset": 7,
        "activo": True,
    },
]

EVIDENCIA_CAPTIONS = [
    "Sitio antes de iniciar trabajos",
    "Retiro de carpeta existente",
    "Avance de obra al 35%",
    "Maquinaria pesada operando",
    "Cuadrilla colocando capa nueva",
    "Sellado de juntas",
    "Acabados finales",
    "Inspecci\u00f3n de supervisi\u00f3n",
    "Recepci\u00f3n de obra",
]


def _generate_equipo(obra_id: str, rand) -> list[dict]:
    size = 3 + math.floor(rand() * 4)
    used: set[int] = set()
    equipo = []
    for i in range(size):
        idx = math.floor(rand() * len(NOMBRES_EQUIPO))
        while idx in used:
            idx = (idx + 1) % len(NOMBRES_EQUIPO)
        used.add(idx)
        persona = NOMBRES_EQUIPO[idx]
        rol = ROLES_EQUIPO[0] if i == 0 else ROLES_EQUIPO[1 + math.floor(rand() * (len(ROLES_EQUIPO) - 1))]
        equipo.append({
            "id": f"{obra_id}-EM{idx:02d}",
            "obra_id": obra_id,
            "nombre": persona["nombre"],
            "iniciales": persona["iniciales"],
            "rol": rol,
            "contacto": f"{persona['iniciales'].lower()}@mcontreras.gob.mx",
        })
    return equipo


def _generate_presupuesto(categoria: str, rand) -> dict:
    conceptos = PRESUPUESTO_CONCEPTOS[categoria]
    items = []
    for c in conceptos:
        cantidad = round((20 + rand() * 480) * 10) / 10
        precio_unitario = round(180 + rand() * 4800)
        importe = round(cantidad * precio_unitario)
        items.append({**c, "cantidad": cantidad, "precio_unitario": precio_unitario, "importe": importe})
    subtotal = sum(it["importe"] for it in items)
    autorizado = round(subtotal * (1 + (rand() - 0.4) * 0.18))
    ejercido = round(autorizado * (0.05 + rand() * 0.9))
    return {"autorizado": autorizado, "ejercido": ejercido, "items": items}


def _pick_obra_estado(rand) -> str:
    weights = [("planeacion", 0.10), ("licitacion", 0.10), ("en_ejecucion", 0.45), ("suspendida", 0.05), ("en_cierre", 0.10), ("concluida", 0.20)]
    t = rand()
    for id_, w in weights:
        t -= w
        if t <= 0:
            return id_
    return "en_ejecucion"


def _pick_prioridad_obra(rand) -> str:
    weights = [("baja", 0.20), ("media", 0.45), ("alta", 0.25), ("estrategica", 0.10)]
    t = rand()
    for id_, w in weights:
        t -= w
        if t <= 0:
            return id_
    return "media"


def _avance_por_estado(estado: str, rand) -> int:
    if estado == "planeacion":
        return round(rand() * 5)
    if estado == "licitacion":
        return round(5 + rand() * 8)
    if estado == "en_ejecucion":
        return round(20 + rand() * 60)
    if estado == "suspendida":
        return round(30 + rand() * 40)
    if estado == "en_cierre":
        return round(85 + rand() * 12)
    return 100  # concluida


def _calle_coords(calle_id: str, clng: float, clat: float) -> str:
    """Polilínea corta determinista cerca del centro de la obra, como JSON string
    (placeholder de geometría de calle afectada; el frontend la dibuja como
    cierre vial).

    Usa su propio RNG sembrado por el id de la calle, así que NO consume del
    `rand` del seed y la secuencia determinista del resto no cambia.
    """
    import hashlib
    import json
    import random as _random

    r = _random.Random(int(hashlib.md5(calle_id.encode()).hexdigest()[:8], 16))
    bx = clng + r.uniform(-0.0035, 0.0035)
    by = clat + r.uniform(-0.0035, 0.0035)
    a = r.uniform(0, 2 * math.pi)
    step = 0.00085  # ~90 m por segmento
    pts: list[list[float]] = []
    for k in range(r.choice([2, 3, 3, 4])):
        pts.append([round(bx + math.cos(a) * step * k, 6),
                    round(by + math.sin(a) * step * k, 6)])
        a += r.uniform(-0.4, 0.4)  # ligera curva
    return json.dumps(pts)


def _generate_calles_afectadas(
    obra_id: str, estado: str, rand, base_lng: float = 0.0, base_lat: float = 0.0
) -> list[dict]:
    """Generate calles afectadas.

    Note: the TS version uses a precomputed street graph (obras-streets.json)
    to pick real segments via pickRealSegments. Since that 60k-token JSON is not
    available here, we generate placeholder calles and consume rand calls in a
    compatible cadence. The obras PRNG sequence therefore differs from the TS
    frontend, but it is still fully deterministic within this seed script.
    """
    activas = estado not in ("planeacion", "licitacion", "concluida")
    if not activas:
        # Still consume the rand calls the TS would make for segment picking
        rand()  # for desiredCalles calculation
        return []
    desired = 1 + math.floor(rand() * 3)
    calles = []
    for ci in range(desired):
        cierre_estado = CIERRE_ESTADOS[math.floor(rand() * len(CIERRE_ESTADOS))]
        inicio_ms = NOW_MS - rand() * 30 * DAY_MS
        fin_ms = inicio_ms + (5 + rand() * 35) * DAY_MS
        calles.append({
            "id": f"{obra_id}-CA{ci + 1}",
            "obra_id": obra_id,
            "nombre": f"Calle afectada {ci + 1}",
            "estado": cierre_estado,
            "coordenadas": _calle_coords(f"{obra_id}-CA{ci + 1}", base_lng, base_lat),
            "fecha_inicio": _ms_to_dt(inicio_ms),
            "fecha_fin_estimada": _ms_to_dt(fin_ms),
            "alternativas_viales": None,
        })
    return calles


def _generate_obra_timeline(obra_id: str, estado: str, fecha_inicio_str_ms: int,
                              fecha_fin_str_ms: int, responsable: dict, rand) -> list[dict]:
    inicio = fecha_inicio_str_ms
    fin = fecha_fin_str_ms
    events: list[dict] = []

    def push(offset_days: float, tipo: str, titulo: str, descripcion: str | None = None):
        ms = inicio - 14 * DAY_MS + offset_days * DAY_MS
        if ms > NOW_MS:
            return
        events.append({
            "id": f"{obra_id}-T{len(events) + 1}",
            "obra_id": obra_id,
            "fecha": _ms_to_dt(ms),
            "tipo": tipo,
            "titulo": titulo,
            "descripcion": descripcion,
            "autor_nombre": responsable["nombre"],
            "autor_iniciales": responsable["iniciales"],
            "autor_rol": responsable["cargo"],
        })

    push(0, "creacion", "Expediente abierto", "Solicitud canalizada por la Subdirecci\u00f3n de Obras.")
    push(2, "autorizacion", "Autorizaci\u00f3n presupuestal", "Recurso autorizado por la Tesorer\u00eda.")
    push(5, "licitacion", "Convocatoria p\u00fablica", "Publicaci\u00f3n en Plataforma CDMX y portal de Compranet.")
    push(10, "fallo", "Fallo de licitaci\u00f3n", "Adjudicaci\u00f3n al contratista con mayor calificaci\u00f3n t\u00e9cnica.")

    if estado not in ("planeacion", "licitacion"):
        push(14, "inicio", "Inicio de obra", "Entrega del sitio al contratista; bit\u00e1cora abierta.")
        span = (fin - inicio) / DAY_MS
        avances = min(5, max(2, math.floor(span / 7)))
        for av_i in range(1, avances + 1):
            push(14 + (av_i * span) / (avances + 1), "avance",
                 f"Avance del {round((av_i / (avances + 1)) * 100)}%",
                 "Reporte fotogr\u00e1fico y bit\u00e1cora firmada por residente.")
            if rand() < 0.35:
                push(14 + (av_i * span) / (avances + 1) + 1, "inspeccion",
                     "Inspecci\u00f3n de supervisi\u00f3n", "Verificaci\u00f3n de calidad y avance f\u00edsico.")
            if rand() < 0.25:
                push(14 + (av_i * span) / (avances + 1) + 2, "pago",
                     f"Estimaci\u00f3n {av_i} pagada", "Pago de estimaci\u00f3n liberada conforme a calendario.")
        if estado == "suspendida" and rand() < 0.8:
            push(14 + span * 0.6, "incidente", "Suspensi\u00f3n temporal",
                 "Detectada interferencia con instalaciones subterr\u00e1neas; pendiente coordinaci\u00f3n con CFE.")
        if estado in ("en_cierre", "concluida"):
            push(span + 14, "cierre", "Acta de entrega-recepci\u00f3n",
                 "Firma de acta entre la alcald\u00eda y el contratista.")

    events.sort(key=lambda e: e["fecha"])
    return events


def _generate_obra_documentos(obra_id: str, estado: str, fecha_inicio_ms: int, rand) -> list[dict]:
    inicio = fecha_inicio_ms
    docs: list[dict] = []

    def add(tipo: str, nombre: str, dias_offset: int, autor: str):
        ms = inicio - 14 * DAY_MS + dias_offset * DAY_MS
        if ms > NOW_MS:
            return
        docs.append({
            "id": f"{obra_id}-D{len(docs) + 1}",
            "obra_id": obra_id,
            "nombre": nombre,
            "tipo": tipo,
            "tamano_kb": 320 + math.floor(rand() * 4800),
            "fecha_subida": _ms_to_dt(ms),
            "autor": autor,
        })

    add("contrato", f"Contrato_{obra_id}.pdf", 8, "Direcci\u00f3n Jur\u00eddica")
    add("permiso", "Permiso_SEDUVI.pdf", 4, "SEDUVI")
    add("plano", "Plano_general_R0.dwg", 6, "Subdirecci\u00f3n T\u00e9cnica")
    add("orden_trabajo", "Orden_de_trabajo_001.pdf", 14, "Residencia de obra")
    if estado not in ("planeacion", "licitacion"):
        add("reporte_avance", "Reporte_avance_semana_1.pdf", 21, "Residencia de obra")
        add("estimacion", "Estimacion_001.xlsx", 28, "Residencia de obra")
        if rand() < 0.5:
            add("reporte_avance", "Reporte_avance_semana_2.pdf", 28, "Residencia de obra")
        if estado in ("en_cierre", "concluida"):
            add("acta", "Acta_entrega_recepcion.pdf", 60, "Subdirecci\u00f3n de Obras")
    return docs


def _generate_obra_evidencias(obra_id: str, estado: str, fecha_inicio_ms: int, rand) -> list[dict]:
    inicio = fecha_inicio_ms
    ev: list[dict] = []
    total_shots = 0 if estado in ("planeacion", "licitacion") else 4 + math.floor(rand() * 6)
    tipos_cycle = ["antes", "durante", "durante", "durante", "despues"]
    for ei in range(total_shots):
        dias_offset = -1 if ei == 0 else 1 + ei * 4
        ms = inicio + dias_offset * DAY_MS
        if ms > NOW_MS:
            continue
        if ei == 0:
            tipo_ev = "antes"
        elif estado == "concluida" and ei == total_shots - 1:
            tipo_ev = "despues"
        else:
            tipo_ev = tipos_cycle[min(ei, len(tipos_cycle) - 1)]
        ev.append({
            "id": f"{obra_id}-E{ei + 1}",
            "obra_id": obra_id,
            "url": EVIDENCIA_URLS[math.floor(rand() * len(EVIDENCIA_URLS))],
            "caption": EVIDENCIA_CAPTIONS[min(ei, len(EVIDENCIA_CAPTIONS) - 1)],
            "fecha": _ms_to_dt(ms),
            "autor": "Residencia de obra",
            "tipo": tipo_ev,
        })
    return ev


def generate_obras_for_tenant(tenant_id: str, seed: int, total: int) -> list[dict]:
    """Generate all obras for a tenant."""
    rand = mulberry32(seed)
    colonias = COLONIAS_MC if tenant_id == "magdalena-contreras" else COLONIAS_TL
    prefix = "TL" if tenant_id == "tlalpan" else "MC"
    obras = []

    for i in range(total):
        colonia = _pick_colonia(rand, colonias)
        categoria = _weighted_pick(OBRA_CATEGORIAS, rand)["id"]
        estado = _pick_obra_estado(rand)
        prioridad = _pick_prioridad_obra(rand)
        responsable = NOMBRES_RESPONSABLES[math.floor(rand() * len(NOMBRES_RESPONSABLES))]

        # Generate equipo (consume rand like TS)
        equipo = _generate_equipo(f"{prefix}-OB-{str(i + 1).zfill(3)}", rand)

        contratista_id = None if estado == "planeacion" else CONTRATISTAS[math.floor(rand() * len(CONTRATISTAS))]["id"]

        # Generate center and calles (simplified -- no street graph)
        calles = _generate_calles_afectadas(
            f"{prefix}-OB-{str(i + 1).zfill(3)}", estado, rand,
            colonia["center_lng"], colonia["center_lat"],
        )
        center_lng, center_lat = _jitter_coord(colonia["center_lng"], colonia["center_lat"], colonia["area_ha"], rand, factor=0.7)

        id_num = str(i + 1).zfill(3)
        obra_id = f"{prefix}-OB-{id_num}"
        folio = f"{prefix}-OBR-2026-{id_num}"

        duracion_dias = 30 + math.floor(rand() * 150)
        inicio_offset_dias = -120 + rand() * 90
        inicio_ms = NOW_MS + inicio_offset_dias * DAY_MS
        fin_ms = inicio_ms + duracion_dias * DAY_MS

        fecha_inicio = _ms_to_dt(inicio_ms)
        fecha_fin_estimada = _ms_to_dt(fin_ms)
        fecha_fin_real = _ms_to_dt(fin_ms - rand() * 12 * DAY_MS) if estado == "concluida" else None

        nombres = NOMBRES_OBRA[categoria]
        nombre = f"{nombres[math.floor(rand() * len(nombres))]} \u00b7 {colonia['nombre']}"
        avance_pct = _avance_por_estado(estado, rand)

        presupuesto = _generate_presupuesto(categoria, rand)
        timeline = _generate_obra_timeline(obra_id, estado, int(inicio_ms), int(fin_ms), responsable, rand)
        documentos = _generate_obra_documentos(obra_id, estado, int(inicio_ms), rand)
        evidencias = _generate_obra_evidencias(obra_id, estado, int(inicio_ms), rand)

        obras.append({
            "id": obra_id,
            "tenant_id": tenant_id,
            "folio": folio,
            "nombre": nombre,
            "descripcion": DESCRIPCIONES_OBRA[categoria],
            "categoria_id": categoria,
            "estado": estado,
            "prioridad": prioridad,
            "colonia_id": colonia["id"],
            "colonia_nombre": colonia["nombre"],
            "center_lng": center_lng,
            "center_lat": center_lat,
            "responsable_nombre": responsable["nombre"],
            "responsable_iniciales": responsable["iniciales"],
            "responsable_cargo": responsable["cargo"],
            "contratista_id": contratista_id,
            "fecha_inicio": fecha_inicio,
            "fecha_fin_estimada": fecha_fin_estimada,
            "fecha_fin_real": fecha_fin_real,
            "avance_pct": avance_pct,
            "presupuesto_autorizado": presupuesto["autorizado"],
            "presupuesto_ejercido": presupuesto["ejercido"],
            "presupuesto_items": presupuesto["items"],
            "equipo": equipo,
            "calles_afectadas": calles,
            "timeline": timeline,
            "documentos": documentos,
            "evidencias": evidencias,
        })

    return obras


# ═══════════════════════════════════════════════════════════════════════════
# Reporte <-> Obra linking  (exact port from reportes.ts)
# ═══════════════════════════════════════════════════════════════════════════

def link_reportes_to_obras(reportes: list[dict], obras: list[dict], seed: int) -> list[tuple[str, str]]:
    """Return list of (reporte_id, obra_id) links."""
    rand2 = mulberry32(seed + 7)
    ninety_days_ms = 90 * 24 * 3_600_000
    links: list[tuple[str, str]] = []

    for r in reportes:
        compat_cats = REPORTE_TO_OBRA_CATS.get(r["categoria_id"])
        if not compat_cats:
            continue
        r_ms = int(r["fecha_creacion"].timestamp() * 1000)
        candidates = [
            o for o in obras
            if o["colonia_id"] == r["colonia_id"]
            and o["categoria_id"] in compat_cats
            and abs(int(o["fecha_inicio"].timestamp() * 1000) - r_ms) < ninety_days_ms
        ]
        if not candidates:
            continue
        link_prob = (
            0.55 if r["estado"] in ("resuelto", "en_proceso")
            else 0.45 if r["peso"] >= 4
            else 0.25
        )
        if rand2() < link_prob:
            picked = candidates[math.floor(rand2() * len(candidates))]
            links.append((r["id"], picked["id"]))
            if len(candidates) > 1 and rand2() < 0.25:
                second = next((o for o in candidates if o["id"] != picked["id"]), None)
                if second:
                    links.append((r["id"], second["id"]))

    return links


# ═══════════════════════════════════════════════════════════════════════════
# Database seeding
# ═══════════════════════════════════════════════════════════════════════════

async def seed_all():
    """Connect to PostgreSQL and seed everything."""
    print(f"Connecting to: {DATABASE_URL.split('@')[-1] if '@' in DATABASE_URL else DATABASE_URL}")
    engine = create_async_engine(DATABASE_URL, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as session:
        # ── 1. Audit log immutability trigger ──────────────────────────────
        print("[1/11] Audit log immutability trigger...")
        await session.execute(text("""
            CREATE OR REPLACE FUNCTION prevent_audit_modification()
            RETURNS TRIGGER AS $$
            BEGIN
                RAISE EXCEPTION 'audit_logs table is append-only. UPDATE and DELETE are forbidden.';
                RETURN NULL;
            END;
            $$ LANGUAGE plpgsql;
        """))
        await session.execute(text("DROP TRIGGER IF EXISTS audit_logs_immutable ON audit_logs;"))
        await session.execute(text("""
            CREATE TRIGGER audit_logs_immutable
                BEFORE UPDATE OR DELETE ON audit_logs
                FOR EACH ROW EXECUTE FUNCTION prevent_audit_modification();
        """))
        await session.commit()

        # ── 2. Tenants ────────────────────────────────────────────────────
        print("[2/11] Seeding tenants...")
        for t in TENANTS:
            await session.execute(text("""
                INSERT INTO tenants (id, nombre, nombre_corto, clave_geo, acronimo,
                    bbox, center, polygon_path, escudo_path,
                    primario, secundario, dorado, poblacion, area_km2)
                VALUES (:id, :nombre, :nombre_corto, :clave_geo, :acronimo,
                    :bbox, :center, :polygon_path, :escudo_path,
                    :primario, :secundario, :dorado, :poblacion, :area_km2)
                ON CONFLICT (id) DO NOTHING
            """), {
                **{k: v for k, v in t.items() if k not in ("bbox", "center")},
                "bbox": t["bbox"],
                "center": t["center"],
            })
        await session.commit()
        print(f"         {len(TENANTS)} tenants")

        # ── 3. Categorias ─────────────────────────────────────────────────
        print("[3/11] Seeding categorias...")
        for cat in CATEGORIAS:
            await session.execute(text("""
                INSERT INTO categorias (id, label, color, icono, peso)
                VALUES (:id, :label, :color, :icono, :peso)
                ON CONFLICT (id) DO NOTHING
            """), cat)
        await session.commit()
        print(f"         {len(CATEGORIAS)} categorias")

        # ── 4. Obra categorias ────────────────────────────────────────────
        print("[4/11] Seeding obra_categorias...")
        for oc in OBRA_CATEGORIAS:
            await session.execute(text("""
                INSERT INTO obra_categorias (id, label, color, peso)
                VALUES (:id, :label, :color, :peso)
                ON CONFLICT (id) DO NOTHING
            """), oc)
        await session.commit()
        print(f"         {len(OBRA_CATEGORIAS)} obra categorias")

        # ── 5. Contratistas ───────────────────────────────────────────────
        print("[5/11] Seeding contratistas...")
        for ct in CONTRATISTAS:
            await session.execute(text("""
                INSERT INTO contratistas (id, razon_social, rfc, calificacion)
                VALUES (:id, :razon_social, :rfc, :calificacion)
                ON CONFLICT (id) DO NOTHING
            """), ct)
        await session.commit()
        print(f"         {len(CONTRATISTAS)} contratistas")

        # ── 6. Colonias ──────────────────────────────────────────────────
        print("[6/11] Seeding colonias...")
        for col in ALL_COLONIAS:
            await session.execute(text("""
                INSERT INTO colonias (id, tenant_id, nombre, tipo,
                    center_lng, center_lat, area_ha, poblacion, viviendas, densidad,
                    codigos_postales, servicio_agua, servicio_drenaje,
                    servicio_luz, servicio_internet, factor_reportes)
                VALUES (:id, :tenant_id, :nombre, :tipo,
                    :center_lng, :center_lat, :area_ha, :poblacion, :viviendas, :densidad,
                    :codigos_postales, :servicio_agua, :servicio_drenaje,
                    :servicio_luz, :servicio_internet, :factor_reportes)
                ON CONFLICT (id) DO NOTHING
            """), col)
        await session.commit()
        print(f"         {len(ALL_COLONIAS)} colonias ({len(COLONIAS_MC)} MC + {len(COLONIAS_TL)} TL)")

        # ── 7. Users ─────────────────────────────────────────────────────
        print("[7/11] Seeding users...")
        user_area_rows = []
        for u in USERS:
            # Por defecto "<id>.2026" (coincide con CREDENCIALES.md); si hay
            # SEED_DEMO_PASSWORD se usa esa contraseña compartida para todos.
            # Salt único; rounds=12 unificado con app/core/security.py. El
            # ON CONFLICT actualiza el hash para que un re-seed re-alinee las
            # credenciales documentadas (evita que queden desfasadas).
            password_plain = DEMO_PASSWORD_OVERRIDE or f"{u['id']}.2026"
            password_hash = _bcrypt.hashpw(
                password_plain.encode(), _bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
            ).decode()
            await session.execute(text("""
                INSERT INTO users (id, tenant_id, email, nombre, iniciales, cargo, role, avatar_tone, password_hash, is_active)
                VALUES (:id, :tenant_id, :email, :nombre, :iniciales, :cargo, :role, :avatar_tone, :password_hash, true)
                ON CONFLICT (id) DO UPDATE SET password_hash = EXCLUDED.password_hash
            """), {
                "id": u["id"],
                "tenant_id": u["tenant_id"],
                "email": u["email"],
                "nombre": u["nombre"],
                "iniciales": u["iniciales"],
                "cargo": u["cargo"],
                "role": u["role"],
                "avatar_tone": u["avatar_tone"],
                "password_hash": password_hash,
            })
            for area in u["areas"]:
                user_area_rows.append({"user_id": u["id"], "categoria_id": area})
        await session.commit()

        for row in user_area_rows:
            await session.execute(text("""
                INSERT INTO user_areas (user_id, categoria_id)
                VALUES (:user_id, :categoria_id)
                ON CONFLICT DO NOTHING
            """), row)
        await session.commit()
        print(f"         {len(USERS)} users, {len(user_area_rows)} user_areas")
        print(
            "         contraseña: "
            + ("SEED_DEMO_PASSWORD (compartida)" if DEMO_PASSWORD_OVERRIDE
               else "«<id>.2026» por usuario (ver CREDENCIALES.md)")
        )

        # ── 8. Cuadrillas ────────────────────────────────────────────────
        print("[8/11] Seeding cuadrillas...")
        cuadrilla_esp_rows = []
        tenant_prefixes = [("magdalena-contreras", "MC"), ("tlalpan", "TL")]
        cuadrilla_count = 0
        for tenant_id, prefix in tenant_prefixes:
            for c in CUADRILLAS:
                cuad_id = f"{prefix}-{c['id']}"
                await session.execute(text("""
                    INSERT INTO cuadrillas (id, tenant_id, nombre, integrantes)
                    VALUES (:id, :tenant_id, :nombre, :integrantes)
                    ON CONFLICT (id) DO NOTHING
                """), {
                    "id": cuad_id,
                    "tenant_id": tenant_id,
                    "nombre": c["nombre"],
                    "integrantes": c["integrantes"],
                })
                cuadrilla_count += 1
                for esp in c["especialidad"]:
                    cuadrilla_esp_rows.append({"cuadrilla_id": cuad_id, "categoria_id": esp})
        await session.commit()

        for row in cuadrilla_esp_rows:
            await session.execute(text("""
                INSERT INTO cuadrilla_especialidades (cuadrilla_id, categoria_id)
                VALUES (:cuadrilla_id, :categoria_id)
                ON CONFLICT DO NOTHING
            """), row)
        await session.commit()
        print(f"         {cuadrilla_count} cuadrillas, {len(cuadrilla_esp_rows)} especialidades")

        # ── 9. Obras ─────────────────────────────────────────────────────
        print("[9/11] Generating and seeding obras...")
        obras_mc = generate_obras_for_tenant("magdalena-contreras", OBRAS_SEED, OBRAS_TOTAL_MC)
        obras_tl = generate_obras_for_tenant("tlalpan", OBRAS_SEED + 11, OBRAS_TOTAL_TL)
        all_obras = obras_mc + obras_tl

        for o in all_obras:
            await session.execute(text("""
                INSERT INTO obras (id, tenant_id, folio, nombre, descripcion,
                    categoria_id, estado, prioridad,
                    colonia_id, colonia_nombre, center_lng, center_lat,
                    responsable_nombre, responsable_iniciales, responsable_cargo,
                    contratista_id, fecha_inicio, fecha_fin_estimada, fecha_fin_real,
                    avance_pct, presupuesto_autorizado, presupuesto_ejercido)
                VALUES (:id, :tenant_id, :folio, :nombre, :descripcion,
                    :categoria_id, :estado, :prioridad,
                    :colonia_id, :colonia_nombre, :center_lng, :center_lat,
                    :responsable_nombre, :responsable_iniciales, :responsable_cargo,
                    :contratista_id, :fecha_inicio, :fecha_fin_estimada, :fecha_fin_real,
                    :avance_pct, :presupuesto_autorizado, :presupuesto_ejercido)
                ON CONFLICT (id) DO NOTHING
            """), {
                "id": o["id"],
                "tenant_id": o["tenant_id"],
                "folio": o["folio"],
                "nombre": o["nombre"][:300],
                "descripcion": o["descripcion"],
                "categoria_id": o["categoria_id"],
                "estado": o["estado"],
                "prioridad": o["prioridad"],
                "colonia_id": o["colonia_id"],
                "colonia_nombre": o["colonia_nombre"],
                "center_lng": o["center_lng"],
                "center_lat": o["center_lat"],
                "responsable_nombre": o["responsable_nombre"],
                "responsable_iniciales": o["responsable_iniciales"],
                "responsable_cargo": o["responsable_cargo"],
                "contratista_id": o["contratista_id"],
                "fecha_inicio": o["fecha_inicio"],
                "fecha_fin_estimada": o["fecha_fin_estimada"],
                "fecha_fin_real": o["fecha_fin_real"],
                "avance_pct": o["avance_pct"],
                "presupuesto_autorizado": o["presupuesto_autorizado"],
                "presupuesto_ejercido": o["presupuesto_ejercido"],
            })

            # Presupuesto items (no natural PK -- guard against duplicates)
            existing = await session.execute(text(
                "SELECT 1 FROM obra_presupuesto_items WHERE obra_id = :oid LIMIT 1"
            ), {"oid": o["id"]})
            if existing.first() is None:
                for pi in o["presupuesto_items"]:
                    await session.execute(text("""
                        INSERT INTO obra_presupuesto_items (obra_id, concepto, unidad, cantidad, precio_unitario, importe)
                        VALUES (:obra_id, :concepto, :unidad, :cantidad, :precio_unitario, :importe)
                    """), {
                        "obra_id": o["id"],
                        "concepto": pi["concepto"],
                        "unidad": pi["unidad"],
                        "cantidad": pi["cantidad"],
                        "precio_unitario": pi["precio_unitario"],
                        "importe": pi["importe"],
                    })

            # Equipo
            for eq in o["equipo"]:
                await session.execute(text("""
                    INSERT INTO obra_equipo (id, obra_id, nombre, iniciales, rol, contacto)
                    VALUES (:id, :obra_id, :nombre, :iniciales, :rol, :contacto)
                    ON CONFLICT (id) DO NOTHING
                """), eq)

            # Calles afectadas
            for ca in o["calles_afectadas"]:
                await session.execute(text("""
                    INSERT INTO obra_calles_afectadas (id, obra_id, nombre, estado, coordenadas, fecha_inicio, fecha_fin_estimada, alternativas_viales)
                    VALUES (:id, :obra_id, :nombre, :estado, CAST(:coordenadas AS jsonb), :fecha_inicio, :fecha_fin_estimada, :alternativas_viales)
                    ON CONFLICT (id) DO NOTHING
                """), ca)

            # Timeline
            for te in o["timeline"]:
                await session.execute(text("""
                    INSERT INTO obra_timeline (id, obra_id, fecha, tipo, titulo, descripcion, autor_nombre, autor_iniciales, autor_rol)
                    VALUES (:id, :obra_id, :fecha, :tipo, :titulo, :descripcion, :autor_nombre, :autor_iniciales, :autor_rol)
                    ON CONFLICT (id) DO NOTHING
                """), te)

            # Documentos
            for doc in o["documentos"]:
                await session.execute(text("""
                    INSERT INTO obra_documentos (id, obra_id, nombre, tipo, tamano_kb, fecha_subida, autor)
                    VALUES (:id, :obra_id, :nombre, :tipo, :tamano_kb, :fecha_subida, :autor)
                    ON CONFLICT (id) DO NOTHING
                """), doc)

            # Evidencias
            for ev in o["evidencias"]:
                await session.execute(text("""
                    INSERT INTO obra_evidencias (id, obra_id, url, caption, fecha, autor, tipo)
                    VALUES (:id, :obra_id, :url, :caption, :fecha, :autor, :tipo)
                    ON CONFLICT (id) DO NOTHING
                """), ev)

        await session.commit()
        print(f"         {len(all_obras)} obras ({len(obras_mc)} MC + {len(obras_tl)} TL)")

        # ── 9b. Compromisos de gobierno ───────────────────────────────────
        print("[9b]  Seeding compromisos de gobierno...")
        n_compromisos = 0
        for t in TENANTS:
            prefix = "MC" if t["id"] == "magdalena-contreras" else "TL"
            for idx, c in enumerate(COMPROMISOS_BASE):
                cid = f"{prefix}-CMP-{str(idx + 1).zfill(2)}"
                fecha_objetivo = _ms_to_dt(NOW_MS + c["dias_objetivo"] * DAY_MS)
                await session.execute(text("""
                    INSERT INTO compromisos (id, tenant_id, titulo, descripcion,
                        area_id, meta, avance_pct, estado, fecha_objetivo)
                    VALUES (:id, :tenant_id, :titulo, :descripcion,
                        :area_id, :meta, :avance_pct, :estado, :fecha_objetivo)
                    ON CONFLICT (id) DO NOTHING
                """), {
                    "id": cid,
                    "tenant_id": t["id"],
                    "titulo": c["titulo"][:200],
                    "descripcion": c["descripcion"],
                    "area_id": c["area_id"],
                    "meta": c["meta"][:300] if c["meta"] else None,
                    "avance_pct": c["avance_pct"],
                    "estado": c["estado"],
                    "fecha_objetivo": fecha_objetivo,
                })
                n_compromisos += 1
        await session.commit()
        print(f"         {n_compromisos} compromisos ({len(COMPROMISOS_BASE)} por tenant)")

        # ── 9b-2. Trámites y servicios (catálogo público) ─────────────────────
        import json as _json_tramites
        print("[9b-2] Seeding trámites y servicios...")
        n_tramites = 0
        for t in TENANTS:
            prefix = "MC" if t["id"] == "magdalena-contreras" else "TL"
            for idx, tr in enumerate(TRAMITES_BASE):
                tid = f"{prefix}-TRM-{str(idx + 1).zfill(2)}"
                dependencia = f"{tr['dependencia']} · {t['nombre_corto']}"
                await session.execute(text("""
                    INSERT INTO tramites (id, tenant_id, nombre, dependencia, area_id,
                        descripcion, requisitos, costo, tiempo_estimado, vigencia,
                        documentos, donde_acudir, horarios)
                    VALUES (:id, :tenant_id, :nombre, :dependencia, :area_id,
                        :descripcion, CAST(:requisitos AS jsonb), :costo, :tiempo_estimado,
                        :vigencia, CAST(:documentos AS jsonb), :donde_acudir, :horarios)
                    ON CONFLICT (id) DO NOTHING
                """), {
                    "id": tid,
                    "tenant_id": t["id"],
                    "nombre": tr["nombre"][:200],
                    "dependencia": dependencia[:160],
                    "area_id": tr.get("area_id"),
                    "descripcion": tr.get("descripcion"),
                    "requisitos": _json_tramites.dumps(tr.get("requisitos", [])),
                    "costo": tr.get("costo"),
                    "tiempo_estimado": tr.get("tiempo_estimado"),
                    "vigencia": tr.get("vigencia"),
                    "documentos": _json_tramites.dumps(tr.get("documentos", [])),
                    "donde_acudir": (tr.get("donde_acudir") or None),
                    "horarios": tr.get("horarios"),
                })
                n_tramites += 1
        await session.commit()
        print(f"         {n_tramites} trámites ({len(TRAMITES_BASE)} por tenant)")

        # ── 9b-3. Avisos y campañas institucionales ───────────────────────────
        print("[9b-3] Seeding avisos y campañas...")
        n_avisos = 0
        for t in TENANTS:
            prefix = "MC" if t["id"] == "magdalena-contreras" else "TL"
            for idx, av in enumerate(AVISOS_BASE):
                aid = f"{prefix}-AVI-{str(idx + 1).zfill(2)}"
                fecha = _ms_to_dt(NOW_MS + av["dias_offset"] * DAY_MS)
                await session.execute(text("""
                    INSERT INTO avisos (id, tenant_id, titulo, cuerpo, tipo, area_id,
                        segmento, fecha, activo)
                    VALUES (:id, :tenant_id, :titulo, :cuerpo, :tipo, :area_id,
                        :segmento, :fecha, :activo)
                    ON CONFLICT (id) DO NOTHING
                """), {
                    "id": aid,
                    "tenant_id": t["id"],
                    "titulo": av["titulo"][:200],
                    "cuerpo": av["cuerpo"],
                    "tipo": av["tipo"],
                    "area_id": av.get("area_id"),
                    "segmento": (av.get("segmento") or None),
                    "fecha": fecha,
                    "activo": av.get("activo", True),
                })
                n_avisos += 1
        await session.commit()
        print(f"         {n_avisos} avisos ({len(AVISOS_BASE)} por tenant)")

        # ── 9c. tipo_afectacion en calles afectadas (backfill determinista) ──
        print("[9c]  Asignando tipo_afectacion a calles afectadas...")
        n_calles_afect = 0
        for from_estado, tipo in CIERRE_TO_TIPO_AFECTACION.items():
            res = await session.execute(text("""
                UPDATE obra_calles_afectadas
                SET tipo_afectacion = :tipo
                WHERE estado = :estado AND tipo_afectacion IS NULL
            """), {"tipo": tipo, "estado": from_estado})
            n_calles_afect += res.rowcount or 0
        # Cualquier calle restante sin mapeo conocido -> 'parcial' (determinista).
        res = await session.execute(text("""
            UPDATE obra_calles_afectadas
            SET tipo_afectacion = 'parcial'
            WHERE tipo_afectacion IS NULL
        """))
        n_calles_afect += res.rowcount or 0
        await session.commit()
        print(f"         {n_calles_afect} calles afectadas con tipo_afectacion")

        # ── 10. Reportes ──────────────────────────────────────────────────
        print("[10/11] Generating and seeding reportes...")
        reportes_mc = generate_reportes_for_tenant("magdalena-contreras", REPORTES_SEED, REPORTES_TOTAL_MC)
        reportes_tl = generate_reportes_for_tenant("tlalpan", REPORTES_SEED + 31, REPORTES_TOTAL_TL)
        all_reportes = reportes_mc + reportes_tl

        for r in all_reportes:
            await session.execute(text("""
                INSERT INTO reportes (id, tenant_id, folio, categoria_id, estado, prioridad, fuente,
                    cuadrilla_id, colonia_id, colonia_nombre, lng, lat, peso,
                    titulo, descripcion, ciudadano_nombre, ciudadano_iniciales,
                    fecha_creacion, fecha_actualizacion, fecha_cierre,
                    tiempo_atencion_horas, costo_estimado, gasto_real)
                VALUES (:id, :tenant_id, :folio, :categoria_id, :estado, :prioridad, :fuente,
                    :cuadrilla_id, :colonia_id, :colonia_nombre, :lng, :lat, :peso,
                    :titulo, :descripcion, :ciudadano_nombre, :ciudadano_iniciales,
                    :fecha_creacion, :fecha_actualizacion, :fecha_cierre,
                    :tiempo_atencion_horas, :costo_estimado, :gasto_real)
                ON CONFLICT (id) DO NOTHING
            """), {
                "id": r["id"],
                "tenant_id": r["tenant_id"],
                "folio": r["folio"],
                "categoria_id": r["categoria_id"],
                "estado": r["estado"],
                "prioridad": r["prioridad"],
                "fuente": r["fuente"],
                "cuadrilla_id": r["cuadrilla_id"],
                "colonia_id": r["colonia_id"],
                "colonia_nombre": r["colonia_nombre"],
                "lng": r["lng"],
                "lat": r["lat"],
                "peso": r["peso"],
                "titulo": r["titulo"],
                "descripcion": r["descripcion"],
                "ciudadano_nombre": r["ciudadano_nombre"],
                "ciudadano_iniciales": r["ciudadano_iniciales"],
                "fecha_creacion": r["fecha_creacion"],
                "fecha_actualizacion": r["fecha_actualizacion"],
                "fecha_cierre": r["fecha_cierre"],
                "tiempo_atencion_horas": r["tiempo_atencion_horas"],
                "costo_estimado": r["costo_estimado"],
                "gasto_real": r["gasto_real"],
            })

            # Evidencias
            for ev in r["evidencias"]:
                await session.execute(text("""
                    INSERT INTO reporte_evidencias (id, reporte_id, url, caption, fecha, autor, tipo)
                    VALUES (:id, :reporte_id, :url, :caption, :fecha, :autor, :tipo)
                    ON CONFLICT (id) DO NOTHING
                """), {"reporte_id": r["id"], **ev})

            # Timeline events
            for te in r["timeline"]:
                await session.execute(text("""
                    INSERT INTO reporte_eventos (id, reporte_id, fecha, tipo, titulo, descripcion, autor_nombre, autor_iniciales, autor_rol)
                    VALUES (:id, :reporte_id, :fecha, :tipo, :titulo, :descripcion, :autor_nombre, :autor_iniciales, :autor_rol)
                    ON CONFLICT (id) DO NOTHING
                """), {"reporte_id": r["id"], **te})

        await session.commit()
        print(f"         {len(all_reportes)} reportes ({len(reportes_mc)} MC + {len(reportes_tl)} TL)")

        # ── Reporte-Obra links ────────────────────────────────────────────
        print("         Linking reportes to obras...")
        links_mc = link_reportes_to_obras(reportes_mc, obras_mc, REPORTES_SEED)
        links_tl = link_reportes_to_obras(reportes_tl, obras_tl, REPORTES_SEED + 31)
        all_links = links_mc + links_tl

        for reporte_id, obra_id in all_links:
            await session.execute(text("""
                INSERT INTO reporte_obra_relaciones (reporte_id, obra_id)
                VALUES (:reporte_id, :obra_id)
                ON CONFLICT DO NOTHING
            """), {"reporte_id": reporte_id, "obra_id": obra_id})
        await session.commit()
        print(f"         {len(all_links)} reporte-obra links")

        # ── 11. Notificaciones ────────────────────────────────────────────
        print("[11/11] Generating and seeding notificaciones...")
        all_notifs = generate_notificaciones(USERS, all_reportes, all_obras)
        for n in all_notifs:
            await session.execute(text("""
                INSERT INTO notificaciones (id, user_id, tenant_id, tipo, titulo, cuerpo,
                    href, entity_type, entity_id, leida, fecha)
                VALUES (:id, :user_id, :tenant_id, :tipo, :titulo, :cuerpo,
                    :href, :entity_type, :entity_id, false, :fecha)
                ON CONFLICT (id) DO NOTHING
            """), n)
        await session.commit()
        print(f"         {len(all_notifs)} notificaciones")

        # ── 12. Campo (integrantes, turnos, tareas, ubicaciones) ──────────────
        print("[12/12] Seeding módulo de campo (monitor en vivo)...")
        await seed_campo(session, all_reportes)

        # ── 13. Fase 6 (carry-over de jornada + documentos versionados) ───────
        await seed_fase6(session)

        # ── 14. Edad realista de reportes abiertos (indicador SLA creíble) ────
        await reajustar_reportes_abiertos(session)

    await engine.dispose()
    print("\nSeed complete.")


# ═══════════════════════════════════════════════════════════════════════════
# Notificaciones generator
# Materialises the SLA / new-report / obra-closure rules that the frontend bell
# used to compute client-side, but per-user and scoped to each user's tenant +
# areas (admins see everything in their tenant; directors only their areas).
# ═══════════════════════════════════════════════════════════════════════════

# director areas -> obra categories they may also see
# (kept in sync with app/services/reporte_service.py and obra_service.py)
CATEGORIA_TO_OBRA_NOTIF = {
    "bacheo": ["pavimentacion", "vialidad"],
    "alumbrado": ["alumbrado"],
    "limpia": ["imagen_urbana"],
    "seguridad": [],
    "agua": ["agua_potable", "drenaje"],
    "parques": ["parques"],
    "arboles": ["parques"],
    "drenaje": ["drenaje"],
    "semaforos": ["vialidad"],
    "comercio_vp": ["imagen_urbana"],
}


def generate_notificaciones(users: list[dict], all_reportes: list[dict], all_obras: list[dict]) -> list[dict]:
    """Build up to 10 notifications per user, mirroring the frontend bell logic."""
    notifs: list[dict] = []

    for u in users:
        tenant_id = u["tenant_id"]
        is_admin = u["role"] == "admin" or not u["areas"]
        areas = set(u["areas"])
        obra_cats: set[str] = set()
        for a in u["areas"]:
            obra_cats.update(CATEGORIA_TO_OBRA_NOTIF.get(a, []))

        # Visible items for this user, preserving generation order
        vis_reportes = [
            r for r in all_reportes
            if r["tenant_id"] == tenant_id and (is_admin or r["categoria_id"] in areas)
        ]
        vis_obras = [
            o for o in all_obras
            if o["tenant_id"] == tenant_id and (is_admin or o["categoria_id"] in obra_cats)
        ]

        user_notifs: list[dict] = []

        # 1. SLA alerts (up to 4): unattended high/critical reports
        alert_count = 0
        for r in vis_reportes[:80]:
            if r["estado"] in ("nuevo", "asignado") and r["prioridad"] in ("critica", "alta"):
                titulo = (
                    "Reporte crítico sin atender"
                    if r["prioridad"] == "critica"
                    else "Reporte de alta prioridad sin atender"
                )
                user_notifs.append({
                    "id": f"{u['id']}-sla-{r['id']}",
                    "tipo": "alerta",
                    "titulo": titulo,
                    "cuerpo": f"{r['titulo']} · {r['colonia_nombre']}",
                    "href": f"/backoffice/reportes/{r['id']}",
                    "entity_type": "reporte",
                    "entity_id": r["id"],
                    "fecha": r["fecha_creacion"],
                })
                alert_count += 1
                if alert_count >= 4:
                    break

        # 2. New reports (first 3)
        for r in vis_reportes[:3]:
            user_notifs.append({
                "id": f"{u['id']}-nuevo-{r['id']}",
                "tipo": "reporte",
                "titulo": "Nuevo reporte recibido",
                "cuerpo": f"{r['titulo']} · {r['colonia_nombre']}",
                "href": f"/backoffice/reportes/{r['id']}",
                "entity_type": "reporte",
                "entity_id": r["id"],
                "fecha": r["fecha_creacion"],
            })

        # 3. Obra closures (up to 3)
        cierres = [o for o in vis_obras if o["estado"] in ("concluida", "en_cierre")][:3]
        for o in cierres:
            concluida = o["estado"] == "concluida"
            user_notifs.append({
                "id": f"{u['id']}-obra-{o['id']}",
                "tipo": "cierre" if concluida else "obra",
                "titulo": "Obra concluida" if concluida else "Obra entrando en cierre",
                "cuerpo": o["nombre"],
                "href": f"/backoffice/obras/{o['id']}",
                "entity_type": "obra",
                "entity_id": o["id"],
                "fecha": o["fecha_fin_real"] or o["fecha_inicio"],
            })

        # 4. Newest first, keep top 10
        user_notifs.sort(key=lambda n: n["fecha"], reverse=True)
        for n in user_notifs[:10]:
            notifs.append({**n, "user_id": u["id"], "tenant_id": tenant_id})

    return notifs


# ═══════════════════════════════════════════════════════════════════════════
# Campo (Fase 2): integrantes, turnos, tareas, ubicaciones
# Da "vida" al monitor en vivo de cuadrillas. Idempotente: si ya existen
# integrantes para los tenants, se omite todo el bloque.
# ═══════════════════════════════════════════════════════════════════════════

# Nombres completos para la nómina de campo (jefes + operarios).
INTEGRANTE_NOMBRES = [
    "Ricardo Ñúñez Saldaña", "Gerardo Peña Olvera", "Marcos Toledo Rey",
    "Efraín Castro Lima", "Ismael Vera Pacheco", "Joaquín Mora Reyes",
    "Abel Ruíz Tovar", "Saúl Medina Cano", "Raúl Ibarra Vela",
    "Osêr Tapia Luna", "Felipe Acosta Rico", "Gerónimo Salas Mejía",
    "Damián Rosales Cruz", "Mateo Fuentes Gil", "Bruno Aguilar Soto",
    "Nicolás Herrera Paz", "Teodoro Lara Vidal", "Emiliano Cuevas Roa",
    "Bernardo Gil Anaya", "Aarón Ramos Cid", "Lorenzo Vega Rubio",
    "Genaro Muñoz Real", "Cipriano Díaz Lugo", "Salvador Nava Pino",
]

# Pasos de checklist por categoría de reporte (operación de campo realista).
CHECKLIST_POR_CATEGORIA = {
    "bacheo":      ["Acordonar área de trabajo", "Retirar material suelto", "Aplicar mezcla asfáltica", "Compactar y liberar vialidad"],
    "alumbrado":   ["Verificar tablero eléctrico", "Reemplazar luminaria", "Probar encendido", "Registrar folio cerrado"],
    "limpia":      ["Cargar residuos al camión", "Barrer y limpiar el punto", "Verificar disposición final"],
    "seguridad":   ["Inspeccionar la zona", "Levantar evidencia fotográfica", "Coordinar con SSC-CDMX", "Reportar a base"],
    "agua":        ["Cerrar válvula de paso", "Reparar fuga", "Restablecer suministro", "Probar presión"],
    "parques":     ["Evaluar mobiliario dañado", "Reparar o reemplazar", "Limpiar el área", "Cierre con foto"],
    "arboles":     ["Acordonar perímetro", "Realizar poda certificada", "Retirar ramas", "Liberar paso peatonal"],
    "drenaje":     ["Destapar coladera", "Desazolvar registro", "Verificar flujo", "Cerrar el reporte"],
    "semaforos":   ["Diagnosticar el equipo", "Reparar o reprogramar", "Probar fases", "Liberar el cruce"],
    "comercio_vp": ["Notificar al comerciante", "Levantar acta de inspección", "Despejar la vía", "Registrar resultado"],
}
CHECKLIST_DEFAULT = ["Llegar al sitio", "Atender la incidencia", "Registrar evidencia", "Cerrar la tarea"]

# Estados de tarea de campo asignados ciclicamente a la muestra de reportes.
TAREA_ESTADOS = ["pendiente", "en_ruta", "en_sitio"]


def _campo_rand(seed: int):
    return mulberry32(seed)


def _telefono(rand) -> str:
    return "55" + "".join(str(math.floor(rand() * 10)) for _ in range(8))


def _checklist_for(categoria_id: str, n_pasos: int) -> list[dict]:
    pasos = CHECKLIST_POR_CATEGORIA.get(categoria_id, CHECKLIST_DEFAULT)
    pasos = pasos[:n_pasos] if len(pasos) >= n_pasos else pasos
    return [{"paso": p, "hecho": False} for p in pasos]


async def seed_campo(session, all_reportes: list[dict]) -> None:
    """Siembra datos de campo (Fase 2) para el monitor en vivo.

    Idempotente: si ya hay integrantes sembrados, no hace nada.
    """
    import json
    import uuid as _uuid

    existing = await session.execute(text("SELECT count(*) FROM integrantes"))
    if (existing.scalar() or 0) > 0:
        print("         integrantes ya existen, se omite el seed de campo.")
        return

    rand = _campo_rand(20260618)

    # Cuadrillas reales de la DB (id, tenant_id).
    cuad_rows = (await session.execute(
        text("SELECT id, tenant_id FROM cuadrillas ORDER BY tenant_id, id")
    )).fetchall()

    # Jefes de cuadrilla disponibles por tenant (para vincular user_id).
    jefe_rows = (await session.execute(
        text("SELECT id, tenant_id FROM users WHERE role = 'jefe_cuadrilla'")
    )).fetchall()
    jefes_por_tenant: dict[str, list[str]] = {}
    for uid, tid in jefe_rows:
        jefes_por_tenant.setdefault(tid, []).append(uid)

    n_integrantes = n_turnos = n_tareas = n_ubic = 0
    nombre_idx = 0
    # Integrante "jefe" por cuadrilla, para asociar tareas/ubicaciones.
    jefe_integrante_por_cuad: dict[str, str] = {}
    # Para colocar ubicaciones cerca de las tareas reales.
    coords_por_cuad: dict[str, list[tuple[float, float]]] = {}

    # ── Integrantes: 3-5 por cuadrilla (1 jefe) ───────────────────────────────
    for idx, (cuad_id, tenant_id) in enumerate(cuad_rows):
        total = 3 + math.floor(rand() * 3)  # 3..5
        jefe_user_id = None
        # El primer cuadrilla de cada tenant vincula al user jefe_cuadrilla real.
        jefes = jefes_por_tenant.get(tenant_id, [])
        if jefes and idx % 8 == 1:  # una cuadrilla por tenant lleva la cuenta real
            jefe_user_id = jefes[0]
        for j in range(total):
            es_jefe = j == 0
            nombre = INTEGRANTE_NOMBRES[nombre_idx % len(INTEGRANTE_NOMBRES)]
            nombre_idx += 1
            iid = str(_uuid.uuid4())
            if es_jefe:
                jefe_integrante_por_cuad[cuad_id] = iid
            await session.execute(text("""
                INSERT INTO integrantes (id, cuadrilla_id, tenant_id, user_id, nombre, rol_campo, telefono, activo)
                VALUES (:id, :cuadrilla_id, :tenant_id, :user_id, :nombre, :rol_campo, :telefono, true)
                ON CONFLICT (id) DO NOTHING
            """), {
                "id": iid,
                "cuadrilla_id": cuad_id,
                "tenant_id": tenant_id,
                "user_id": jefe_user_id if es_jefe else None,
                "nombre": nombre,
                "rol_campo": "jefe" if es_jefe else "integrante",
                "telefono": _telefono(rand),
            })
            n_integrantes += 1

    # ── Turnos abiertos para ~la mitad de las cuadrillas ──────────────────────
    cuadrillas_activas: list[tuple[str, str]] = []
    for idx, (cuad_id, tenant_id) in enumerate(cuad_rows):
        if idx % 2 == 0:  # ~la mitad
            cuadrillas_activas.append((cuad_id, tenant_id))
            await session.execute(text("""
                INSERT INTO turnos (id, tenant_id, cuadrilla_id, inicio, fin, estado)
                VALUES (:id, :tenant_id, :cuadrilla_id, :inicio, NULL, 'abierto')
                ON CONFLICT (id) DO NOTHING
            """), {
                "id": str(_uuid.uuid4()),
                "tenant_id": tenant_id,
                "cuadrilla_id": cuad_id,
                # Inicio hace 2-6 horas (referido a NOW del seed).
                "inicio": _ms_to_dt(NOW_MS - round((2 + rand() * 4) * 3_600_000)),
            })
            n_turnos += 1

    # ── Tareas: muestra de reportes asignados/en proceso con cuadrilla ────────
    rep_rows = (await session.execute(text("""
        SELECT id, tenant_id, cuadrilla_id, categoria_id, titulo, lat, lng, colonia_id, prioridad
        FROM reportes
        WHERE cuadrilla_id IS NOT NULL AND estado IN ('asignado', 'en_proceso')
        ORDER BY fecha_creacion DESC
        LIMIT 50
    """))).fetchall()

    for i, (rid, tenant_id, cuad_id, categoria_id, titulo, lat, lng, colonia_id, prioridad) in enumerate(rep_rows):
        estado = TAREA_ESTADOS[i % len(TAREA_ESTADOS)]
        n_pasos = 3 + (i % 2)  # 3 o 4 pasos
        checklist = _checklist_for(categoria_id, n_pasos)
        # En tareas en_sitio, marca algunos pasos como hechos.
        if estado == "en_sitio" and checklist:
            checklist[0]["hecho"] = True
        integrante_id = jefe_integrante_por_cuad.get(cuad_id)
        await session.execute(text("""
            INSERT INTO tareas (id, tenant_id, cuadrilla_id, integrante_id, origen_tipo,
                reporte_id, obra_id, titulo, descripcion, prioridad, estado, orden_ruta,
                lat, lng, colonia_id, instrucciones, checklist)
            VALUES (:id, :tenant_id, :cuadrilla_id, :integrante_id, 'reporte',
                :reporte_id, NULL, :titulo, NULL, :prioridad, :estado, :orden_ruta,
                :lat, :lng, :colonia_id, :instrucciones, CAST(:checklist AS jsonb))
            ON CONFLICT (id) DO NOTHING
        """), {
            "id": str(_uuid.uuid4()),
            "tenant_id": tenant_id,
            "cuadrilla_id": cuad_id,
            "integrante_id": integrante_id,
            "reporte_id": rid,
            "titulo": (titulo or "Tarea de campo")[:200],
            "prioridad": prioridad or "media",
            "estado": estado,
            "orden_ruta": (i % 6) + 1,
            "lat": lat,
            "lng": lng,
            "colonia_id": colonia_id,
            "instrucciones": "Atender en sitio y documentar con evidencia antes/después.",
            "checklist": json.dumps(checklist),
        })
        n_tareas += 1
        if lat is not None and lng is not None:
            coords_por_cuad.setdefault(cuad_id, []).append((float(lat), float(lng)))

    # ── Ubicaciones: 2-3 pines recientes por cuadrilla activa ─────────────────
    for cuad_id, tenant_id in cuadrillas_activas:
        coords = coords_por_cuad.get(cuad_id)
        # Centro de referencia: cerca de una tarea de la cuadrilla, si existe.
        if coords:
            base_lat, base_lng = coords[0]
        else:
            # Sin tareas: usa el centro del tenant.
            base_lng, base_lat = next(
                (t["center"] for t in TENANTS if t["id"] == tenant_id),
                (-99.21, 19.27),
            )
        n_pines = 2 + math.floor(rand() * 2)  # 2..3
        integrante_id = jefe_integrante_por_cuad.get(cuad_id)
        for k in range(n_pines):
            jlat = base_lat + (rand() - 0.5) * 0.004
            jlng = base_lng + (rand() - 0.5) * 0.004
            await session.execute(text("""
                INSERT INTO ubicaciones (id, tenant_id, cuadrilla_id, integrante_id, lat, lng, timestamp)
                VALUES (:id, :tenant_id, :cuadrilla_id, :integrante_id, :lat, :lng, :ts)
                ON CONFLICT (id) DO NOTHING
            """), {
                "id": str(_uuid.uuid4()),
                "tenant_id": tenant_id,
                "cuadrilla_id": cuad_id,
                "integrante_id": integrante_id,
                "lat": jlat,
                "lng": jlng,
                # Pines de los últimos ~30 min (más reciente con k mayor).
                "ts": _ms_to_dt(NOW_MS - round((n_pines - k) * (5 + rand() * 5) * 60_000)),
            })
            n_ubic += 1

    await session.commit()
    print(
        f"         {n_integrantes} integrantes, {n_turnos} turnos, "
        f"{n_tareas} tareas, {n_ubic} ubicaciones"
    )


async def seed_fase6(session) -> None:
    """Siembra carry-over de jornada (REQ-07) y documentos versionados (REQ-04).

    Idempotente e independiente del guard de ``seed_campo``: usa ids fijos con
    ``ON CONFLICT DO NOTHING`` para poder correr aunque el resto ya esté sembrado.
    """
    print("[13/13] Seeding Fase 6 (carry-over + documentos)...")

    cuad_rows = (await session.execute(
        text("SELECT id, tenant_id FROM cuadrillas ORDER BY tenant_id, id")
    )).fetchall()
    jefe_rows = (await session.execute(
        text("SELECT DISTINCT ON (cuadrilla_id) cuadrilla_id, id FROM integrantes "
             "ORDER BY cuadrilla_id, id")
    )).fetchall()
    jefe_por_cuad = {cid: iid for cid, iid in jefe_rows}

    # ── Carry-over: una cadena arrastrada por tenant ──────────────────────────
    n_carry = 0
    cuad_por_tenant: dict[str, str] = {}
    for cuad_id, tenant_id in cuad_rows:
        cuad_por_tenant.setdefault(tenant_id, cuad_id)
    for tenant_id, cuad_id in cuad_por_tenant.items():
        orig_id = f"seed-carry-{tenant_id}-orig"
        cont_id = f"seed-carry-{tenant_id}-cont"
        integrante_id = jefe_por_cuad.get(cuad_id)
        titulo = "Reparación mayor de socavón (multi-jornada)"
        await session.execute(text("""
            INSERT INTO tareas (id, tenant_id, cuadrilla_id, integrante_id, origen_tipo,
                titulo, prioridad, estado, orden_ruta, instrucciones, checklist, intento_n)
            VALUES (:id, :tenant_id, :cuadrilla_id, :integrante_id, 'manual',
                :titulo, 'alta', 'en_ruta', 1, 'Trabajo no concluido en jornada previa.',
                '[]'::jsonb, 2)
            ON CONFLICT (id) DO NOTHING
        """), {
            "id": orig_id, "tenant_id": tenant_id, "cuadrilla_id": cuad_id,
            "integrante_id": integrante_id, "titulo": titulo,
        })
        await session.execute(text("""
            INSERT INTO tareas (id, tenant_id, cuadrilla_id, integrante_id, origen_tipo,
                titulo, prioridad, estado, orden_ruta, instrucciones, checklist,
                carry_over_de, intento_n)
            VALUES (:id, :tenant_id, :cuadrilla_id, :integrante_id, 'manual',
                :titulo, 'alta', 'pendiente', 1, 'Arrastrada de la jornada anterior.',
                '[]'::jsonb, :carry, 3)
            ON CONFLICT (id) DO NOTHING
        """), {
            "id": cont_id, "tenant_id": tenant_id, "cuadrilla_id": cuad_id,
            "integrante_id": integrante_id, "titulo": titulo, "carry": orig_id,
        })
        n_carry += 1

    # ── Documentos versionados del repositorio ────────────────────────────────
    admin_rows = (await session.execute(
        text("SELECT tenant_id, id FROM users WHERE role = 'admin'")
    )).fetchall()
    admin_por_tenant = {tid: uid for tid, uid in admin_rows}
    DOC_SAMPLES = [
        ("Convenio de colaboración interinstitucional 2026", "convenio"),
        ("Expediente técnico de obra — repavimentación", "obra"),
        ("Acta de entrega-recepción de obra", "acta"),
        ("Reglamento interno de operación de cuadrillas", "norma"),
        ("Manual de imagen institucional", "norma"),
    ]
    _INS_DOC = text("""
        INSERT INTO archivos (id, tenant_id, nombre, content_type, size_bytes,
            storage_key, url, categoria, entity_type, entity_id, version,
            reemplaza_a, es_actual, created_by)
        VALUES (:id,:tenant_id,:nombre,'application/pdf',:size,:key,:url,
            'documento',:etype,NULL,:version,:prev,:actual,:creador)
        ON CONFLICT (id) DO NOTHING
    """)
    n_docs = 0
    for tenant_id in [tid for tid, _ in cuad_por_tenant.items()] or [
        t["id"] for t in TENANTS
    ]:
        creador = admin_por_tenant.get(tenant_id)
        for j, (nombre, kind) in enumerate(DOC_SAMPLES):
            size = 80_000 + j * 45_000
            if j == 0:
                v1, v2 = f"seed-doc-{tenant_id}-{j}-v1", f"seed-doc-{tenant_id}-{j}-v2"
                await session.execute(_INS_DOC, {
                    "id": v1, "tenant_id": tenant_id, "nombre": nombre, "size": size,
                    "key": f"{tenant_id}/{v1}.pdf", "url": f"/uploads/{tenant_id}/{v1}.pdf",
                    "etype": kind, "version": 1, "prev": None, "actual": False,
                    "creador": creador,
                })
                await session.execute(_INS_DOC, {
                    "id": v2, "tenant_id": tenant_id, "nombre": nombre,
                    "size": size + 12_000,
                    "key": f"{tenant_id}/{v2}.pdf", "url": f"/uploads/{tenant_id}/{v2}.pdf",
                    "etype": kind, "version": 2, "prev": v1, "actual": True,
                    "creador": creador,
                })
            else:
                vid = f"seed-doc-{tenant_id}-{j}"
                await session.execute(_INS_DOC, {
                    "id": vid, "tenant_id": tenant_id, "nombre": nombre, "size": size,
                    "key": f"{tenant_id}/{vid}.pdf", "url": f"/uploads/{tenant_id}/{vid}.pdf",
                    "etype": kind, "version": 1, "prev": None, "actual": True,
                    "creador": creador,
                })
            n_docs += 1

    await session.commit()
    print(f"         {n_carry} cadenas carry-over, {n_docs} documentos")


async def reajustar_reportes_abiertos(session) -> None:
    """Reacomoda la EDAD de los reportes abiertos a una distribución realista
    (sesgada a reciente, ventana ~16 días), anclada al 'hoy' del dataset.

    Sin esto, los reportes abiertos del seed quedan demasiado viejos respecto a la
    línea de tiempo congelada y el indicador 'En riesgo de SLA' marca a casi todos
    los activos. Con el reacomodo, sólo un subconjunto creíble (~25%) rebasa su
    SLA. Determinista por id (md5) → idempotente; ancla a max(fecha) de los
    reportes ya cerrados, que no se tocan, para ser estable entre corridas.
    """
    res = await session.execute(text("""
        WITH hoy AS (
            SELECT tenant_id, max(fecha_creacion) AS t
            FROM reportes WHERE estado IN ('resuelto','cerrado') GROUP BY tenant_id
        ),
        calc AS (
            SELECT r.id, r.estado, h.t AS hoy,
                h.t - (power(
                    (('x'||substr(md5(r.id),1,8))::bit(32)::bigint::numeric
                     / 4294967295.0), 2.0) * 16) * interval '1 day' AS nueva
            FROM reportes r JOIN hoy h ON h.tenant_id = r.tenant_id
            WHERE r.estado IN ('nuevo','asignado','en_proceso')
        )
        UPDATE reportes r SET
            fecha_creacion = c.nueva,
            fecha_actualizacion = CASE WHEN c.estado = 'nuevo' THEN c.nueva
                ELSE c.nueva + (c.hoy - c.nueva) * 0.6 END
        FROM calc c WHERE c.id = r.id
    """))
    await session.commit()
    print(f"         {res.rowcount} reportes abiertos reacomodados (edad realista)")


def main():
    asyncio.run(seed_all())


if __name__ == "__main__":
    main()
