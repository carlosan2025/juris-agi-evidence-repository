"""Task runner that wraps job execution with database updates.

This module provides the entry point for RQ workers. When a job is executed,
the task runner:
1. Loads the job from the database
2. Updates status to RUNNING
3. Executes the appropriate task function
4. Updates status to SUCCEEDED/FAILED
5. Stores result or error
"""

import logging
import socket
import traceback
import uuid
from datetime import datetime, timezone
from typing import Any

from rq import get_current_job
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from evidence_repository.config import get_settings
from evidence_repository.models.job import Job, JobStatus, JobType

logger = logging.getLogger(__name__)


def _get_sync_db_session() -> Session:
    """Get synchronous database session for worker tasks."""
    settings = get_settings()
    sync_url = settings.database_url.replace("+asyncpg", "")
    engine = create_engine(sync_url)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def _get_worker_id() -> str:
    """Generate a worker identifier."""
    hostname = socket.gethostname()
    rq_job = get_current_job()
    worker_name = rq_job.worker_name if rq_job else "unknown"
    return f"{hostname}:{worker_name}"


def run_job(job_id: str) -> dict[str, Any]:
    """Run a job from the database.

    This is the main entry point for RQ workers. It:
    1. Loads the job record from the database
    2. Updates status to RUNNING with worker ID
    3. Dispatches to the appropriate task function
    4. Updates status to SUCCEEDED/FAILED with result/error

    Args:
        job_id: Job UUID string.

    Returns:
        Job result dict.
    """
    db = _get_sync_db_session()
    worker_id = _get_worker_id()

    try:
        # Load job from database
        job_uuid = uuid.UUID(job_id)
        job = db.execute(
            select(Job).where(Job.id == job_uuid)
        ).scalar_one_or_none()

        if not job:
            raise ValueError(f"Job {job_id} not found in database")

        logger.info(f"Starting job {job_id} type={job.type.value} worker={worker_id}")

        # Update status to RUNNING
        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(timezone.utc)
        job.worker_id = worker_id
        job.attempts += 1
        job.progress = 0
        job.progress_message = "Starting job execution"
        db.commit()

        # Dispatch to appropriate task function
        result = _dispatch_job(job, db)

        # Update status to SUCCEEDED
        job.status = JobStatus.SUCCEEDED
        job.finished_at = datetime.now(timezone.utc)
        job.progress = 100
        job.progress_message = "Job completed successfully"
        job.result = result
        job.error = None
        db.commit()

        logger.info(f"Job {job_id} completed successfully")
        return result

    except Exception as e:
        logger.error(f"Job {job_id} failed: {e}")
        logger.error(traceback.format_exc())

        # Update status to FAILED
        try:
            if job:
                job.status = JobStatus.FAILED
                job.finished_at = datetime.now(timezone.utc)
                job.error = str(e)
                job.progress_message = f"Failed: {str(e)[:200]}"
                db.commit()
        except Exception as db_error:
            logger.error(f"Failed to update job status: {db_error}")

        raise

    finally:
        db.close()


