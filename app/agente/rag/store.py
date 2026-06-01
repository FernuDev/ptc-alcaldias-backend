"""Almacén vectorial (RAG), aislado tras una interfaz.

Implementación por defecto: ChromaDB persistente en disco. El embedder se crea de
forma perezosa (solo al consultar/ingresar), de modo que operaciones ligeras como
`count()` no exijan cargar sentence-transformers.
"""

from abc import ABC, abstractmethod
from functools import lru_cache

from app.agente.rag.embeddings import EmbeddingProvider
from app.core.config import settings

COLLECTION = "conocimiento"


class VectorStore(ABC):
    @abstractmethod
    def add(
        self,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict],
    ) -> None:
        ...

    @abstractmethod
    def query(self, texto: str, *, n_results: int, where: dict | None) -> list[dict]:
        ...

    @abstractmethod
    def count(self) -> int:
        ...

    @abstractmethod
    def delete_documento(self, documento_id: str) -> None:
        ...


class ChromaStore(VectorStore):
    def __init__(self, path: str, embedder: EmbeddingProvider | None = None):
        import chromadb

        self._client = chromadb.PersistentClient(path=path)
        self._col = self._client.get_or_create_collection(
            COLLECTION, metadata={"hnsw:space": "cosine"}
        )
        self._embedder = embedder

    def _get_embedder(self) -> EmbeddingProvider:
        if self._embedder is None:
            from app.agente.rag.embeddings import build_embedder

            self._embedder = build_embedder()
        return self._embedder

    def add(self, ids: list[str], documents: list[str], metadatas: list[dict]) -> None:
        embeddings = self._get_embedder().embed(documents)
        self._col.add(ids=ids, documents=documents, metadatas=metadatas, embeddings=embeddings)

    def query(self, texto: str, *, n_results: int, where: dict | None) -> list[dict]:
        emb = self._get_embedder().embed([texto])[0]
        res = self._col.query(
            query_embeddings=[emb],
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        # Chroma devuelve listas-de-listas (una por consulta); aplanamos la 1ª.
        ids = res["ids"][0]
        docs = res["documents"][0]
        metas = res["metadatas"][0]
        dists = res["distances"][0]
        return [
            {"id": i, "document": d, "metadata": m, "distance": dist}
            for i, d, m, dist in zip(ids, docs, metas, dists, strict=False)
        ]

    def count(self) -> int:
        return self._col.count()

    def delete_documento(self, documento_id: str) -> None:
        self._col.delete(where={"documento_id": documento_id})


@lru_cache(maxsize=1)
def get_store() -> VectorStore:
    """Almacén por defecto (Chroma persistente en settings.VECTOR_DB_PATH)."""
    return ChromaStore(settings.VECTOR_DB_PATH)
