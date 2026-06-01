"""Implementación del motor LLM sobre Claude (Anthropic).

Stub listo para activar: con `LLM_PROVIDER=anthropic` y `ANTHROPIC_API_KEY`,
el factory selecciona esta clase. Requiere el paquete `anthropic` instalado.
"""

from collections.abc import AsyncIterator

from app.agente.llm.base import LLMClient, LLMError, LLMResult, Message


def _split_system(messages: list[Message]) -> tuple[str, list[Message]]:
    """Anthropic separa el system prompt del resto de mensajes."""
    system_parts = [m["content"] for m in messages if m["role"] == "system"]
    rest = [m for m in messages if m["role"] != "system"]
    return "\n\n".join(system_parts), rest


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
        system, rest = _split_system(messages)
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
        return "".join(block.text for block in resp.content if block.type == "text")

    async def stream(
        self,
        messages: list[Message],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        system, rest = _split_system(messages)
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
        if tools:
            # El formato de tool-use de Anthropic difiere del de OpenAI; queda
            # pendiente al activar este proveedor.
            raise LLMError("Tool calling con Anthropic aún no implementado.")
        texto = await self.chat(messages, temperature=temperature, max_tokens=max_tokens)
        return LLMResult(content=texto)
