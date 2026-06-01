"""Integración del almacén vectorial: valida que el filtro `where` enviado a
ChromaDB (primera barrera) bloquea de verdad lo prohibido, usando FakeEmbedder
(sin red ni modelos pesados) contra una colección temporal en disco.
"""

from app.agente.rag.embeddings import FakeEmbedder
from app.agente.rag.permissions import SIN_AREA, build_chroma_where
from tests.test_permissions import ctx_admin, ctx_director


def _store(tmp_path):
    from app.agente.rag.store import ChromaStore

    return ChromaStore(str(tmp_path / "chroma"), embedder=FakeEmbedder())


def _seed(store):
    store.add(
        ids=["a", "b", "c", "d", "e"],
        documents=[
            "procedimiento de bacheo interno",
            "procedimiento de agua interno",
            "tablero ejecutivo presupuestal",
            "documento de tlalpan",
            "reglamento publico global",
        ],
        metadatas=[
            {"documento_id": i, "titulo": i, "nivel": n, "tenant_id": t, "area_id": a}
            for i, n, t, a in [
                ("A", "interno", "magdalena-contreras", "bacheo"),
                ("B", "interno", "magdalena-contreras", "agua"),
                ("C", "ejecutivo", "magdalena-contreras", SIN_AREA),
                ("D", "interno", "tlalpan", "bacheo"),
                ("E", "publico", "global", SIN_AREA),
            ]
        ],
    )


def test_where_director_bloquea_en_chroma(tmp_path):
    store = _store(tmp_path)
    _seed(store)
    res = store.query("procedimiento", n_results=10, where=build_chroma_where(ctx_director()))
    ids = {r["metadata"]["documento_id"] for r in res}
    assert ids <= {"A", "E"}  # solo su área + global público
    assert "B" not in ids and "C" not in ids and "D" not in ids


def test_where_admin_ve_ejecutivo_y_global_no_otro_tenant(tmp_path):
    store = _store(tmp_path)
    _seed(store)
    res = store.query("documento", n_results=10, where=build_chroma_where(ctx_admin()))
    ids = {r["metadata"]["documento_id"] for r in res}
    assert {"A", "B", "C", "E"} <= ids  # todas las áreas de su tenant + ejecutivo + global
    assert "D" not in ids  # nunca otro tenant


def test_count(tmp_path):
    store = _store(tmp_path)
    _seed(store)
    assert store.count() == 5
