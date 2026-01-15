"""Job management and async processing endpoints."""

import base64
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status

from evidence_repository.api.dependencies import User, get_current_user
from evidence_repository.config import get_settings
from evidence_repository.models.job import JobStatus as DBJobStatus, JobType as DBJobType
from evidence_repository.queue.job_queue import JobQueue, get_job_queue
from evidence_repository.queue.jobs import JobManager, JobStatus, JobType, get_job_manager
from evidence_repository.schemas.job import (
    BatchEmbedRequest,
    BatchExtractRequest,
    BulkFolderIngestRequest,
    BulkJobEnqueueResponse,
    JobEnqueueRequest,
    JobEnqueueResponse,
    JobListResponse,
    JobResponse,
    URLIngestRequest,
)

router = APIRouter()


# =============================================================================
# Generic Job Enqueue Endpoint
# =============================================================================


@router.post(
    "/enqueue",
    response_model=JobEnqueueResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Enqueue Job",
    description="""
Enqueue a job for background processing. Jobs are persisted to the database
and processed by workers asynchronously.

**Supported Job Types:**
- `document_ingest` - Ingest a document (requires file_data, filename, content_type)
- `document_extract` - Extract text from a document (requires document_id)
- `document_embed` - Generate embeddings for a document (requires document_id)
- `document_process_full` - Full processing pipeline (requires file_data, filename, content_type)
- `bulk_folder_ingest` - Ingest files from a folder (requires folder_path)
- `bulk_url_ingest` - Download and ingest from URL (requires url)

**Priority:**
- priority >= 10: Uses high priority queue
- priority < 0: Uses low priority queue
- Otherwise: Uses normal queue
    """,
)
async def enqueue_job(
    request: JobEnqueueRequest,
    user: User = Depends(get_current_user),
) -> JobEnqueueResponse:
    """Enqueue a job for background processing."""
    # Validate job type
    try:
        job_type = DBJobType(request.type)
    except ValueError:
        valid_types = [jt.value for jt in DBJobType]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid job type: {request.type}. Valid types: {valid_types}",
        )

    # Add user context to payload
    payload = {**request.payload, "user_id": user.id}

    # Enqueue using the new JobQueue (database-backed)
    job_queue = get_job_queue()
    job_id = job_queue.enqueue(
        job_type=job_type,
        payload=payload,
        priority=request.priority,
    )

    return JobEnqueueResponse(
        job_id=job_id,
        job_type=job_type.value,
        status="queued",
        message=f"Job enqueued successfully",
    )


# =============================================================================
# Job Status Endpoints
# =============================================================================


@router.get(
    "/{job_id}",
    response_model=JobResponse,
    summary="Get Job Status",
    description="Get the current status and details of a job from the database.",
)
async def get_job_status(
    job_id: str,
    user: User = Depends(get_current_user),
) -> JobResponse:
    """Get job status by ID from the database."""
    job_queue = get_job_queue()
    job_info = job_queue.get_status(job_id)

    if not job_info:
        # Fall back to the old job manager for backwards compatibility
        job_manager = get_job_manager()
        job_info_old = job_manager.get_job_info(job_id)

        if not job_info_old:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job {job_id} not found",
            )

        return JobResponse(
            job_id=job_info_old.job_id,
            job_type=job_info_old.job_type.value,
            status=job_info_old.status.value,
            created_at=job_info_old.created_at,
            started_at=job_info_old.started_at,
            ended_at=job_info_old.ended_at,
            result=job_info_old.result,
            error=job_info_old.error,
            progress=job_info_old.progress,
            progress_message=job_info_old.progress_message,
            metadata=job_info_old.metadata,
        )

    return JobResponse(
        job_id=job_info["job_id"],
        job_type=job_info["type"],
        status=job_info["status"],
        created_at=job_info["created_at"],
        started_at=job_info["started_at"],
        ended_at=job_info["finished_at"],
        result=job_info["result"],
        error=job_info["error"],
        progress=job_info["progress"],
        progress_message=job_info["progress_message"],
        metadata={"payload": job_info.get("payload", {})},
    )


