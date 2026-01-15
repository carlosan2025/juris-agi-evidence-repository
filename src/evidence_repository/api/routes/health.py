"""Health check endpoints."""

import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from evidence_repository.config import get_settings
from evidence_repository.db.session import get_db_session
from evidence_repository.schemas.common import HealthResponse

router = APIRouter()

# Check if running in serverless environment
IS_SERVERLESS = os.environ.get("VERCEL") == "1"


async def _check_redis() -> tuple[str, dict | None]:
    """Check Redis connectivity and return status with info."""
    # In serverless mode, Redis is not expected to be available
    if IS_SERVERLESS:
        return "skipped (serverless)", {"mode": "serverless", "note": "Redis not used in Vercel deployment"}

    try:
        from evidence_repository.queue.connection import get_redis_connection

        redis_conn = get_redis_connection()
        # Ping Redis
        if redis_conn.ping():
            # Get queue info
            info = redis_conn.info("server")
            return "healthy", {
                "redis_version": info.get("redis_version"),
                "connected_clients": redis_conn.info("clients").get("connected_clients"),
            }
        return "unhealthy: ping failed", None
    except Exception as e:
        return f"unhealthy: {e}", None


async def _check_database(db: AsyncSession) -> tuple[str, dict | None]:
    """Check database connectivity and return status with info."""
    try:
        # Test basic connectivity
        result = await db.execute(text("SELECT 1"))
        result.fetchone()

        # Get PostgreSQL version and pgvector status
        version_result = await db.execute(text("SELECT version()"))
        version = version_result.scalar()

        # Check if pgvector extension is installed
        ext_result = await db.execute(
            text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        )
        pgvector_version = ext_result.scalar()

        return "healthy", {
            "version": version.split(",")[0] if version else "unknown",
            "pgvector": pgvector_version or "not installed",
        }
    except Exception as e:
        return f"unhealthy: {e}", None


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health Check",
    description="Check the health status of the API and its dependencies.",
)
async def health_check(
    db: AsyncSession = Depends(get_db_session),
) -> HealthResponse:
    """Perform comprehensive health check.

    Verifies:
    - API is running
    - Database connection is working
    - Redis connection is working (if configured)
    - pgvector extension is installed
    """
    settings = get_settings()

    # Check database
    db_status, db_info = await _check_database(db)

    # Check Redis
    redis_status, redis_info = await _check_redis()

    # Determine overall status
    # In serverless mode, Redis is skipped so we only check database
    if IS_SERVERLESS:
        overall_status = "healthy" if db_status == "healthy" else "unhealthy"
    elif db_status == "healthy" and redis_status == "healthy":
        overall_status = "healthy"
    elif db_status == "healthy" or redis_status == "healthy":
        overall_status = "degraded"
    else:
        overall_status = "unhealthy"

    return HealthResponse(
        status=overall_status,
        version=settings.app_version,
        timestamp=datetime.now(timezone.utc),
        database=db_status,
        redis=redis_status,
        details={
            "database": db_info,
            "redis": redis_info,
            "app_name": settings.app_name,
            "debug": settings.debug,
        },
    )


@router.get(
    "/health/db",
    summary="Database Health Check",
    description="Check database connectivity and get detailed info.",
)
async def database_health_check(
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Detailed database health check."""
    status, info = await _check_database(db)

    # Get table counts
    table_counts = {}
    tables = [
        "documents", "document_versions", "projects", "project_documents",
        "spans", "claims", "metrics", "embedding_chunks",
        "jobs", "ingestion_batches", "ingestion_items",
        "conflicts", "open_questions", "evidence_packs", "audit_logs",
    ]

    if status == "healthy":
        for table in tables:
            try:
                result = await db.execute(text(f"SELECT COUNT(*) FROM {table}"))
                table_counts[table] = result.scalar()
            except Exception:
                table_counts[table] = "error"

    return {
        "status": status,
        "info": info,
        "table_counts": table_counts if status == "healthy" else None,
    }


@router.get(
    "/health/redis",
    summary="Redis Health Check",
    description="Check Redis connectivity and queue status.",
)
async def redis_health_check() -> dict:
    """Detailed Redis health check."""
    status, info = await _check_redis()

    queue_info = {}
    if status == "healthy":
        try:
            from evidence_repository.queue.connection import (
                get_high_priority_queue,
                get_low_priority_queue,
                get_queue,
            )

            high_q = get_high_priority_queue()
            normal_q = get_queue()
            low_q = get_low_priority_queue()

            queue_info = {
                "high_priority": {
                    "name": high_q.name,
                    "count": len(high_q),
                },
                "normal": {
                    "name": normal_q.name,
                    "count": len(normal_q),
                },
                "low_priority": {
                    "name": low_q.name,
                    "count": len(low_q),
                },
            }
        except Exception as e:
            queue_info = {"error": str(e)}

    return {
        "status": status,
        "info": info,
        "queues": queue_info if status == "healthy" else None,
    }


@router.get(
    "/ready",
    summary="Readiness Check",
    description="Check if the service is ready to accept traffic.",
)
async def readiness_check(
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Check if service is ready.

    Service is ready when:
    - Database is accessible
    - Redis is accessible (for job processing) - optional in serverless mode
    """
    db_status, _ = await _check_database(db)
    redis_status, _ = await _check_redis()

    # In serverless mode, only database is required
    if IS_SERVERLESS:
        ready = db_status == "healthy"
    else:
        ready = db_status == "healthy" and redis_status == "healthy"

    return {
        "ready": ready,
        "checks": {
            "database": db_status == "healthy",
            "redis": redis_status == "healthy" or redis_status.startswith("skipped"),
        },
    }


@router.get(
    "/live",
    summary="Liveness Check",
    description="Check if the service is alive.",
)
async def liveness_check() -> dict:
    """Simple liveness check - just returns OK if the service is running."""
    return {"alive": True}
