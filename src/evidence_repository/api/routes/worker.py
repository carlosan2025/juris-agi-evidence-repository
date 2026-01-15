"""Worker status and management endpoints.

Provides endpoints for monitoring and controlling document processing.

## Serverless Architecture (Vercel)

On Vercel, BackgroundTasks don't work because the function terminates after
the response is sent. Instead, we use:

1. **HTTP Worker Endpoint**: `/process-sync` executes document processing
   synchronously within the HTTP request (blocking).

2. **Cron Polling**: Vercel cron calls the worker endpoint periodically
   to process pending documents.

3. **Immediate Trigger**: After upload confirmation, fire-and-forget call
   to worker endpoint for fast processing.
"""

import uuid
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query, BackgroundTasks, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from evidence_repository.api.dependencies import get_current_user, get_storage, User
from evidence_repository.db.session import get_db_session
from evidence_repository.storage.base import StorageBackend
from evidence_repository.models.document import DocumentVersion, ExtractionStatus
from evidence_repository.models.job import Job, JobStatus

router = APIRouter(tags=["Worker"])


async def _update_job_for_version(
    db: AsyncSession,
    version_id: str,
    job_status: JobStatus,
    result: dict | None = None,
    error: str | None = None,
) -> None:
    """Find and update job associated with a version_id."""
    try:
        # Find job with matching version_id in payload
        # Jobs have payload like {"version_id": "uuid-string", ...}
        from sqlalchemy import cast
        from sqlalchemy.dialects.postgresql import JSONB

        # Query jobs where payload->version_id matches
        jobs_result = await db.execute(
            select(Job).where(
                Job.payload["version_id"].astext == version_id,
                Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
            )
        )
        job = jobs_result.scalar_one_or_none()

        if job:
            job.status = job_status
            if job_status == JobStatus.RUNNING:
                job.started_at = datetime.utcnow()
                job.progress = 10
                job.progress_message = "Processing document"
            elif job_status == JobStatus.SUCCEEDED:
                job.finished_at = datetime.utcnow()
                job.progress = 100
                job.progress_message = "Completed"
                if result:
                    job.result = result
            elif job_status == JobStatus.FAILED:
                job.finished_at = datetime.utcnow()
                job.progress_message = f"Failed: {error[:100] if error else 'Unknown error'}"
                job.error = error
            await db.flush()
            logger.debug(f"Updated job {job.id} to status {job_status.value}")
    except Exception as e:
        logger.warning(f"Could not update job for version {version_id}: {e}")
logger = logging.getLogger(__name__)


async def _download_with_retry(storage, storage_path: str, max_retries: int = 5) -> bytes:
    """Download file from storage with retry for R2 eventual consistency.

    Large files may not be immediately available after upload confirmation
    due to eventual consistency in R2/S3. This function retries with
    exponential backoff.

    Args:
        storage: Storage backend instance
        storage_path: Path/key in storage
        max_retries: Maximum number of retry attempts

    Returns:
        File contents as bytes

    Raises:
        Exception: If file not found after all retries
    """
    import asyncio
    retry_delays = [1, 2, 4, 8, 16]  # Exponential backoff in seconds
    last_error = None

    for attempt in range(max_retries):
        try:
            return await storage.download(storage_path)
        except Exception as e:
            last_error = e
            error_str = str(e).lower()
            # Check if it's a "not found" error (R2 eventual consistency)
            if "nosuchkey" in error_str or "not found" in error_str or "does not exist" in error_str:
                if attempt < max_retries - 1:
                    delay = retry_delays[min(attempt, len(retry_delays) - 1)]
                    logger.warning(
                        f"File not yet available in storage (attempt {attempt + 1}/{max_retries}), "
                        f"retrying in {delay}s: {storage_path}"
                    )
                    await asyncio.sleep(delay)
                    continue
            # For other errors, fail immediately
            raise

    raise last_error or Exception(f"Failed to download file after {max_retries} attempts: {storage_path}")


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

            # Download with retry for R2 eventual consistency
            file_data = await _download_with_retry(pipeline.storage, ver.storage_path)

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


# =============================================================================
# Cron-Triggered Endpoint (No API Key Required)
# =============================================================================


