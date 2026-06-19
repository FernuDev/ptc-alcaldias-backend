"""Implementación del motor LLM sobre Claude (Anthropic), con tool-calling.

Con `LLM_PROVIDER=anthropic` y `ANTHROPIC_API_KEY`, el factory selecciona esta
clase. Requiere el paquete `anthropic` instalado.

El orquestador habla en formato OpenAI (mensajes con ``tool_calls`` y mensajes
``role="tool"``). Aquí se convierte ese historial al formato de bloques de
Anthropic (``tool_use`` / ``tool_result``) en cada llamada, de modo que cambiar
de DeepSeek a Claude no requiere tocar el orquestador.
"""

import json
from collections.abc import AsyncIterator

from app.agente.llm.base import LLMClient, LLMError, LLMResult, Message, ToolCall


def _to_anthropic(messages: list[Message]) -> tuple[str, list[dict]]:
    """Convierte mensajes estilo OpenAI al formato de Anthropic.

    Devuelve ``(system, messages)``. Los mensajes ``role="tool"`` se pliegan en
    un turno ``user`` con bloques ``tool_result`` que sigue al turno ``assistant``
    con ``tool_use`` (orden que Anthropic exige).
    """
    system_parts: list[str] = []
    out: list[dict] = []
    pendientes: list[dict] = []

    def _flush() -> None:
        nonlocal pendientes
        if pendientes:
            out.append({"role": "user", "content": pendientes})
            pendientes = []

    for m in messages:
        role = m.get("role")
        if role == "system":
            if m.get("content"):
                system_parts.append(m["content"])
            continue
        if role == "tool":
            pendientes.append(
                {
                    "type": "tool_result",
                    "tool_use_id": m.get("tool_call_id"),
                    "content": m.get("content") or "",
                }
            )
            continue

        _flush()
        if role == "assistant":
            blocks: list[dict] = []
            if m.get("content"):
                blocks.append({"type": "text", "text": m["content"]})
            for tc in m.get("tool_calls") or []:
                fn = tc.get("function", {})
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except (ValueError, TypeError):
                    args = {}
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": tc.get("id"),
                        "name": fn.get("name"),
                        "input": args,
                    }
                )
            out.append({"role": "assistant", "content": blocks or [{"type": "text", "text": ""}]})
        else:  # user (u otro rol no estándar)
            content = m.get("content")
            out.append(
                {"role": "user", "content": content if isinstance(content, str) else (content or "")}
            )

    _flush()
    return "\n\n".join(system_parts), out


def _to_anthropic_tools(tools: list[dict]) -> list[dict]:
    """Convierte tools OpenAI (``function``) al esquema de Anthropic."""
    out: list[dict] = []
    for t in tools or []:
        fn = t.get("function", t)
        out.append(
            {
                "name": fn.get("name"),
                "description": fn.get("description", ""),
                "input_schema": fn.get("parameters") or {"type": "object", "properties": {}},
            }
        )
    return out


class AnthropicClient(LLMClient):
    def __init__(self, *, api_key: str, model: str, temperature: float, max_tokens: int):
        from anthropic import AsyncAnthropic  # import perezoso

        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens

    async def chat(
        self,
        messages: list[Message],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        system, rest = _to_anthropic(messages)
        try:
            resp = await self._client.messages.create(
                model=self._model,
                system=system,
                messages=rest,
                temperature=self._temperature if temperature is None else temperature,
                max_tokens=self._max_tokens if max_tokens is None else max_tokens,
            )
        except Exception as exc:  # noqa: BLE001
            raise LLMError(f"Anthropic: {exc}") from exc
        return "".join(b.text for b in resp.content if b.type == "text")

    async def stream(
        self,
        messages: list[Message],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        system, rest = _to_anthropic(messages)
        try:
            async with self._client.messages.stream(
                model=self._model,
                system=system,
                messages=rest,
                temperature=self._temperature if temperature is None else temperature,
                max_tokens=self._max_tokens if max_tokens is None else max_tokens,
            ) as stream:
                async for text in stream.text_stream:
                    yield text
        except Exception as exc:  # noqa: BLE001
            raise LLMError(f"Anthropic: {exc}") from exc

    async def complete(
        self,
        messages: list[Message],
        *,
        tools: list[dict] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResult:
        system, rest = _to_anthropic(messages)
        kwargs: dict = {
            "model": self._model,
            "system": system,
            "messages": rest,
            "temperature": self._temperature if temperature is None else temperature,
            "max_tokens": self._max_tokens if max_tokens is None else max_tokens,
        }
        if tools:
            kwargs["tools"] = _to_anthropic_tools(tools)
        try:
            resp = await self._client.messages.create(**kwargs)
        except Exception as exc:  # noqa: BLE001
            raise LLMError(f"Anthropic: {exc}") from exc

        content = "".join(b.text for b in resp.content if b.type == "text")
        tool_calls = [
            ToolCall(id=b.id, name=b.name, arguments=json.dumps(b.input))
            for b in resp.content
            if b.type == "tool_use"
        ]
        return LLMResult(content=content or None, tool_calls=tool_calls)
