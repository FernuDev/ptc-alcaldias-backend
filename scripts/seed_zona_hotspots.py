#!/usr/bin/env python3
"""Inyecta los focos densos del Expediente de zona (Plan.IA) en una DB ya
sembrada, sin re-ejecutar el seed completo.

Reutiliza el generador y la inserción de ``scripts/seed.py`` (fuente única), así
que los datos son idénticos a los que produciría un seed limpio. Idempotente:
todos los INSERT usan ON CONFLICT DO NOTHING.

Uso:
    python scripts/seed_zona_hotspots.py

Lee DATABASE_URL del entorno / .env (igual que seed.py). Útil para refrescar la
demo en caliente; el seed completo ya los incluye en arranques nuevos.
"""

from __future__ import annotations

import asyncio
import os
import sys

# Permite importar seed.py (mismo directorio) corriendo desde la raíz del backend.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from seed import (  # noqa: E402
    DATABASE_URL,
    REPORTES_SEED,
    generate_zona_hotspots_for_tenant,
    insert_reportes,
)


async def main() -> None:
    print(f"Connecting to: {DATABASE_URL.split('@')[-1] if '@' in DATABASE_URL else DATABASE_URL}")
    engine = create_async_engine(DATABASE_URL, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    hotspots_mc = generate_zona_hotspots_for_tenant("magdalena-contreras", REPORTES_SEED + 101)
    hotspots_tl = generate_zona_hotspots_for_tenant("tlalpan", REPORTES_SEED + 131)
    all_hotspots = hotspots_mc + hotspots_tl

    async with Session() as session:
        await insert_reportes(session, all_hotspots)
        await session.commit()

    await engine.dispose()
    print(
        f"Listo: {len(all_hotspots)} reportes de focos de zona "
        f"({len(hotspots_mc)} MC + {len(hotspots_tl)} TL)."
    )


if __name__ == "__main__":
    asyncio.run(main())
