"""JobQueue abstraction with database persistence.

This module provides a unified interface for enqueueing jobs that:
1. Creates a persistent job record in the database
2. Enqueues the job to Redis/RQ for processing (when Redis is available)
3. Tracks status transitions and progress

Workers update the database job record at each processing step.

In serverless environments (Vercel), Redis is not available, so jobs are
stored in the database only and processed via HTTP-triggered workers.
"""

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from evidence_repository.config import get_settings
from evidence_repository.models.job import Job, JobStatus, JobType

logger = logging.getLogger(__name__)

# Check if running in serverless environment
IS_SERVERLESS = os.environ.get("VERCEL") == "1"


class JobQueue:
    """Unified job queue with database persistence.

    This class provides the main interface for:
    - Enqueueing jobs with database tracking
    - Getting job status from the database
    - Updating job progress and status

    In serverless mode (Vercel), jobs are stored in the database only.
    In traditional mode, jobs are also enqueued to Redis/RQ for processing.
    """

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
        # Multi-level extraction (with process_context support)
        JobType.MULTILEVEL_EXTRACT: "evidence_repository.queue.tasks.task_multilevel_extract",
        JobType.MULTILEVEL_EXTRACT_BATCH: "evidence_repository.queue.tasks.task_multilevel_extract_batch",
        JobType.UPGRADE_EXTRACTION_LEVEL: "evidence_repository.queue.tasks.task_upgrade_extraction_level",
    }

    def __init__(
        self,
        redis: Any | None = None,
        db_session_factory: sessionmaker | None = None,
    ):
        """Initialize JobQueue.

        Args:
            redis: Redis connection (uses default if not provided, ignored in serverless).
            db_session_factory: SQLAlchemy session factory for database access.
        """
        self.settings = get_settings()
        self.redis = None
        self._redis_available = False

        # Only try to connect to Redis if not in serverless mode
        if not IS_SERVERLESS:
            try:
                if redis:
                    self.redis = redis
                else:
                    from evidence_repository.queue.connection import get_redis_connection
                    self.redis = get_redis_connection()
                self._redis_available = True
            except Exception as e:
                logger.warning(f"Redis not available, running in database-only mode: {e}")

        if db_session_factory:
            self._session_factory = db_session_factory
        else:
            # Create sync engine for database access using psycopg (psycopg3)
            sync_url = self.settings.database_url.replace(
                "postgresql+asyncpg://", "postgresql+psycopg://"
            )
            # psycopg3 uses 'sslmode' instead of 'ssl' parameter
            # Neon URLs use ssl=require, convert to sslmode=require for psycopg3
            sync_url = sync_url.replace("ssl=require", "sslmode=require")
            sync_url = sync_url.replace("ssl=true", "sslmode=require")
            # Use NullPool in serverless for fresh connections each time
            if IS_SERVERLESS:
                engine = create_engine(sync_url, poolclass=NullPool)
            else:
                engine = create_engine(sync_url, pool_pre_ping=True)
            self._session_factory = sessionmaker(bind=engine)

    def _get_db_session(self) -> Session:
        """Get a database session."""
        return self._session_factory()

    def _get_queue_for_priority(self, priority: int):
        """Get the appropriate RQ queue for a priority level."""
        if not self._redis_available:
            return None

        from evidence_repository.queue.connection import (
            get_high_priority_queue,
            get_low_priority_queue,
            get_queue,
        )

        if priority >= 10:
            return get_high_priority_queue()
        elif priority < 0:
            return get_low_priority_queue()
        else:
            return get_queue()

    def enqueue(
        self,
        job_type: JobType | str,
        payload: dict[str, Any],
        priority: int = 0,
        max_attempts: int = 3,
    ) -> str:
        """Enqueue a job for background processing.

        Creates a persistent job record in the database. If Redis is available,
        also enqueues to Redis/RQ for processing. Otherwise, jobs are processed
        via HTTP-triggered workers (Vercel cron).

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

            # If Redis is available, also enqueue to RQ
            if self._redis_available:
                queue = self._get_queue_for_priority(priority)
                if queue:
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
            else:
                logger.info(f"Job {job_id} stored in database (serverless mode, no Redis)")

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

            # Cancel in RQ if we have Redis and a reference
            if self._redis_available and job.queue_job_id:
                try:
                    from rq.job import Job as RQJob
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

    def delete_job(self, job_id: str) -> bool:
        """Delete a job from the database.

        Can delete jobs in any terminal state (succeeded, failed, canceled)
        or queued jobs. Cannot delete running jobs.

        Args:
            job_id: Job ID.

        Returns:
            True if deleted, False otherwise.
        """
        db = self._get_db_session()
        try:
            job_uuid = uuid.UUID(job_id)
            job = db.execute(
                select(Job).where(Job.id == job_uuid)
            ).scalar_one_or_none()

            if not job:
                return False

            # Cannot delete running jobs
            if job.status == JobStatus.RUNNING:
                return False

            db.delete(job)
            db.commit()

            logger.info(f"Deleted job {job_id}")
            return True

        except Exception as e:
            db.rollback()
            logger.error(f"Failed to delete job: {e}")
            return False
        finally:
            db.close()

    def delete_stale_jobs(self, max_age_hours: int = 24) -> int:
        """Delete stale jobs that are no longer relevant.

        Deletes jobs that:
        - Are in QUEUED status but older than max_age_hours
        - Are in RUNNING status but older than max_age_hours (likely orphaned)

        Args:
            max_age_hours: Maximum age in hours for queued/running jobs.

        Returns:
            Number of deleted jobs.
        """
        from datetime import timedelta

        db = self._get_db_session()
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)

            # Find stale jobs
            stale_jobs = db.execute(
                select(Job).where(
                    Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
                    Job.created_at < cutoff,
                )
            ).scalars().all()

            deleted_count = 0
            for job in stale_jobs:
                db.delete(job)
                deleted_count += 1

            db.commit()
            logger.info(f"Deleted {deleted_count} stale jobs")
            return deleted_count

        except Exception as e:
            db.rollback()
            logger.error(f"Failed to delete stale jobs: {e}")
            return 0
        finally:
            db.close()

    def cleanup_completed_jobs(self, max_age_days: int = 7) -> int:
        """Delete old completed jobs to keep the database clean.

        Deletes jobs that:
        - Are in terminal state (succeeded, failed, canceled)
        - Were finished more than max_age_days ago

        Args:
            max_age_days: Maximum age in days for completed jobs.

        Returns:
            Number of deleted jobs.
        """
        from datetime import timedelta

        db = self._get_db_session()
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)

            # Find old completed jobs
            old_jobs = db.execute(
                select(Job).where(
                    Job.status.in_([JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELED]),
                    Job.finished_at < cutoff,
                )
            ).scalars().all()

            deleted_count = 0
            for job in old_jobs:
                db.delete(job)
                deleted_count += 1

            db.commit()
            logger.info(f"Deleted {deleted_count} old completed jobs")
            return deleted_count

        except Exception as e:
            db.rollback()
            logger.error(f"Failed to cleanup completed jobs: {e}")
            return 0
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