def _dispatch_job(job: Job, db: Session) -> dict[str, Any]:
    """Dispatch a job to its task function.

    Args:
        job: Job record from database.
        db: Database session for progress updates.

    Returns:
        Task result dict.
    """
    # Import task functions here to avoid circular imports
    from evidence_repository.queue.tasks import (
        task_batch_folder_ingest,
        task_batch_url_ingest,
        task_bulk_folder_ingest,
        task_embed_document,
        task_extract_document,
        task_ingest_document,
        task_ingest_from_url,
        task_multilevel_extract,
        task_multilevel_extract_batch,
        task_process_document_full,
        task_process_document_version,
        task_upgrade_extraction_level,
    )

    payload = job.payload or {}

    # Create a progress callback that updates the database
    def update_progress(progress: float, message: str | None = None) -> None:
        """Update job progress in database."""
        try:
            job.progress = int(min(100, max(0, progress)))
            if message:
                job.progress_message = message
            db.commit()
        except Exception as e:
            logger.warning(f"Failed to update progress: {e}")

    # Inject progress callback into payload
    payload["_update_progress"] = update_progress
    payload["_job_id"] = str(job.id)

    # Dispatch based on job type
    if job.type == JobType.DOCUMENT_INGEST:
        return _run_task(task_ingest_document, payload, [
            "file_data", "filename", "content_type", "metadata", "user_id"
        ])

    elif job.type == JobType.DOCUMENT_EXTRACT:
        return _run_task(task_extract_document, payload, [
            "document_id", "version_id"
        ])

    elif job.type == JobType.DOCUMENT_EMBED:
        return _run_task(task_embed_document, payload, [
            "document_id", "version_id"
        ])

    elif job.type == JobType.DOCUMENT_PROCESS_FULL:
        return _run_task(task_process_document_full, payload, [
            "file_data", "filename", "content_type", "metadata", "user_id", "skip_embedding"
        ])

    elif job.type == JobType.BULK_FOLDER_INGEST:
        # Check if this is a batch job (has batch_id) or legacy job
        if "batch_id" in payload:
            return _run_task(task_batch_folder_ingest, payload, [
                "batch_id", "folder_path", "project_id", "auto_process", "user_id"
            ])
        else:
            return _run_task(task_bulk_folder_ingest, payload, [
                "folder_path", "recursive", "user_id", "process_full"
            ])

    elif job.type == JobType.BULK_URL_INGEST:
        # Check if this is a batch job (has batch_id) or legacy job
        if "batch_id" in payload:
            return _run_task(task_batch_url_ingest, payload, [
                "batch_id", "item_id", "url", "filename", "project_id", "auto_process", "user_id"
            ])
        else:
            return _run_task(task_ingest_from_url, payload, [
                "url", "filename", "user_id", "process_full"
            ])

    elif job.type in (JobType.BATCH_EXTRACT, JobType.BATCH_EMBED):
        # These reuse individual document tasks
        if job.type == JobType.BATCH_EXTRACT:
            return _run_task(task_extract_document, payload, ["document_id", "version_id"])
        else:
            return _run_task(task_embed_document, payload, ["document_id", "version_id"])

    elif job.type == JobType.PROCESS_DOCUMENT_VERSION:
        return _run_task(task_process_document_version, payload, [
            "version_id", "project_id", "profile_code", "process_context",
            "extraction_level", "skip_extraction", "skip_spans", "skip_embeddings",
            "skip_facts", "skip_quality", "reprocess"
        ])

    elif job.type == JobType.FACT_EXTRACT:
        # Fact extraction reuses the version pipeline but only runs fact step
        return _run_task(task_process_document_version, payload, [
            "version_id", "project_id", "profile_code", "process_context",
            "extraction_level", "skip_extraction", "skip_spans", "skip_embeddings",
            "skip_quality"
        ])

    elif job.type == JobType.QUALITY_CHECK:
        # Quality check reuses the version pipeline but only runs quality step
        return _run_task(task_process_document_version, payload, [
            "version_id", "project_id", "process_context", "skip_extraction",
            "skip_spans", "skip_embeddings", "skip_facts"
        ])

    elif job.type == JobType.MULTILEVEL_EXTRACT:
        # Multi-level extraction with process_context support
        return _run_task(task_multilevel_extract, payload, [
            "version_id", "profile_code", "process_context", "level",
            "triggered_by", "compute_missing_levels", "schema_version", "vocab_version"
        ])

    elif job.type == JobType.MULTILEVEL_EXTRACT_BATCH:
        # Batch multi-level extraction
        return _run_task(task_multilevel_extract_batch, payload, [
            "version_ids", "profile_code", "process_context", "level",
            "triggered_by", "schema_version", "vocab_version"
        ])

    elif job.type == JobType.UPGRADE_EXTRACTION_LEVEL:
        # Upgrade extraction to higher level
        return _run_task(task_upgrade_extraction_level, payload, [
            "version_id", "profile_code", "process_context", "target_level",
            "triggered_by", "schema_version", "vocab_version"
        ])

    else:
        raise ValueError(f"Unknown job type: {job.type}")


def _run_task(
    task_func: callable,
    payload: dict[str, Any],
    allowed_params: list[str],
) -> dict[str, Any]:
    """Run a task function with filtered payload.

    Args:
        task_func: Task function to call.
        payload: Full payload dict.
        allowed_params: Parameter names to pass to function.

    Returns:
        Task result.
    """
    # Filter payload to only include allowed parameters
    filtered = {k: payload[k] for k in allowed_params if k in payload}
    return task_func(**filtered)
