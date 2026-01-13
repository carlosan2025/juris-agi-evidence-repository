"""JobQueue abstraction with database persistence.

This module provides a unified interface for enqueueing jobs that:
1. Creates a persistent job record in the database
2. Enqueues the job to Redis/RQ for processing
3. Tracks status transitions and progress

Workers update the database job record at each processing step.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from redis import Redis
from rq import Queue
from rq.job import Job as RQJob
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session, sessionmaker

from evidence_repository.config import get_settings
from evidence_repository.models.job import Job, JobStatus, JobType
from evidence_repository.queue.connection import (
    get_high_priority_queue,
    get_low_priority_queue,
    get_queue,
    get_redis_connection,
)

logger = logging.getLogger(__name__)


class JobQueue:
    """Unified job queue with database persistence.

    This class provides the main interface for:
    - Enqueueing jobs with database tracking
    - Getting job status from the database
    - Updating job progress and status

    Multiple workers can run in parallel - each job is processed exactly once
    by RQ, and workers update the database job record.
    """

    # Map priority strings to queue getters
    PRIORITY_QUEUES = {
        "high": get_high_priority_queue,
        "normal": get_queue,
        "low": get_low_priority_queue,
    }

    # Map job types to their task functions
    JOB_TYPE_FUNCTIONS = {
        JobType.DOCUMENT_INGEST: "evidence_repository.queue.tasks.task_ingest_document",
        JobType.DOCUMENT_EXTRACT: "evidence_repository.queue.tasks.task_extract_document",
        JobType.DOCUMENT_EMBED: "evidence_repository.queue.tasks.task_embed_document",
        JobType.DOCUMENT_PROCESS_FULL: "evidence_repository.queue.tasks.task_process_document_full",
        JobType.BULK_FOLDER_INGEST: "evidence_repository.queue.tasks.task_bulk_folder_ingest",
        JobType.BULK_URL_INGEST: "evidence_repository.queue.tasks.task_ingest_from_url",
        JobType.BATCH_EXTRACT: "evidence_repository.queue.tasks.task_extract_document",
        JobType.BATCH_EMBED: "evidence_repository.queue.tasks.task_embed_document",
        # Version processing pipeline
        JobType.PROCESS_DOCUMENT_VERSION: "evidence_repository.queue.tasks.task_process_document_version",
        JobType.FACT_EXTRACT: "evidence_repository.queue.tasks.task_process_document_version",
        JobType.QUALITY_CHECK: "evidence_repository.queue.tasks.task_process_document_version",
    }

    def __init__(
        self,
        redis: Redis | None = None,
        db_session_factory: sessionmaker | None = None,
    ):
        """Initialize JobQueue.

        Args:
            redis: Redis connection (uses default if not provided).
            db_session_factory: SQLAlchemy session factory for database access.
        """
        self.redis = redis or get_redis_connection()
        self.settings = get_settings()

        if db_session_factory:
            self._session_factory = db_session_factory
        else:
            # Create sync engine for database access
            sync_url = self.settings.database_url.replace("+asyncpg", "")
            engine = create_engine(sync_url)
            self._session_factory = sessionmaker(bind=engine)

    def _get_db_session(self) -> Session:
        """Get a database session."""
        return self._session_factory()

    def enqueue(
        self,
        job_type: JobType | str,
        payload: dict[str, Any],
        priority: int = 0,
        max_attempts: int = 3,
    ) -> str:
        """Enqueue a job for background processing.

        Creates a persistent job record in the database, then enqueues
        to Redis/RQ for processing.

        Args:
            job_type: Type of job (JobType enum or string).
            payload: Input data for the job.
            priority: Job priority (higher = more urgent). Also maps to queue:
                      priority >= 10: high priority queue
                      priority < 0: low priority queue
                      otherwise: normal queue
            max_attempts: Maximum retry attempts on failure.

        Returns:
            Job ID (UUID string).
        """
        # Normalize job type
        if isinstance(job_type, str):
            job_type = JobType(job_type)

        job_id = uuid.uuid4()
        db = self._get_db_session()

        try:
            # Create database job record
            job = Job(
                id=job_id,
                type=job_type,
                status=JobStatus.QUEUED,
                priority=priority,
                payload=payload,
                max_attempts=max_attempts,
                attempts=0,
                progress=0,
            )
            db.add(job)
            db.commit()
            logger.info(f"Created job record: {job_id} type={job_type.value}")

            # Select queue based on priority
            if priority >= 10:
                queue = get_high_priority_queue()
            elif priority < 0:
                queue = get_low_priority_queue()
            else:
                queue = get_queue()

            # Get the task function for this job type
            func_path = self.JOB_TYPE_FUNCTIONS.get(job_type)
            if not func_path:
                raise ValueError(f"No task function configured for job type: {job_type}")

            # Enqueue to RQ
            rq_job = queue.enqueue(
                "evidence_repository.queue.task_runner.run_job",
                job_id=str(job_id),
                job_id_str=str(job_id),
                result_ttl=self.settings.redis_result_ttl,
            )

            # Update job with RQ job ID
            job.queue_job_id = rq_job.id
            db.commit()

            logger.info(f"Enqueued job {job_id} to queue {queue.name}, RQ job: {rq_job.id}")
            return str(job_id)

        except Exception as e:
            db.rollback()
            logger.error(f"Failed to enqueue job: {e}")
            raise
        finally:
            db.close()

    def get_status(self, job_id: str) -> dict[str, Any] | None:
        """Get the current status of a job.

        Args:
            job_id: Job ID (UUID string).

        Returns:
            Job info dict or None if not found.
        """
        db = self._get_db_session()
        try:
            job_uuid = uuid.UUID(job_id)
            job = db.execute(
                select(Job).where(Job.id == job_uuid)
            ).scalar_one_or_none()

            if not job:
                return None

            return {
                "job_id": str(job.id),
                "type": job.type.value,
                "status": job.status.value,
                "priority": job.priority,
                "payload": job.payload,
                "result": job.result,
                "error": job.error,
                "attempts": job.attempts,
                "max_attempts": job.max_attempts,
                "progress": job.progress,
                "progress_message": job.progress_message,
                "worker_id": job.worker_id,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "finished_at": job.finished_at.isoformat() if job.finished_at else None,
                "is_terminal": job.is_terminal,
                "can_retry": job.can_retry,
                "duration_seconds": job.duration_seconds,
            }
        finally:
            db.close()

    def update_job_status(
        self,
        job_id: str,
        status: JobStatus,
        progress: int | None = None,
        progress_message: str | None = None,
        result: dict[str, Any] | None = None,
        error: str | None = None,
        worker_id: str | None = None,
    ) -> None:
        """Update job status in the database.

        Called by workers at each processing step.

        Args:
            job_id: Job ID.
            status: New status.
            progress: Progress percentage (0-100).
            progress_message: Current step description.
            result: Job result (for SUCCEEDED status).
            error: Error message (for FAILED status).
            worker_id: Worker identifier.
        """
        db = self._get_db_session()
        try:
            job_uuid = uuid.UUID(job_id)
            now = datetime.now(timezone.utc)

            update_data: dict[str, Any] = {"status": status}

            if progress is not None:
                update_data["progress"] = min(100, max(0, progress))
            if progress_message is not None:
                update_data["progress_message"] = progress_message
            if result is not None:
                update_data["result"] = result
            if error is not None:
                update_data["error"] = error
            if worker_id is not None:
                update_data["worker_id"] = worker_id

            # Set timestamps based on status
            if status == JobStatus.RUNNING:
                update_data["started_at"] = now
            elif status in (JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELED):
                update_data["finished_at"] = now

            db.execute(
                update(Job).where(Job.id == job_uuid).values(**update_data)
            )
            db.commit()
            logger.debug(f"Updated job {job_id} status to {status.value}")

        except Exception as e:
            db.rollback()
            logger.error(f"Failed to update job status: {e}")
            raise
        finally:
            db.close()

    def increment_attempts(self, job_id: str) -> int:
        """Increment the attempts counter for a job.

        Args:
            job_id: Job ID.

        Returns:
            New attempt count.
        """
        db = self._get_db_session()
        try:
            job_uuid = uuid.UUID(job_id)
            job = db.execute(
                select(Job).where(Job.id == job_uuid)
            ).scalar_one_or_none()

            if job:
                job.attempts += 1
                db.commit()
                return job.attempts
            return 0
        finally:
            db.close()

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a queued job.

        Args:
            job_id: Job ID.

        Returns:
            True if canceled, False otherwise.
        """
        db = self._get_db_session()
        try:
            job_uuid = uuid.UUID(job_id)
            job = db.execute(
                select(Job).where(Job.id == job_uuid)
            ).scalar_one_or_none()

            if not job:
                return False

            # Can only cancel queued jobs
            if job.status != JobStatus.QUEUED:
                return False

            # Cancel in RQ if we have the reference
            if job.queue_job_id:
                try:
                    rq_job = RQJob.fetch(job.queue_job_id, connection=self.redis)
                    rq_job.cancel()
                except Exception:
                    pass  # RQ job may already be gone

            # Update database status
            job.status = JobStatus.CANCELED
            job.finished_at = datetime.now(timezone.utc)
            db.commit()

            logger.info(f"Canceled job {job_id}")
            return True

        except Exception as e:
            db.rollback()
            logger.error(f"Failed to cancel job: {e}")
            return False
        finally:
            db.close()

    def retry_job(self, job_id: str) -> str | None:
        """Retry a failed job.

        Creates a new job with the same payload.

        Args:
            job_id: Original job ID.

        Returns:
            New job ID or None if retry not allowed.
        """
        db = self._get_db_session()
        try:
            job_uuid = uuid.UUID(job_id)
            job = db.execute(
                select(Job).where(Job.id == job_uuid)
            ).scalar_one_or_none()

            if not job or not job.can_retry:
                return None

            # Update status to retrying
            job.status = JobStatus.RETRYING
            db.commit()

            # Enqueue new job
            return self.enqueue(
                job_type=job.type,
                payload=job.payload,
                priority=job.priority,
                max_attempts=job.max_attempts - job.attempts,
            )

        finally:
            db.close()

    def list_jobs(
        self,
        job_type: JobType | str | None = None,
        status: JobStatus | str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List jobs with optional filtering.

        Args:
            job_type: Filter by job type.
            status: Filter by status.
            limit: Maximum jobs to return.
            offset: Number of jobs to skip.

        Returns:
            List of job info dicts.
        """
        db = self._get_db_session()
        try:
            query = select(Job).order_by(Job.created_at.desc())

            if job_type:
                if isinstance(job_type, str):
                    job_type = JobType(job_type)
                query = query.where(Job.type == job_type)

            if status:
                if isinstance(status, str):
                    status = JobStatus(status)
                query = query.where(Job.status == status)

            query = query.offset(offset).limit(limit)
            jobs = db.execute(query).scalars().all()

            return [
                {
                    "job_id": str(job.id),
                    "type": job.type.value,
                    "status": job.status.value,
                    "priority": job.priority,
                    "progress": job.progress,
                    "progress_message": job.progress_message,
                    "error": job.error,
                    "created_at": job.created_at.isoformat() if job.created_at else None,
                    "started_at": job.started_at.isoformat() if job.started_at else None,
                    "finished_at": job.finished_at.isoformat() if job.finished_at else None,
                }
                for job in jobs
            ]
        finally:
            db.close()


# Global job queue instance
_job_queue: JobQueue | None = None


def get_job_queue() -> JobQueue:
    """Get global JobQueue instance."""
    global _job_queue
    if _job_queue is None:
        _job_queue = JobQueue()
    return _job_queue
