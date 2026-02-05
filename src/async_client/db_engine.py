"""
Async database engine factory with connection pooling.

Provides SQLAlchemy async engine using asyncpg driver for
non-blocking PostgreSQL operations.
"""

from functools import lru_cache
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.config import DATABASE_URL


def _convert_to_async_url(url: str) -> str:
    """
    Convert a sync PostgreSQL URL to async (asyncpg) URL.

    Args:
        url: Sync database URL (postgresql://)

    Returns:
        Async database URL (postgresql+asyncpg://)
    """
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


@lru_cache(maxsize=1)
def get_async_engine(
    pool_size: int = 10,
    max_overflow: int = 20,
) -> AsyncEngine:
    """
    Create a singleton async SQLAlchemy engine.

    Uses asyncpg driver for non-blocking PostgreSQL operations.
    The engine is cached and reused across the application.

    Args:
        pool_size: Number of connections to keep open in the pool.
        max_overflow: Number of connections to allow beyond pool_size.

    Returns:
        Configured AsyncEngine instance.
    """
    async_url = _convert_to_async_url(DATABASE_URL)

    return create_async_engine(
        async_url,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_pre_ping=True,  # Validate connections before use
        pool_recycle=3600,  # Recycle connections after 1 hour
    )


def async_session_factory() -> async_sessionmaker[AsyncSession]:
    """
    Create an async session factory.

    Returns a factory that can be used as a context manager:

        async with async_session_factory()() as session:
            result = await session.execute(text("SELECT 1"))

    Returns:
        Configured async_sessionmaker instance.
    """
    engine = get_async_engine()
    return async_sessionmaker(
        engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )


async def dispose_engine() -> None:
    """
    Dispose of the async engine and close all connections.

    Call this during application shutdown for clean cleanup.
    """
    engine = get_async_engine()
    await engine.dispose()
