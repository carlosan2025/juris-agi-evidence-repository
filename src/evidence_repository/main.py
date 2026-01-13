"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from evidence_repository.api.middleware import setup_middleware
from evidence_repository.api.routes import router
from evidence_repository.config import get_settings
from evidence_repository.db.engine import dispose_engine

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler.

    Handles startup and shutdown events.
    """
    # Startup
    logger.info("Starting Evidence Repository API...")
    settings = get_settings()
    logger.info(f"Storage backend: {settings.storage_backend}")
    logger.info(f"Debug mode: {settings.debug}")

    yield

    # Shutdown
    logger.info("Shutting down Evidence Repository API...")
    await dispose_engine()
    logger.info("Database connections closed")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        description="""
# Evidence Repository API

API-first document management system designed to feed Juris-AGI.

## Key Features

- **Global Documents**: Documents are standalone assets that can be attached to multiple projects
- **Version Control**: Every document maintains immutable versions for stable citations
- **Evidence Spans**: Precise locators (page/bbox, sheet/cell, char offsets) for citations
- **Semantic Search**: Vector similarity search powered by pgvector and OpenAI embeddings
- **Evidence Packs**: Bundle evidence items for export and presentation

## Authentication

Currently using API key authentication via `X-API-Key` header.
JWT Bearer token support is prepared for future upgrade.

## Getting Started

1. Obtain an API key
2. Include `X-API-Key: your-key` header in all requests
3. Upload documents via `/api/v1/documents`
4. Create projects and attach documents
5. Extract text and generate embeddings
6. Search and build evidence packs
        """,
        version=settings.app_version,
        openapi_url=f"{settings.api_v1_prefix}/openapi.json",
        docs_url=f"{settings.api_v1_prefix}/docs",
        redoc_url=f"{settings.api_v1_prefix}/redoc",
        lifespan=lifespan,
    )

    # Setup CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=settings.cors_allow_methods,
        allow_headers=settings.cors_allow_headers,
    )

    # Setup custom middleware (audit logging, error handling)
    setup_middleware(app)

    # Include API router
    app.include_router(router, prefix=settings.api_v1_prefix)

    return app


# Create app instance
app = create_app()


def run() -> None:
    """Run the application using uvicorn."""
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "evidence_repository.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    run()
