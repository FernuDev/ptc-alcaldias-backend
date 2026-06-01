#!/usr/bin/env python
"""Ingesta los documentos demo de la base de conocimiento del Agente Institucional.

Lee los .md de KNOWLEDGE_PATH (frontmatter simple + cuerpo) y los carga en el
almacén vectorial. Idempotente por título: borra el documento previo con el mismo
título antes de reinsertarlo.

Uso (dentro del contenedor):
    python scripts/ingest_knowledge.py
"""

import asyncio
from pathlib import Path

from sqlalchemy import delete, select

from app.agente.rag.ingest import ingest_documento
from app.core.config import settings
from app.core.database import async_session_factory
from app.models.agente_documento import AgenteDocumento


def _parse_frontmatter(texto: str) -> tuple[dict, str]:
    """Parsea un frontmatter YAML mínimo (clave: valor) delimitado por '---'."""
    if not texto.startswith("---"):
        return {}, texto
    _, fm, cuerpo = texto.split("---", 2)
    meta: dict = {}
    for linea in fm.strip().splitlines():
        if ":" in linea:
            k, _, v = linea.partition(":")
            meta[k.strip()] = v.strip()
    return meta, cuerpo.strip()


async def main() -> None:
    carpeta = Path(settings.KNOWLEDGE_PATH)
    archivos = sorted(carpeta.glob("*.md"))
    if not archivos:
        print(f"Sin documentos en {carpeta.resolve()}")
        return

    async with async_session_factory() as db:
        for ruta in archivos:
            meta, cuerpo = _parse_frontmatter(ruta.read_text(encoding="utf-8"))
            titulo = meta.get("titulo") or ruta.stem

            # Idempotencia: elimina la versión anterior con el mismo título.
            previos = (
                await db.execute(select(AgenteDocumento).where(AgenteDocumento.titulo == titulo))
            ).scalars().all()
            from app.agente.rag.store import get_store

            for p in previos:
                get_store().delete_documento(p.id)
            await db.execute(delete(AgenteDocumento).where(AgenteDocumento.titulo == titulo))

            doc = await ingest_documento(
                db,
                titulo=titulo,
                contenido=cuerpo,
                nivel=meta.get("nivel", "interno"),
                tenant_id=meta.get("tenant") or "global",
                area_id=(meta.get("area") or None),
                fuente=meta.get("fuente"),
            )
            print(f"  ✓ {titulo}  [nivel={doc.nivel_visibilidad} tenant={doc.tenant_id} "
                  f"area={doc.area_id or '-'}]  {doc.fragmentos} fragmento(s)")
        await db.commit()

    print("\nIngesta completa.")


if __name__ == "__main__":
    asyncio.run(main())
