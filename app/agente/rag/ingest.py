"""Ingesta de documentos a la base de conocimiento (RAG).

Trocea el texto, etiqueta cada fragmento con su metadato de visibilidad
(tenant, nivel, área), lo embebe en el almacén vectorial y registra el documento
en `agente_documentos` para poder listarlo/auditarlo.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.agente.context import NivelVisibilidad
from app.agente.rag.permissions import SIN_AREA
from app.agente.rag.store import VectorStore, get_store
from app.models.agente_documento import AgenteDocumento


def chunk_text(texto: str, *, max_chars: int = 900, overlap: int = 150) -> list[str]:
    """Trocea por párrafos acumulando hasta ~max_chars, con solapamiento."""
    parrafos = [p.strip() for p in texto.split("\n\n") if p.strip()]
    fragmentos: list[str] = []
    actual = ""
    for p in parrafos:
        if actual and len(actual) + len(p) + 2 > max_chars:
            fragmentos.append(actual)
            # solapamiento: arrastra la cola del fragmento anterior
            actual = (actual[-overlap:] + "\n\n" + p) if overlap else p
        else:
            actual = f"{actual}\n\n{p}" if actual else p
    if actual:
        fragmentos.append(actual)
    return fragmentos or [texto.strip()]


async def ingest_documento(
    db: AsyncSession,
    *,
    titulo: str,
    contenido: str,
    nivel: NivelVisibilidad,
    tenant_id: str = "global",
    area_id: str | None = None,
    fuente: str | None = None,
    store: VectorStore | None = None,
) -> AgenteDocumento:
    store = store or get_store()

    doc = AgenteDocumento(
        titulo=titulo,
        nivel_visibilidad=nivel,
        tenant_id=tenant_id,
        area_id=area_id,
        fuente=fuente,
        fragmentos=0,
    )
    db.add(doc)
    await db.flush()  # asigna doc.id

    fragmentos = chunk_text(contenido)
    ids = [f"{doc.id}:{i}" for i in range(len(fragmentos))]
    metadatas = [
        {
            "documento_id": doc.id,
            "titulo": titulo,
            "nivel": nivel,
            "tenant_id": tenant_id,
            "area_id": area_id or SIN_AREA,
            "seccion": f"fragmento {i + 1}/{len(fragmentos)}",
            "fuente": fuente or "",
        }
        for i in range(len(fragmentos))
    ]
    store.add(ids=ids, documents=fragmentos, metadatas=metadatas)

    doc.fragmentos = len(fragmentos)
    await db.flush()
    return doc
