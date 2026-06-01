"""Proveedor de embeddings, aislado tras una interfaz para poder sustituirlo.

Implementación por defecto: `LocalEmbedder` (sentence-transformers, all-MiniLM),
100% local y sin API key. `FakeEmbedder` es determinista y sin dependencias,
pensado para tests rápidos y offline.
"""

import hashlib
import math
from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    @property
    @abstractmethod
    def dim(self) -> int:
        ...

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        ...


class FakeEmbedder(EmbeddingProvider):
    """Embeddings deterministas por hashing de tokens. Solo para tests."""

    def __init__(self, dim: int = 64):
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        salida: list[list[float]] = []
        for t in texts:
            v = [0.0] * self._dim
            for tok in t.lower().split():
                h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
                v[h % self._dim] += 1.0
            norm = math.sqrt(sum(x * x for x in v)) or 1.0
            salida.append([x / norm for x in v])
        return salida


class LocalEmbedder(EmbeddingProvider):
    """Embeddings locales con sentence-transformers (descarga el modelo 1ª vez)."""

    def __init__(self, model_name: str):
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)
        self._dim = int(self._model.get_sentence_embedding_dimension())

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        vecs = self._model.encode(list(texts), normalize_embeddings=True)
        return [list(map(float, v)) for v in vecs]


def build_embedder() -> EmbeddingProvider:
    """Construye el embedder según configuración (local por defecto)."""
    from app.core.config import settings

    if settings.EMBEDDING_PROVIDER.lower() == "fake":
        return FakeEmbedder()
    return LocalEmbedder(settings.EMBEDDING_MODEL)
