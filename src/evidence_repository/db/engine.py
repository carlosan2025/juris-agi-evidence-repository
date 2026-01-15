"""SQLAlchemy async engine configuration."""

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from evidence_repository.config import get_settings

_engine: AsyncEngine | None = None


def get_engine() -> AsyncEngine:
    """Get or create the SQLAlchemy async engine.

    For serverless environments (Vercel + Neon), we use NullPool to avoid
    connection pooling issues where connections become stale between invocations.
    """
    global _engine
    if _engine is None:
        settings = get_settings()

        # Check if running in serverless environment (Vercel sets this)
        import os
        is_serverless = os.environ.get("VERCEL") == "1"

        if is_serverless:
            # Serverless: disable connection pooling, create fresh connections
            _engine = create_async_engine(
                settings.database_url,
                poolclass=NullPool,
                echo=settings.debug,
                future=True,
            )
        else:
            # Traditional deployment: use connection pooling
            _engine = create_async_engine(
                settings.database_url,
                pool_size=settings.database_pool_size,
                max_overflow=settings.database_max_overflow,
                pool_pre_ping=True,  # Verify connections before use
                pool_recycle=300,  # Recycle connections after 5 minutes
                echo=settings.debug,
                future=True,
            )
    return _engine


# Convenience alias for direct import
engine = property(lambda self: get_engine())


async def dispose_engine() -> None:
    """Dispose of the engine connection pool."""
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None
