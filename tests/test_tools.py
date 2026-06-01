"""Pruebas de las herramientas de datos y del loop de tool-calling.

Verifican que: (1) las herramientas respetan el alcance del usuario, y (2) el
orquestador ejecuta una herramienta cuando el modelo la solicita (FakeLLM emite
una llamada al detectar un folio en la pregunta).
"""

import json

from sqlalchemy import select

from app.agente import orchestrator, tools
from app.agente.llm.base import LLMResult, ToolCall
from app.agente.llm.fake import FakeLLM
from app.models.reporte import Reporte
from app.models.user import User


async def _user(db, uid: str) -> User:
    return (await db.execute(select(User).where(User.id == uid))).scalar_one()


async def _folio_de(db, tenant: str, categoria: str | None = None) -> str:
    stmt = select(Reporte.folio).where(Reporte.tenant_id == tenant)
    if categoria:
        stmt = stmt.where(Reporte.categoria_id == categoria)
    return (await db.execute(stmt.limit(1))).scalar_one()


# ─── Herramientas: alcance ──────────────────────────────────────────────────


async def test_consultar_reporte_admin_encuentra(db):
    admin = await _user(db, "mc-admin")
    folio = await _folio_de(db, "magdalena-contreras")
    out = await tools.ejecutar_tool("consultar_reporte", {"referencia": folio}, admin, db)
    assert out["encontrado"] is True
    assert out["folio"] == folio


async def test_consultar_reporte_director_fuera_de_area_no_encuentra(db):
    director = await _user(db, "mc-dir-obras")  # área: bacheo
    # Un folio de otra área del mismo tenant: el director NO debe poder verlo.
    folio_otra_area = (
        await db.execute(
            select(Reporte.folio).where(
                Reporte.tenant_id == "magdalena-contreras", Reporte.categoria_id != "bacheo"
            ).limit(1)
        )
    ).scalar_one()
    out = await tools.ejecutar_tool(
        "consultar_reporte", {"referencia": folio_otra_area}, director, db
    )
    assert out.get("encontrado") is False


async def test_consultar_reporte_cross_tenant_no_encuentra(db):
    admin_mc = await _user(db, "mc-admin")
    folio_tlalpan = await _folio_de(db, "tlalpan")
    out = await tools.ejecutar_tool(
        "consultar_reporte", {"referencia": folio_tlalpan}, admin_mc, db
    )
    assert out.get("encontrado") is False


async def test_buscar_reportes_filtra_por_estado(db):
    admin = await _user(db, "mc-admin")
    out = await tools.ejecutar_tool("buscar_reportes", {"estado": "nuevo", "limite": 5}, admin, db)
    assert "reportes" in out
    assert all(r["estado"] == "nuevo" for r in out["reportes"])


# ─── Loop de tool-calling en el orquestador ────────────────────────────────


async def test_chat_invoca_herramienta_por_folio(db):
    admin = await _user(db, "mc-admin")
    folio = await _folio_de(db, "magdalena-contreras")
    # FakeLLM, al ver un folio y tener herramientas, pide consultar_reporte.
    resp = await orchestrator.responder_chat(
        db, admin, f"dame información del reporte {folio}", llm=FakeLLM()
    )
    # Se registró el uso de la herramienta como fuente "consulta en vivo".
    assert any(f.documento_id == "tool:consultar_reporte" for f in resp.fuentes)
    assert resp.sin_informacion is False


# ─── Navegación ─────────────────────────────────────────────────────────────


async def test_navegar_pantalla_fija(db):
    admin = await _user(db, "mc-admin")
    out = await tools.ejecutar_tool("navegar", {"destino": "obras"}, admin, db)
    assert out["navegacion"]["href"] == "/backoffice/obras"


async def test_navegar_reporte_en_alcance(db):
    admin = await _user(db, "mc-admin")
    folio = await _folio_de(db, "magdalena-contreras")
    out = await tools.ejecutar_tool(
        "navegar", {"destino": "reporte", "referencia": folio}, admin, db
    )
    assert out["navegacion"]["href"].startswith("/backoffice/reportes/")
    assert folio in out["navegacion"]["titulo"]


async def test_navegar_reporte_fuera_de_alcance(db):
    director = await _user(db, "mc-dir-obras")  # área: bacheo
    folio_otra_area = (
        await db.execute(
            select(Reporte.folio)
            .where(
                Reporte.tenant_id == "magdalena-contreras", Reporte.categoria_id != "bacheo"
            )
            .limit(1)
        )
    ).scalar_one()
    out = await tools.ejecutar_tool(
        "navegar", {"destino": "reporte", "referencia": folio_otra_area}, director, db
    )
    assert "navegacion" not in out
    assert out.get("encontrado") is False


class _NavLLM(FakeLLM):
    """LLM de prueba que decide navegar a 'obras' una vez."""

    async def complete(self, messages, *, tools=None, temperature=None, max_tokens=None):
        if tools and not any(m.get("role") == "tool" for m in messages):
            return LLMResult(
                tool_calls=[ToolCall("c1", "navegar", json.dumps({"destino": "obras"}))]
            )
        return LLMResult(content="Te dejo el enlace para abrir la pantalla.")


async def test_chat_recolecta_navegacion(db):
    admin = await _user(db, "mc-admin")
    resp = await orchestrator.responder_chat(db, admin, "llévame a obras", llm=_NavLLM())
    assert resp.navegacion and resp.navegacion[0].href == "/backoffice/obras"