@router.get(
    "",
    response_model=JobListResponse,
    summary="List Jobs",
    description="List jobs from the database with optional filtering.",
)
async def list_jobs(
    job_type: str | None = Query(None, description="Filter by job type"),
    status_filter: str | None = Query(None, alias="status", description="Filter by status"),
    limit: int = Query(default=50, ge=1, le=200, description="Maximum jobs to return"),
    offset: int = Query(default=0, ge=0, description="Offset for pagination"),
    user: User = Depends(get_current_user),
) -> JobListResponse:
    """List jobs from the database with optional filters."""
    job_queue = get_job_queue()

    jobs = job_queue.list_jobs(
        job_type=job_type,
        status=status_filter,
        limit=limit,
        offset=offset,
    )

    job_responses = [
        JobResponse(
            job_id=j["job_id"],
            job_type=j["type"],
            status=j["status"],
            created_at=j["created_at"],
            started_at=j["started_at"],
            ended_at=j["finished_at"],
            result=None,  # Not included in list for performance
            error=j["error"],
            progress=j["progress"],
            progress_message=j["progress_message"],
            metadata={},
        )
        for j in jobs
    ]

    return JobListResponse(jobs=job_responses, total=len(job_responses))


@router.delete(
    "/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Job",
    description="Delete a job. Can delete queued, succeeded, failed, or canceled jobs. Cannot delete running jobs.",
)
async def delete_job(
    job_id: str,
    user: User = Depends(get_current_user),
) -> None:
    """Delete a job from the database."""
    job_queue = get_job_queue()

    if not job_queue.delete_job(job_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Job not found or cannot be deleted (may be currently running)",
        )


@router.post(
    "/{job_id}/cancel",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cancel Job",
    description="Cancel a queued job (cannot cancel running jobs).",
)
async def cancel_job(
    job_id: str,
    user: User = Depends(get_current_user),
) -> None:
    """Cancel a queued job."""
    job_queue = get_job_queue()

    if not job_queue.cancel_job(job_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Job not found or cannot be canceled (may already be running)",
        )


@router.delete(
    "/cleanup/stale",
    summary="Delete Stale Jobs",
    description="Delete stale queued/running jobs older than specified hours.",
)
async def delete_stale_jobs(
    max_age_hours: int = Query(24, ge=1, le=168, description="Max age in hours for stale jobs"),
    user: User = Depends(get_current_user),
) -> dict:
    """Delete stale jobs that are stuck in queued/running state."""
    job_queue = get_job_queue()
    deleted = job_queue.delete_stale_jobs(max_age_hours)
    return {"deleted": deleted, "message": f"Deleted {deleted} stale jobs"}


@router.delete(
    "/cleanup/old",
    summary="Delete Old Completed Jobs",
    description="Delete old completed jobs to clean up the database.",
)
async def delete_old_jobs(
    max_age_days: int = Query(7, ge=1, le=90, description="Max age in days for completed jobs"),
    user: User = Depends(get_current_user),
) -> dict:
    """Delete old completed jobs."""
    job_queue = get_job_queue()
    deleted = job_queue.cleanup_completed_jobs(max_age_days)
    return {"deleted": deleted, "message": f"Deleted {deleted} old completed jobs"}


