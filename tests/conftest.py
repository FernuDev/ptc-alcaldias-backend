"""Fixtures compartidas de tests."""

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings


@pytest_asyncio.fixture
async def db():
    """Sesión async contra Postgres con engine propio por test.

    Se usa NullPool y un engine creado dentro del loop del test para evitar el
    error de asyncpg "attached to a different loop" (pytest-asyncio crea un loop
    por función). Todo se revierte al final: no persiste nada.
    """
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        try:
            yield session
        finally:
            await session.rollback()
    await engine.dispose()
