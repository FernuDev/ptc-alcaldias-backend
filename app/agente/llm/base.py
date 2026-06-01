"""Interfaz intercambiable del motor LLM.

La lógica de negocio depende solo de `LLMClient`. Cambiar de DeepSeek a Claude
debe ser cambiar `LLM_PROVIDER` (y la key), sin tocar el orquestador.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

# Un mensaje sigue el formato OpenAI: {"role": ..., "content": ...} y, para
# turnos con herramientas, puede incluir "tool_calls" o "tool_call_id".
Message = dict


class LLMError(Exception):
    """Fallo del proveedor LLM (red, autenticación, saldo, etc.)."""


@dataclass
class ToolCall:
    """Solicitud del modelo para invocar una herramienta."""

    id: str
    name: str
    arguments: str  # JSON en crudo tal como lo emite el modelo


@dataclass
class LLMResult:
    """Resultado de una completación: texto final y/o llamadas a herramientas."""

    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)


class LLMClient(ABC):
    """Contrato mínimo que toda implementación de LLM debe cumplir."""

    @abstractmethod
    async def chat(
        self,
        messages: list[Message],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Devuelve la respuesta completa del modelo como texto."""
        ...

    @abstractmethod
    def stream(
        self,
        messages: list[Message],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        """Itera fragmentos de texto conforme el modelo los genera (SSE)."""
        ...

    @abstractmethod
    async def complete(
        self,
        messages: list[Message],
        *,
        tools: list[dict] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResult:
        """Completación no-streaming que puede devolver llamadas a herramientas."""
        ...
