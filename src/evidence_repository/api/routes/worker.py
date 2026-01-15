"""Worker status and management endpoints.

Provides endpoints for monitoring and controlling document processing.
"""

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query, BackgroundTasks, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from evidence_repository.api.dependencies import get_current_user, User
from evidence_repository.db.session import get_db_session

router = APIRouter(tags=["Worker"])


@router.get(
    "/status",
    summary="Get Worker Status",
    description="Get current processing queue status and statistics.",
)
async def get_worker_status(
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
    detailed: bool = Query(False, description="Include detailed statistics"),
) -> dict:
    """Get worker queue status.

    Returns counts of documents in each processing state and
    recent activity metrics.
    """
    if detailed:
        from evidence_repository.digestion.status import get_processing_stats
        stats = await get_processing_stats(db)
        return stats.to_dict()
    else:
        from evidence_repository.digestion.status import get_queue_status
        return await get_queue_status(db)


@router.get(
    "/version/{version_id}/status",
    summary="Get Version Processing Status",
    description="Get processing status for a specific document version.",
)
async def get_version_status(
    version_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> dict:
    """Get processing status for a document version."""
    from evidence_repository.digestion.status import get_version_status

    result = await get_version_status(db, str(version_id))
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Version {version_id} not found",
        )
    return result


@router.post(
    "/process",
    summary="Trigger Processing",
    description="Manually trigger processing of pending documents.",
)
async def trigger_processing(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
    batch_size: int = Query(5, ge=1, le=50, description="Documents to process"),
    chain: bool = Query(True, description="Continue processing remaining documents"),
) -> dict:
    """Trigger processing of pending documents.

    If chain=True, will continue processing until queue is empty
    (self-triggering chain pattern).

    Returns immediately while processing continues in background.
    """
    from evidence_repository.digestion.pipeline import digest_pending_documents
    from evidence_repository.digestion.status import get_queue_status

    # Get current status
    queue_status = await get_queue_status(db)
    pending = queue_status["queue"].get("pending", 0)

    if pending == 0:
        return {
            "status": "idle",
            "message": "No documents pending",
            "queue": queue_status["queue"],
        }

    # Process batch in background
    async def process_batch():
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from sqlalchemy.orm import sessionmaker
        from evidence_repository.config import get_settings

        settings = get_settings()
        engine = create_async_engine(settings.database_url)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with async_session() as session:
            results = await digest_pending_documents(session, batch_size)

            # Self-triggering: if more pending and chain enabled
            if chain:
                from evidence_repository.digestion.status import get_queue_status
                status = await get_queue_status(session)
                remaining = status["queue"].get("pending", 0)

                if remaining > 0:
                    # Fire next batch (in production, would use proper task queue)
                    await digest_pending_documents(session, batch_size)

            return results

    background_tasks.add_task(process_batch)

    return {
        "status": "processing",
        "message": f"Processing up to {batch_size} documents",
        "pending_before": pending,
        "chain_enabled": chain,
    }


@router.post(
    "/retry-failed",
    summary="Retry Failed Documents",
    description="Reset failed documents to pending for retry.",
)
async def retry_failed(
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
    limit: int = Query(10, ge=1, le=100, description="Maximum documents to retry"),
    older_than_hours: int = Query(1, ge=0, le=168, description="Only retry if failed before this many hours ago"),
) -> dict:
    """Reset failed documents to pending status.

    Only resets documents that failed at least `older_than_hours` ago
    to avoid immediate retry loops.
    """
    from evidence_repository.digestion.status import retry_failed_documents

    count = await retry_failed_documents(
        db=db,
        limit=limit,
        older_than_hours=older_than_hours,
    )

    return {
        "status": "success",
        "documents_reset": count,
        "message": f"Reset {count} documents to pending",
    }


@router.post(
    "/digest/{version_id}",
    summary="Digest Specific Version",
    description="Manually trigger digestion for a specific document version.",
)
async def digest_version(
    version_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
    force: bool = Query(False, description="Force reprocessing even if already complete"),
) -> dict:
    """Trigger digestion for a specific document version.

    Useful for reprocessing documents or manually triggering
    processing of specific files.
    """
    from sqlalchemy import select
    from evidence_repository.models.document import Document, DocumentVersion, ExtractionStatus

    # Get version
    result = await db.execute(
        select(DocumentVersion).where(DocumentVersion.id == version_id)
    )
    version = result.scalar_one_or_none()

    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Version {version_id} not found",
        )

    if version.extraction_status == ExtractionStatus.COMPLETED and not force:
        return {
            "status": "skipped",
            "message": "Version already processed (use force=true to reprocess)",
            "current_status": version.extraction_status.value,
        }

    # Get document
    doc_result = await db.execute(
        select(Document).where(Document.id == version.document_id)
    )
    document = doc_result.scalar_one()

    # Process in background
    async def process_version():
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from sqlalchemy.orm import sessionmaker
        from evidence_repository.config import get_settings
        from evidence_repository.digestion.pipeline import DigestionPipeline, DigestResult

        settings = get_settings()
        engine = create_async_engine(settings.database_url)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with async_session() as session:
            # Reload version in new session
            ver = await session.get(DocumentVersion, version_id)
            doc = await session.get(Document, ver.document_id)

            pipeline = DigestionPipeline(db=session)

            # Download and process
            file_data = await pipeline.storage.download(ver.storage_path)

            result = DigestResult(
                document_id=doc.id,
                version_id=ver.id,
                started_at=datetime.utcnow(),
            )

            await pipeline._step_parse(doc, ver, file_data, result)
            await pipeline._step_build_sections(ver, result)
            await pipeline._step_generate_embeddings(ver, result)

            ver.extraction_status = ExtractionStatus.COMPLETED
            await session.commit()

    background_tasks.add_task(process_version)

    return {
        "status": "processing",
        "version_id": str(version_id),
        "document_id": str(document.id),
        "filename": document.filename,
        "message": "Processing started in background",
    }