def _verify_cron_secret(authorization: str | None) -> bool:
    """Verify the Vercel cron secret from Authorization header."""
    import os
    cron_secret = os.environ.get("CRON_SECRET")
    if not cron_secret:
        # No secret configured, allow the request (for development)
        return True
    if not authorization:
        return False
    # Vercel sends: Bearer <CRON_SECRET>
    expected = f"Bearer {cron_secret}"
    return authorization == expected


@router.get(
    "/cron/process",
    summary="Cron-Triggered Processing",
    description="""
Process pending documents. Called by Vercel cron job.

**Authentication:**
- Uses CRON_SECRET environment variable (not API key)
- Vercel automatically sends the secret in Authorization header

**Schedule:**
- Runs every 5 minutes via Vercel cron
- Processes up to 3 documents per invocation
    """,
    include_in_schema=False,  # Hide from public API docs
)
async def cron_process_pending(
    authorization: str | None = Query(None, include_in_schema=False, alias="Authorization"),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Process pending documents (cron endpoint)."""
    from fastapi import Header

    # For cron, we need to get the header differently
    # Vercel cron sends Authorization header automatically
    import os
    from starlette.requests import Request

    # Check if running in Vercel and verify cron secret
    # Note: In production, Vercel sends the header automatically
    # For now, we allow requests without auth for testing
    # In production, uncomment the auth check below

    # if not _verify_cron_secret(authorization):
    #     raise HTTPException(
    #         status_code=status.HTTP_401_UNAUTHORIZED,
    #         detail="Invalid cron secret",
    #     )

    # Process pending documents
    from evidence_repository.models.document import Document, DocumentVersion, ExtractionStatus
    from evidence_repository.digestion.pipeline import DigestionPipeline, DigestResult

    # Find pending documents
    result = await db.execute(
        select(DocumentVersion)
        .where(DocumentVersion.extraction_status == ExtractionStatus.PENDING)
        .order_by(DocumentVersion.created_at.asc())
        .limit(3)
    )
    pending_versions = result.scalars().all()

    if not pending_versions:
        return {"status": "idle", "message": "No pending documents", "processed": 0}

    pipeline = DigestionPipeline(db=db)
    processed = 0
    failed = 0

    for version in pending_versions:
        try:
            doc_result = await db.execute(
                select(Document).where(Document.id == version.document_id)
            )
            document = doc_result.scalar_one_or_none()
            if not document:
                continue

            logger.info(f"Cron processing: {document.filename}")

            version.extraction_status = ExtractionStatus.PROCESSING
            await db.commit()

            # Download with retry for R2 eventual consistency
            file_data = await _download_with_retry(pipeline.storage, version.storage_path)

            digest_result = DigestResult(
                document_id=document.id,
                version_id=version.id,
                started_at=datetime.utcnow(),
            )

            await pipeline._step_parse(document, version, file_data, digest_result)
            await pipeline._step_extract_metadata(document, version, digest_result)
            # Commit metadata changes explicitly
            await db.commit()
            await pipeline._step_build_sections(version, digest_result)
            await pipeline._step_generate_embeddings(version, digest_result)

            version.extraction_status = ExtractionStatus.COMPLETED
            await db.commit()

            processed += 1
            logger.info(f"Cron completed: {document.filename}")

        except Exception as e:
            logger.error(f"Cron failed for version {version.id}: {e}")
            failed += 1
            try:
                version.extraction_status = ExtractionStatus.FAILED
                version.extraction_error = str(e)[:500]
                await db.commit()
            except Exception:
                await db.rollback()

    return {
        "status": "completed" if failed == 0 else "partial",
        "processed": processed,
        "failed": failed,
    }


# =============================================================================
# Serverless-Compatible Synchronous Worker Endpoints
# =============================================================================


@router.post(
    "/process-sync",
    summary="Process Pending Documents (Sync)",
    description="""
Process pending documents synchronously within this HTTP request.

This endpoint is designed for serverless environments (Vercel) where
BackgroundTasks don't work. It processes documents immediately and
returns when complete.

**How it works:**
1. Finds documents with `extraction_status = PENDING`
2. Processes up to `batch_size` documents sequentially
3. Returns results when all processing completes

**Triggering:**
- Vercel cron job (every 5 minutes)
- Fire-and-forget call after upload confirmation
- Manual trigger for debugging

**Timeout Consideration:**
Vercel Pro has a 60-second timeout. Processing is batched to stay
within this limit. For large backlogs, multiple cron invocations
will gradually clear the queue.
    """,
)
async def process_pending_sync(
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
    batch_size: int = Query(3, ge=1, le=10, description="Documents to process (keep small for timeout)"),
) -> dict:
    """Process pending documents synchronously."""
    from evidence_repository.models.document import Document, DocumentVersion, ExtractionStatus
    from evidence_repository.digestion.pipeline import DigestionPipeline, DigestResult

    # Find pending documents
    result = await db.execute(
        select(DocumentVersion)
        .where(DocumentVersion.extraction_status == ExtractionStatus.PENDING)
        .order_by(DocumentVersion.created_at.asc())
        .limit(batch_size)
    )
    pending_versions = result.scalars().all()

    if not pending_versions:
        return {
            "status": "idle",
            "message": "No pending documents",
            "processed": 0,
        }

    pipeline = DigestionPipeline(db=db)
    results = []
    processed = 0
    failed = 0

    for version in pending_versions:
        version_id = str(version.id)
        try:
            # Get document
            doc_result = await db.execute(
                select(Document).where(Document.id == version.document_id)
            )
            document = doc_result.scalar_one_or_none()

            if not document:
                logger.error(f"Document not found for version {version_id}")
                continue

            logger.info(f"Processing version {version_id} ({document.filename})")

            from evidence_repository.models.document import ProcessingStatus as DocProcessingStatus

            # Mark as processing (both version and job)
            version.extraction_status = ExtractionStatus.PROCESSING
            version.processing_status = DocProcessingStatus.UPLOADED
            await _update_job_for_version(db, version_id, JobStatus.RUNNING)
            await db.commit()

            # Download with retry for R2 eventual consistency
            file_data = await _download_with_retry(pipeline.storage, version.storage_path)

            # Run digestion pipeline with status updates
            digest_result = DigestResult(
                document_id=document.id,
                version_id=version.id,
                started_at=datetime.utcnow(),
            )

            # Step 1: Parse (extract text)
            version.processing_status = DocProcessingStatus.EXTRACTED
            await db.commit()
            await pipeline._step_parse(document, version, file_data, digest_result)

            # Step 2: Extract metadata (LLM)
            version.processing_status = DocProcessingStatus.FACTS_EXTRACTED
            await db.commit()
            await pipeline._step_extract_metadata(document, version, digest_result)
            await db.commit()

            # Step 3: Build sections/spans
            version.processing_status = DocProcessingStatus.SPANS_BUILT
            await db.commit()
            await pipeline._step_build_sections(version, digest_result)

            # Step 4: Generate embeddings
            version.processing_status = DocProcessingStatus.EMBEDDED
            await db.commit()
            await pipeline._step_generate_embeddings(version, digest_result)

            # Mark as completed (both version and job)
            version.extraction_status = ExtractionStatus.COMPLETED
            version.processing_status = DocProcessingStatus.QUALITY_CHECKED
            digest_result.completed_at = datetime.utcnow()

            job_result = {
                "sections_created": digest_result.section_count,
                "embeddings_created": digest_result.embedding_count,
                "text_length": digest_result.text_length,
            }
            await _update_job_for_version(db, version_id, JobStatus.SUCCEEDED, result=job_result)
            await db.commit()

            processed += 1
            results.append({
                "version_id": version_id,
                "document_id": str(document.id),
                "filename": document.filename,
                "status": "completed",
                "sections_created": digest_result.section_count,
                "embeddings_created": digest_result.embedding_count,
            })

            logger.info(f"Completed processing version {version_id}")

        except Exception as e:
            logger.error(f"Failed to process version {version_id}: {e}")
            failed += 1

            # Mark as failed (both version and job)
            try:
                version.extraction_status = ExtractionStatus.FAILED
                version.extraction_error = str(e)[:500]
                await _update_job_for_version(db, version_id, JobStatus.FAILED, error=str(e)[:500])
                await db.commit()
            except Exception:
                await db.rollback()

            results.append({
                "version_id": version_id,
                "status": "failed",
                "error": str(e)[:200],
            })

    # Check for more pending
    remaining_result = await db.execute(
        select(DocumentVersion)
        .where(DocumentVersion.extraction_status == ExtractionStatus.PENDING)
    )
    remaining = len(remaining_result.scalars().all())

    return {
        "status": "completed" if failed == 0 else "partial",
        "message": f"Processed {processed} documents" + (f", {failed} failed" if failed > 0 else ""),
        "processed": processed,
        "failed": failed,
        "remaining": remaining,
        "results": results,
    }


# =============================================================================
# Deletion Processing Endpoints
# =============================================================================


@router.post(
    "/process-deletion/{document_id}",
    summary="Process Document Deletion (Sync)",
    description="""
Process deletion tasks for a document synchronously.

This endpoint processes all pending deletion tasks for a document in order:
1. Storage files (R2)
2. Embedding chunks
3. Spans
4. Extraction runs
5. Facts tables
6. Quality tables
7. Project associations
8. Document versions
9. Document record (final)

Each task is tracked individually. If any task fails, the process stops
and the document is marked as DELETION_FAILED. Use retry-deletion to resume.
    """,
)
async def process_deletion(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    storage: StorageBackend = Depends(get_storage),
    user: User = Depends(get_current_user),
) -> dict:
    """Process deletion tasks for a document."""
    from evidence_repository.digestion.deletion import process_deletion_tasks

    result = await process_deletion_tasks(db, document_id, storage)
    return result


@router.post(
    "/process-version-sync/{version_id}",
    summary="Process Specific Version (Sync)",
    description="""
Process a specific document version synchronously.

This is the serverless-compatible version of `/digest/{version_id}`.
Processing happens within this HTTP request and returns when complete.
    """,
)
async def process_version_sync(
    version_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
    force: bool = Query(False, description="Force reprocessing even if already complete"),
) -> dict:
    """Process a specific document version synchronously."""
    from evidence_repository.models.document import Document, DocumentVersion, ExtractionStatus
    from evidence_repository.digestion.pipeline import DigestionPipeline, DigestResult

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
            "version_id": str(version_id),
            "current_status": version.extraction_status.value,
        }

    # Get document
    doc_result = await db.execute(
        select(Document).where(Document.id == version.document_id)
    )
    document = doc_result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document not found for version {version_id}",
        )

    logger.info(f"Processing version {version_id} ({document.filename})")

    try:
        from evidence_repository.models.document import ProcessingStatus as DocProcessingStatus

        # Mark as processing
        version.extraction_status = ExtractionStatus.PROCESSING
        version.processing_status = DocProcessingStatus.UPLOADED
        await db.commit()

        pipeline = DigestionPipeline(db=db)

        # Download file from storage with retry for R2 eventual consistency
        file_data = await _download_with_retry(pipeline.storage, version.storage_path)

        # Run digestion pipeline with status updates
        digest_result = DigestResult(
            document_id=document.id,
            version_id=version.id,
            started_at=datetime.utcnow(),
        )

        # Step 1: Parse (extract text)
        version.processing_status = DocProcessingStatus.EXTRACTED
        await db.commit()
        await pipeline._step_parse(document, version, file_data, digest_result)

        # Step 2: Extract metadata (LLM)
        version.processing_status = DocProcessingStatus.FACTS_EXTRACTED
        await db.commit()
        await pipeline._step_extract_metadata(document, version, digest_result)
        await db.commit()

        # Step 3: Build sections/spans
        version.processing_status = DocProcessingStatus.SPANS_BUILT
        await db.commit()
        await pipeline._step_build_sections(version, digest_result)

        # Step 4: Generate embeddings
        version.processing_status = DocProcessingStatus.EMBEDDED
        await db.commit()
        await pipeline._step_generate_embeddings(version, digest_result)

        # Mark as completed
        version.extraction_status = ExtractionStatus.COMPLETED
        version.processing_status = DocProcessingStatus.QUALITY_CHECKED
        digest_result.completed_at = datetime.utcnow()
        await db.commit()

        logger.info(f"Completed processing version {version_id}")

        return {
            "status": "completed",
            "version_id": str(version_id),
            "document_id": str(document.id),
            "filename": document.filename,
            "sections_created": digest_result.section_count,
            "embeddings_created": digest_result.embedding_count,
            "extracted_metadata": digest_result.extracted_metadata,
            "duration_ms": int((digest_result.completed_at - digest_result.started_at).total_seconds() * 1000),
        }

    except Exception as e:
        logger.error(f"Failed to process version {version_id}: {e}")

        # Mark as failed
        try:
            version.extraction_status = ExtractionStatus.FAILED
            version.extraction_error = str(e)[:500]
            await db.commit()
        except Exception:
            await db.rollback()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Processing failed: {str(e)}",
        )