@router.post(
    "/{job_id}/run",
    response_model=JobResponse,
    summary="Run Job Synchronously",
    description="""
Run a queued job synchronously and wait for completion.

This endpoint is for serverless environments (Vercel) where background tasks
don't work. The job will be executed immediately and the response will contain
the result.

**Note:** This endpoint blocks until the job completes. Use with caution for
long-running jobs as it may timeout.
    """,
)
async def run_job_sync(
    job_id: str,
    user: User = Depends(get_current_user),
) -> JobResponse:
    """Run a queued job synchronously."""
    import uuid
    from datetime import datetime, timezone
    from sqlalchemy import select, create_engine
    from sqlalchemy.orm import sessionmaker

    from evidence_repository.config import get_settings
    from evidence_repository.models.job import Job, JobStatus as DBJobStatus
    from evidence_repository.queue.tasks import task_process_document_version

    settings = get_settings()

    # Create sync database session
    sync_url = settings.database_url.replace("postgresql+asyncpg://", "postgresql+psycopg://")
    sync_url = sync_url.replace("ssl=require", "sslmode=require")
    sync_url = sync_url.replace("ssl=true", "sslmode=require")
    engine = create_engine(sync_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        # Load job from database
        job_uuid = uuid.UUID(job_id)
        job = db.execute(
            select(Job).where(Job.id == job_uuid)
        ).scalar_one_or_none()

        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job {job_id} not found",
            )

        if job.status != DBJobStatus.QUEUED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Job is not queued (status: {job.status.value})",
            )

        # Update status to RUNNING
        job.status = DBJobStatus.RUNNING
        job.started_at = datetime.now(timezone.utc)
        job.worker_id = "serverless-sync"
        job.attempts += 1
        job.progress = 0
        job.progress_message = "Starting synchronous execution"
        db.commit()

        # Execute the job based on type
        try:
            payload = job.payload or {}

            # Progress callback
            def update_progress(progress: float, message: str | None = None) -> None:
                try:
                    job.progress = int(min(100, max(0, progress)))
                    if message:
                        job.progress_message = message
                    db.commit()
                except Exception:
                    pass

            if job.type.value == "process_document_version":
                result = task_process_document_version(
                    version_id=payload.get("version_id"),
                    profile_code=payload.get("profile_code", "general"),
                    extraction_level=payload.get("extraction_level", 2),
                    reprocess=payload.get("reprocess", False),
                )
            else:
                raise ValueError(f"Synchronous execution not supported for job type: {job.type.value}")

            # Update status to SUCCEEDED
            job.status = DBJobStatus.SUCCEEDED
            job.finished_at = datetime.now(timezone.utc)
            job.progress = 100
            job.progress_message = "Job completed successfully"
            job.result = result
            job.error = None
            db.commit()

        except Exception as e:
            # Update status to FAILED
            job.status = DBJobStatus.FAILED
            job.finished_at = datetime.now(timezone.utc)
            job.error = str(e)
            job.progress_message = f"Failed: {str(e)[:200]}"
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Job execution failed: {str(e)}",
            )

        return JobResponse(
            job_id=str(job.id),
            job_type=job.type.value,
            status=job.status.value,
            created_at=job.created_at.isoformat() if job.created_at else None,
            started_at=job.started_at.isoformat() if job.started_at else None,
            ended_at=job.finished_at.isoformat() if job.finished_at else None,
            result=job.result,
            error=job.error,
            progress=job.progress,
            progress_message=job.progress_message,
            metadata={"payload": job.payload},
        )

    finally:
        db.close()


