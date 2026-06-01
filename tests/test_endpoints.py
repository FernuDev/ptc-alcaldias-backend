"""E2E de los endpoints del agente vía HTTP (ASGI), offline y determinista.

Usa proveedores 'fake' (LLM y embeddings) + JWT real (create_access_token). Valida
auth, derivación de contexto desde el JWT, filtrado por permisos sobre HTTP,
aislamiento admin/director y gating de nivel reservado/ejecutivo.
"""

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.agente.rag.permissions import SIN_AREA
from app.core.config import settings
from app.core.security import create_access_token

TENANT = "magdalena-contreras"

# Documentos sembrados directamente en el store (id_documento -> metadatos).
_DOCS = [
    ("PUB", "Guía pública", "publico", "global", SIN_AREA, "atención ciudadana folio"),
    ("BACHEO", "Procedimiento bacheo", "interno", TENANT, "bacheo", "bacheo sla 72h cuadrilla"),
    ("ALUM", "Manual alumbrado", "interno", TENANT, "alumbrado", "luminaria led 96h"),
    ("EJEC", "Tablero ejecutivo", "ejecutivo", TENANT, SIN_AREA, "presupuesto ejecutivo"),
    ("RESV", "Protocolo reservado", "reservado", TENANT, SIN_AREA, "protocolo reservado seguridad"),
]


@pytest_asyncio.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "fake")
    monkeypatch.setattr(settings, "EMBEDDING_PROVIDER", "fake")
    monkeypatch.setattr(settings, "VECTOR_DB_PATH", str(tmp_path / "chroma"))

    from app.agente.llm import factory as llm_factory
    from app.agente.rag import store as store_mod

    llm_factory.get_llm_client.cache_clear()
    store_mod.get_store.cache_clear()

    store = store_mod.get_store()
    store.add(
        ids=[f"{d[0]}:0" for d in _DOCS],
        documents=[d[5] for d in _DOCS],
        metadatas=[
            {
                "documento_id": d[0],
                "titulo": d[1],
                "nivel": d[2],
                "tenant_id": d[3],
                "area_id": d[4],
                "seccion": "fragmento 1/1",
                "fuente": "test",
            }
            for d in _DOCS
        ],
    )

    # Sesión de test (NullPool, sin commit) para aislar del engine global.
    from app.core.database import get_db
    from app.main import app

    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _override_db():
        async with factory() as s:
            try:
                yield s
            finally:
                await s.rollback()

    app.dependency_overrides[get_db] = _override_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
    await engine.dispose()
    llm_factory.get_llm_client.cache_clear()
    store_mod.get_store.cache_clear()


def _auth(user_id: str, role: str, areas: list[str]) -> dict:
    token = create_access_token(user_id, TENANT, role, areas)
    return {"Authorization": f"Bearer {token}"}


ADMIN = lambda: _auth("mc-admin", "admin", [])  # noqa: E731
DIRECTOR = lambda: _auth("mc-dir-obras", "director_area", ["bacheo"])  # noqa: E731


async def test_sin_token_401(client):
    r = await client.post("/api/v1/agente/chat", json={"mensaje": "hola"})
    assert r.status_code == 401


async def test_health_ok_con_fake(client):
    r = await client.get("/api/v1/agente/health", headers=ADMIN())
    assert r.status_code == 200
    body = r.json()
    assert body["llm_configurado"] is True
    assert body["vector_store_ok"] is True


async def test_chat_admin_cita_fuentes(client):
    r = await client.post(
        "/api/v1/agente/chat",
        headers=ADMIN(),
        json={"mensaje": "procedimiento de bacheo y sla"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["sin_informacion"] is False
    assert body["fuentes"]


async def test_chat_director_aislado_por_area_y_nivel(client):
    # El director de bacheo no debe recibir documentos de otra área ni de niveles
    # superiores (ejecutivo/reservado), aunque pregunte justo por ellos.
    r = await client.post(
        "/api/v1/agente/chat",
        headers=DIRECTOR(),
        json={"mensaje": "presupuesto tablero ejecutivo y protocolo reservado de alumbrado"},
    )
    assert r.status_code == 200
    ids = {f["documento_id"] for f in r.json()["fuentes"]}
    assert ids <= {"PUB", "BACHEO"}  # solo su área + conocimiento global público
    assert {"EJEC", "RESV", "ALUM"}.isdisjoint(ids)


async def test_admin_ve_ejecutivo_pero_no_reservado_sin_flag(client):
    r = await client.post(
        "/api/v1/agente/chat",
        headers=ADMIN(),
        json={"mensaje": "presupuesto tablero ejecutivo y protocolo reservado"},
    )
    ids = {f["documento_id"] for f in r.json()["fuentes"]}
    assert "EJEC" in ids       # admin sí ve ejecutivo
    assert "RESV" not in ids   # pero no reservado (sin puede_ver_reservado)


async def test_ingest_prohibido_para_director(client):
    r = await client.post(
        "/api/v1/agente/ingest",
        headers=DIRECTOR(),
        json={"titulo": "x", "contenido": "y", "nivel_visibilidad": "interno"},
    )
    assert r.status_code == 403


async def test_classify_emergencia_http(client):
    r = await client.post(
        "/api/v1/agente/classify",
        headers=ADMIN(),
        json={"descripcion": "Reportan una balacera con personas heridas, urge apoyo"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["es_emergencia"] is True
    assert body["prioridad_sugerida"] == "critica"
