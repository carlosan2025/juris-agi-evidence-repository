"""SQLAlchemy async engine configuration."""

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from evidence_repository.config import get_settings

_engine: AsyncEngine | None = None


def get_engine() -> AsyncEngine:
    """Get or create the SQLAlchemy async engine."""
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
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
