"""Pruebas del orquestador con FakeLLM + store falso (sin red ni API key)."""

import pytest
from sqlalchemy import select

from app.agente import orchestrator
from app.agente.context import UsuarioContexto
from app.agente.llm.fake import FakeLLM
from app.agente.rag.embeddings import FakeEmbedder
from app.agente.rag.permissions import SIN_AREA
from app.agente.rag.store import ChromaStore
from app.models.user import User

# Usamos un usuario/tenant reales para que pase la FK al registrar la bitácora.
TENANT = "magdalena-contreras"


async def _admin(db) -> User:
    return (await db.execute(select(User).where(User.id == "mc-admin"))).scalar_one()


def ctx_admin() -> UsuarioContexto:
    return UsuarioContexto(
        id="mc-admin",
        tenant_id=TENANT,
        rol="administrador",
        alcance_datos="global",
        areas=[],
        niveles_visibles=["publico", "interno", "ejecutivo"],
    )


@pytest.fixture
def store_con_doc(tmp_path):
    s = ChromaStore(str(tmp_path / "c"), embedder=FakeEmbedder())
    s.add(
        ids=["d:0"],
        documents=["El bacheo se atiende en un máximo de 72 horas según el manual operativo."],
        metadatas=[
            {
                "documento_id": "D1",
                "titulo": "Manual de bacheo",
                "nivel": "interno",
                "tenant_id": TENANT,
                "area_id": SIN_AREA,
                "seccion": "fragmento 1/1",
            }
        ],
    )
    return s


async def test_chat_con_contexto_cita_fuente(db, store_con_doc):
    resp = await orchestrator.responder_chat(
        db,
        await _admin(db),
        "¿en cuánto tiempo se atiende el bacheo?",
        store=store_con_doc,
        llm=FakeLLM(),
    )
    assert resp.sin_informacion is False
    assert resp.fuentes and resp.fuentes[0].documento_id == "D1"
    assert "[respuesta-fake]" in resp.respuesta


async def test_chat_sin_resultados_dice_no_se(db, tmp_path):
    vacio = ChromaStore(str(tmp_path / "e"), embedder=FakeEmbedder())
    resp = await orchestrator.responder_chat(
        db, await _admin(db), "pregunta sin documentos", store=vacio, llm=FakeLLM()
    )
    assert resp.sin_informacion is True
    assert resp.fuentes == []
    assert "no tengo" in resp.respuesta.lower()


async def test_stream_chat_emite_fragmentos_y_fuentes(db, store_con_doc):
    eventos = []
    async for e in orchestrator.stream_chat(
        db, await _admin(db), "¿cuánto tarda el bacheo?", store=store_con_doc, llm=FakeLLM()
    ):
        eventos.append(e)
    deltas = "".join(e["delta"] for e in eventos if "delta" in e)
    assert "[respuesta-fake]" in deltas
    # El último evento trae las fuentes citadas.
    final = eventos[-1]
    assert "fuentes" in final and final["fuentes"]
    assert final["sin_informacion"] is False


async def test_classify_detecta_emergencia(db):
    resp = await orchestrator.clasificar_reporte(
        db,
        ctx_admin(),
        "Hay una balacera con personas heridas en la colonia, urge apoyo",
        ["bacheo", "seguridad", "agua"],
        llm=FakeLLM(),
    )
    assert resp.es_emergencia is True
    assert resp.prioridad_sugerida == "critica"
    assert resp.canal_recomendado
