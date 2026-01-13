"""SQLAlchemy async session management."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from evidence_repository.db.engine import get_engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get the async session factory."""
    return async_sessionmaker(
        bind=get_engine(),
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )


# Convenience alias
AsyncSessionLocal = get_session_factory


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency that yields an async database session.

    Usage in FastAPI:
        @app.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db_session)):
            ...
    """
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