@router.post(
    "/process-next",
    response_model=JobResponse | dict,
    summary="Process Next Queued Job",
    description="""
Process the next queued job synchronously.

This endpoint is designed for serverless environments (Vercel) where cron jobs
trigger processing. It picks up the oldest queued job and executes it.

**Returns:**
- Job result if a job was processed
- `{"status": "idle", "message": "No queued jobs"}` if queue is empty
    """,
)
async def process_next_job(
    user: User = Depends(get_current_user),
) -> JobResponse | dict:
    """Process the next queued job synchronously."""
    import uuid
    from datetime import datetime, timezone
    from sqlalchemy import select, create_engine
    from sqlalchemy.orm import sessionmaker

    from evidence_repository.config import get_settings
    from evidence_repository.models.job import Job, JobStatus as DBJobStatus
    from evidence_repository.queue.tasks import task_process_document_version

    settings = get_settings()

    # Create sync database session
    sync_url = settings.database_url.replace("postgresql+asyncpg://", "postgresql+psycopg://")
    sync_url = sync_url.replace("ssl=require", "sslmode=require")
    sync_url = sync_url.replace("ssl=true", "sslmode=require")
    engine = create_engine(sync_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        # Find oldest queued job
        job = db.execute(
            select(Job)
            .where(Job.status == DBJobStatus.QUEUED)
            .order_by(Job.priority.desc(), Job.created_at.asc())
            .limit(1)
        ).scalar_one_or_none()

        if not job:
            return {"status": "idle", "message": "No queued jobs"}

        # Update status to RUNNING
        job.status = DBJobStatus.RUNNING
        job.started_at = datetime.now(timezone.utc)
        job.worker_id = "serverless-cron"
        job.attempts += 1
        job.progress = 0
        job.progress_message = "Starting cron execution"
        db.commit()

        # Execute the job based on type
        try:
            payload = job.payload or {}

            if job.type.value == "process_document_version":
                result = task_process_document_version(
                    version_id=payload.get("version_id"),
                    profile_code=payload.get("profile_code", "general"),
                    extraction_level=payload.get("extraction_level", 2),
                    reprocess=payload.get("reprocess", False),
                )
            else:
                raise ValueError(f"Synchronous execution not supported for job type: {job.type.value}")

            # Update status to SUCCEEDED
            job.status = DBJobStatus.SUCCEEDED
            job.finished_at = datetime.now(timezone.utc)
            job.progress = 100
            job.progress_message = "Job completed successfully"
            job.result = result
            job.error = None
            db.commit()

        except Exception as e:
            # Update status to FAILED
            job.status = DBJobStatus.FAILED
            job.finished_at = datetime.now(timezone.utc)
            job.error = str(e)
            job.progress_message = f"Failed: {str(e)[:200]}"
            db.commit()

        return JobResponse(
            job_id=str(job.id),
            job_type=job.type.value,
            status=job.status.value,
            created_at=job.created_at.isoformat() if job.created_at else None,
            started_at=job.started_at.isoformat() if job.started_at else None,
            ended_at=job.finished_at.isoformat() if job.finished_at else None,
            result=job.result,
            error=job.error,
            progress=job.progress,
            progress_message=job.progress_message,
            metadata={"payload": job.payload},
        )

    finally:
        db.close()


# =============================================================================
# Async Document Upload
# =============================================================================


@router.post(
    "/upload",
    response_model=JobEnqueueResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload Document (Async)",
    description="Upload a document for asynchronous processing. Returns immediately with job ID.",
)
async def upload_document_async(
    file: UploadFile = File(..., description="Document file to upload"),
    process_full: bool = Query(default=True, description="Run full processing pipeline"),
    skip_embedding: bool = Query(default=False, description="Skip embedding generation"),
    user: User = Depends(get_current_user),
) -> JobEnqueueResponse:
    """Upload document for async processing."""
    settings = get_settings()

    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required",
        )

    # Check file extension
    from pathlib import Path
    extension = Path(file.filename).suffix.lower()
    if extension not in settings.supported_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: {extension}. Supported: {settings.supported_extensions}",
        )

    # Read file content
    content = await file.read()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty file",
        )

    # Check file size
    max_size = settings.max_file_size_mb * 1024 * 1024
    if len(content) > max_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large ({len(content)} bytes). Maximum: {max_size} bytes",
        )

    # Enqueue job
    job_manager = get_job_manager()

    if process_full:
        job_id = job_manager.enqueue(
            job_type=JobType.DOCUMENT_PROCESS_FULL,
            func="evidence_repository.queue.tasks.task_process_document_full",
            file_data=content,
            filename=file.filename,
            content_type=file.content_type or "application/octet-stream",
            user_id=user.id,
            skip_embedding=skip_embedding,
            priority="normal",
            metadata={"filename": file.filename},
        )
    else:
        job_id = job_manager.enqueue(
            job_type=JobType.DOCUMENT_INGEST,
            func="evidence_repository.queue.tasks.task_ingest_document",
            file_data=content,
            filename=file.filename,
            content_type=file.content_type or "application/octet-stream",
            user_id=user.id,
            priority="normal",
            metadata={"filename": file.filename},
        )

    return JobEnqueueResponse(
        job_id=job_id,
        job_type=JobType.DOCUMENT_PROCESS_FULL.value if process_full else JobType.DOCUMENT_INGEST.value,
        status="queued",
        message=f"Document '{file.filename}' queued for processing",
    )


# =============================================================================
# Bulk Ingestion Endpoints
# =============================================================================


