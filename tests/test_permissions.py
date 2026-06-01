"""Pruebas del filtrado por permisos del RAG (barrera de seguridad crítica).

Son funciones puras sobre `UsuarioContexto` + metadatos de candidatos: no
requieren BD, ChromaDB ni embeddings. Si algo aquí falla, NO se debe avanzar.
"""

from app.agente.context import UsuarioContexto
from app.agente.rag.permissions import (
    SIN_AREA,
    build_chroma_where,
    es_visible,
    filtrar_candidatos,
)

TENANT = "magdalena-contreras"
OTRO_TENANT = "tlalpan"


def ctx_director(areas=("bacheo",), reservado=False) -> UsuarioContexto:
    niveles = ["publico", "interno"] + (["reservado"] if reservado else [])
    return UsuarioContexto(
        id="dir",
        tenant_id=TENANT,
        rol="director",
        alcance_datos="direccion_completa",
        areas=list(areas),
        niveles_visibles=niveles,
        seguridad_reservada=reservado,
    )


def ctx_admin(reservado=False) -> UsuarioContexto:
    niveles = ["publico", "interno", "ejecutivo"] + (["reservado"] if reservado else [])
    return UsuarioContexto(
        id="adm",
        tenant_id=TENANT,
        rol="administrador",
        alcance_datos="global",
        areas=[],
        niveles_visibles=niveles,
        seguridad_reservada=reservado,
    )


def meta(nivel="interno", tenant=TENANT, area=SIN_AREA) -> dict:
    return {"nivel": nivel, "tenant_id": tenant, "area_id": area}


# ─── Director (alcance acotado por área) ───────────────────────────────────


def test_director_no_ve_otra_area():
    assert not es_visible(ctx_director(), meta(area="agua"))


def test_director_ve_su_area():
    assert es_visible(ctx_director(), meta(area="bacheo"))


def test_director_ve_documento_sin_area():
    assert es_visible(ctx_director(), meta(area=SIN_AREA))


def test_director_no_ve_otro_tenant():
    assert not es_visible(ctx_director(), meta(tenant=OTRO_TENANT, area="bacheo"))


def test_director_ve_conocimiento_global():
    assert es_visible(ctx_director(), meta(tenant="global", area=SIN_AREA))


def test_director_no_ve_ejecutivo():
    assert not es_visible(ctx_director(), meta(nivel="ejecutivo", area="bacheo"))


def test_director_sin_flag_no_ve_reservado():
    assert not es_visible(ctx_director(), meta(nivel="reservado", area="bacheo"))


def test_director_con_flag_ve_reservado_de_su_area():
    assert es_visible(ctx_director(reservado=True), meta(nivel="reservado", area="bacheo"))


# ─── Administrador (alcance global dentro de su tenant) ────────────────────


def test_admin_ve_ejecutivo():
    assert es_visible(ctx_admin(), meta(nivel="ejecutivo"))


def test_admin_ve_cualquier_area_de_su_tenant():
    assert es_visible(ctx_admin(), meta(area="agua"))


def test_admin_sin_flag_no_ve_reservado():
    assert not es_visible(ctx_admin(), meta(nivel="reservado"))


def test_admin_con_flag_ve_reservado():
    assert es_visible(ctx_admin(reservado=True), meta(nivel="reservado"))


def test_admin_no_ve_otro_tenant():
    assert not es_visible(ctx_admin(), meta(tenant=OTRO_TENANT))


# ─── filtrar_candidatos sobre un lote mixto ────────────────────────────────


def test_filtrar_candidatos_director():
    candidatos = [
        {"id": "1", "metadata": meta(nivel="publico", area="bacheo")},      # ✓
        {"id": "2", "metadata": meta(nivel="interno", area=SIN_AREA)},      # ✓
        {"id": "3", "metadata": meta(nivel="interno", area="agua")},        # ✗ otra área
        {"id": "4", "metadata": meta(nivel="ejecutivo", area="bacheo")},    # ✗ nivel
        {"id": "5", "metadata": meta(nivel="reservado", area="bacheo")},    # ✗ reservado
        {"id": "6", "metadata": meta(tenant=OTRO_TENANT, area="bacheo")},   # ✗ tenant
    ]
    visibles = {c["id"] for c in filtrar_candidatos(ctx_director(), candidatos)}
    assert visibles == {"1", "2"}


def test_filtrar_candidatos_admin():
    candidatos = [
        {"id": "1", "metadata": meta(nivel="ejecutivo", area="agua")},      # ✓
        {"id": "2", "metadata": meta(nivel="reservado")},                   # ✗ sin flag
        {"id": "3", "metadata": meta(tenant=OTRO_TENANT)},                  # ✗ tenant
        {"id": "4", "metadata": meta(tenant="global")},                     # ✓ global
    ]
    visibles = {c["id"] for c in filtrar_candidatos(ctx_admin(), candidatos)}
    assert visibles == {"1", "4"}


# ─── Estructura del filtro enviado a ChromaDB ──────────────────────────────


def test_where_director_incluye_filtro_de_area():
    where = build_chroma_where(ctx_director())
    campos = {list(c.keys())[0] for c in where["$and"]}
    assert campos == {"nivel", "tenant_id", "area_id"}


def test_where_admin_no_filtra_por_area():
    where = build_chroma_where(ctx_admin())
    campos = {list(c.keys())[0] for c in where["$and"]}
    assert campos == {"nivel", "tenant_id"}
