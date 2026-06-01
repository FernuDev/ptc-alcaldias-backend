"""Motor LLM falso, determinista y sin red, para pruebas.

No llama a ninguna API. Útil para validar el orquestador, los permisos, el
tool-calling y los endpoints sin depender de claves ni conectividad.
"""

import json
import re
from collections.abc import AsyncIterator

from app.agente.llm.base import LLMClient, LLMResult, Message, ToolCall

# Folio/id de reporte u obra: MC-2026-0358, MC-RC-0009, TL-OB-012, etc.
_REF_RE = re.compile(r"[A-Z]{2}-(?:RC-|OB-)?\d{2,4}|[A-Z]{2}-2026-\d{2,4}")


class FakeLLM(LLMClient):
    def __init__(self, respuesta_fija: str | None = None):
        self._respuesta_fija = respuesta_fija

    def _responder(self, messages: list[Message]) -> str:
        if self._respuesta_fija is not None:
            return self._respuesta_fija
        ultimo_usuario = next(
            (str(m.get("content", "")) for m in reversed(messages) if m.get("role") == "user"),
            "",
        )
        # Considera "contexto" tanto el RAG como los resultados de herramientas.
        tiene_contexto = any(
            "CONTEXTO RECUPERADO" in str(m.get("content", "")) for m in messages
        ) or any(m.get("role") == "tool" for m in messages)
        if not tiene_contexto:
            return "No tengo esa información en la base de conocimiento."
        return f"[respuesta-fake] {ultimo_usuario[:200]}"

    async def chat(
        self,
        messages: list[Message],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        return self._responder(messages)

    async def stream(
        self,
        messages: list[Message],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        for palabra in self._responder(messages).split(" "):
            yield palabra + " "

    async def complete(
        self,
        messages: list[Message],
        *,
        tools: list[dict] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResult:
        # Con herramientas disponibles y un folio en la consulta (y sin resultado
        # de herramienta aún), simula la decisión de consultar el reporte.
        if tools and not any(m.get("role") == "tool" for m in messages):
            ultimo_usuario = next(
                (str(m.get("content", "")) for m in reversed(messages) if m.get("role") == "user"),
                "",
            )
            m = _REF_RE.search(ultimo_usuario)
            if m:
                return LLMResult(
                    tool_calls=[
                        ToolCall(
                            id="call_1",
                            name="consultar_reporte",
                            arguments=json.dumps({"referencia": m.group(0)}),
                        )
                    ]
                )
        return LLMResult(content=self._responder(messages))