@router.post(
    "/ingest/folder",
    response_model=JobEnqueueResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Bulk Ingest from Folder",
    description="Scan a local folder and ingest all supported files.",
)
async def bulk_ingest_folder(
    request: BulkFolderIngestRequest,
    user: User = Depends(get_current_user),
) -> JobEnqueueResponse:
    """Enqueue bulk folder ingestion job."""
    from pathlib import Path

    # Validate folder exists
    folder = Path(request.folder_path)
    if not folder.exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Folder not found: {request.folder_path}",
        )
    if not folder.is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Not a directory: {request.folder_path}",
        )

    job_manager = get_job_manager()

    job_id = job_manager.enqueue(
        job_type=JobType.BULK_FOLDER_INGEST,
        func="evidence_repository.queue.tasks.task_bulk_folder_ingest",
        folder_path=request.folder_path,
        recursive=request.recursive,
        user_id=user.id,
        process_full=request.process_full,
        priority="low",  # Bulk jobs are low priority
        metadata={
            "folder_path": request.folder_path,
            "recursive": request.recursive,
        },
    )

    return JobEnqueueResponse(
        job_id=job_id,
        job_type=JobType.BULK_FOLDER_INGEST.value,
        status="queued",
        message=f"Bulk ingestion from '{request.folder_path}' queued",
    )


@router.post(
    "/ingest/url",
    response_model=JobEnqueueResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest from URL",
    description="Download and ingest a file from a URL.",
)
async def ingest_from_url(
    request: URLIngestRequest,
    user: User = Depends(get_current_user),
) -> JobEnqueueResponse:
    """Enqueue URL ingestion job."""
    # Basic URL validation
    if not request.url.startswith(("http://", "https://")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="URL must start with http:// or https://",
        )

    job_manager = get_job_manager()

    job_id = job_manager.enqueue(
        job_type=JobType.BULK_URL_INGEST,
        func="evidence_repository.queue.tasks.task_ingest_from_url",
        url=request.url,
        filename=request.filename,
        user_id=user.id,
        process_full=request.process_full,
        priority="normal",
        metadata={"url": request.url},
    )

    return JobEnqueueResponse(
        job_id=job_id,
        job_type=JobType.BULK_URL_INGEST.value,
        status="queued",
        message=f"URL ingestion queued: {request.url}",
    )


# =============================================================================
# Batch Processing Endpoints
# =============================================================================


@router.post(
    "/batch/extract",
    response_model=BulkJobEnqueueResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Batch Extract Documents",
    description="Trigger text extraction for multiple documents.",
)
async def batch_extract(
    request: BatchExtractRequest,
    user: User = Depends(get_current_user),
) -> BulkJobEnqueueResponse:
    """Enqueue batch extraction jobs."""
    job_manager = get_job_manager()

    job_ids = []
    for doc_id in request.document_ids:
        job_id = job_manager.enqueue(
            job_type=JobType.DOCUMENT_EXTRACT,
            func="evidence_repository.queue.tasks.task_extract_document",
            document_id=doc_id,
            priority="low",
            metadata={"document_id": doc_id},
        )
        job_ids.append(job_id)

    return BulkJobEnqueueResponse(
        job_ids=job_ids,
        total_jobs=len(job_ids),
        message=f"Queued {len(job_ids)} extraction jobs",
    )


@router.post(
    "/batch/embed",
    response_model=BulkJobEnqueueResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Batch Embed Documents",
    description="Generate embeddings for multiple documents.",
)
async def batch_embed(
    request: BatchEmbedRequest,
    user: User = Depends(get_current_user),
) -> BulkJobEnqueueResponse:
    """Enqueue batch embedding jobs."""
    job_manager = get_job_manager()

    job_ids = []
    for doc_id in request.document_ids:
        job_id = job_manager.enqueue(
            job_type=JobType.DOCUMENT_EMBED,
            func="evidence_repository.queue.tasks.task_embed_document",
            document_id=doc_id,
            priority="low",
            metadata={"document_id": doc_id},
        )
        job_ids.append(job_id)

    return BulkJobEnqueueResponse(
        job_ids=job_ids,
        total_jobs=len(job_ids),
        message=f"Queued {len(job_ids)} embedding jobs",
    )
