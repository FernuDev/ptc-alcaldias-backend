"""Selección del motor LLM según configuración.

Cada implementación se importa de forma perezosa para no exigir dependencias
(openai / anthropic) de proveedores que no están activos.
"""

from functools import lru_cache

from app.agente.llm.base import LLMClient
from app.core.config import settings


def build_llm_client() -> LLMClient:
    provider = settings.LLM_PROVIDER.lower()

    if provider == "deepseek":
        from app.agente.llm.deepseek import DeepSeekClient

        return DeepSeekClient(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL,
            model=settings.DEEPSEEK_MODEL,
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=settings.LLM_MAX_TOKENS,
        )

    if provider == "anthropic":
        from app.agente.llm.anthropic import AnthropicClient

        return AnthropicClient(
            api_key=settings.ANTHROPIC_API_KEY,
            model=settings.ANTHROPIC_MODEL,
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=settings.LLM_MAX_TOKENS,
        )

    if provider == "fake":
        from app.agente.llm.fake import FakeLLM

        return FakeLLM()

    raise ValueError(f"LLM_PROVIDER desconocido: {settings.LLM_PROVIDER!r}")


@lru_cache(maxsize=1)
def get_llm_client() -> LLMClient:
    """Cliente LLM cacheado (un proceso = una instancia)."""
    return build_llm_client()
