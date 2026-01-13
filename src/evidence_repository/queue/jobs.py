"""Job management and tracking."""

import enum
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from redis import Redis
from rq import Queue
from rq.job import Job

from evidence_repository.config import get_settings
from evidence_repository.queue.connection import (
    get_high_priority_queue,
    get_low_priority_queue,
    get_queue,
    get_redis_connection,
)


class JobType(str, enum.Enum):
    """Types of background jobs."""

    # Document processing
    DOCUMENT_INGEST = "document_ingest"
    DOCUMENT_EXTRACT = "document_extract"
    DOCUMENT_EMBED = "document_embed"
    DOCUMENT_PROCESS_FULL = "document_process_full"  # Ingest + extract + embed

    # Bulk operations
    BULK_FOLDER_INGEST = "bulk_folder_ingest"
    BULK_URL_INGEST = "bulk_url_ingest"

    # Batch operations
    BATCH_EXTRACT = "batch_extract"
    BATCH_EMBED = "batch_embed"


class JobStatus(str, enum.Enum):
    """Job execution status."""

    QUEUED = "queued"
    STARTED = "started"
    DEFERRED = "deferred"
    FINISHED = "finished"
    FAILED = "failed"
    STOPPED = "stopped"
    SCHEDULED = "scheduled"
    CANCELED = "canceled"


@dataclass
class JobInfo:
    """Information about a job."""

    job_id: str
    job_type: JobType
    status: JobStatus
    created_at: datetime
    started_at: datetime | None = None
    ended_at: datetime | None = None
    result: Any = None
    error: str | None = None
    progress: float = 0.0
    progress_message: str | None = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "job_id": self.job_id,
            "job_type": self.job_type.value,
            "status": self.status.value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "result": self.result,
            "error": self.error,
            "progress": self.progress,
            "progress_message": self.progress_message,
            "metadata": self.metadata,
        }


class JobManager:
    """Manages job enqueueing and status tracking."""

    # Redis key prefixes for job metadata
    JOB_META_PREFIX = "evidence:job:meta:"
    JOB_PROGRESS_PREFIX = "evidence:job:progress:"

    def __init__(
        self,
        redis: Redis | None = None,
        default_queue: Queue | None = None,
    ):
        """Initialize job manager.

        Args:
            redis: Redis connection (uses default if not provided).
            default_queue: Default queue (uses default if not provided).
        """
        self.redis = redis or get_redis_connection()
        self.default_queue = default_queue or get_queue()
        self.settings = get_settings()

    def enqueue(
        self,
        job_type: JobType,
        func: str,
        *args: Any,
        priority: str = "normal",
        metadata: dict | None = None,
        **kwargs: Any,
    ) -> str:
        """Enqueue a job for background processing.

        Args:
            job_type: Type of job.
            func: Function path to execute (e.g., 'module.function').
            *args: Positional arguments for the function.
            priority: Job priority ('high', 'normal', 'low').
            metadata: Additional metadata to store with job.
            **kwargs: Keyword arguments for the function.

        Returns:
            Job ID.
        """
        # Select queue based on priority
        if priority == "high":
            queue = get_high_priority_queue()
        elif priority == "low":
            queue = get_low_priority_queue()
        else:
            queue = self.default_queue

        # Generate job ID
        job_id = str(uuid.uuid4())

        # Enqueue the job
        job = queue.enqueue(
            func,
            *args,
            job_id=job_id,
            result_ttl=self.settings.redis_result_ttl,
            **kwargs,
        )

        # Store job metadata
        meta = {
            "job_type": job_type.value,
            "created_at": datetime.utcnow().isoformat(),
            "priority": priority,
            **(metadata or {}),
        }
        self._store_job_meta(job_id, meta)

        return job_id

    def enqueue_many(
        self,
        jobs: list[dict],
        priority: str = "low",
    ) -> list[str]:
        """Enqueue multiple jobs.

        Args:
            jobs: List of job specs with 'job_type', 'func', 'args', 'kwargs'.
            priority: Default priority for all jobs.

        Returns:
            List of job IDs.
        """
        job_ids = []
        for job_spec in jobs:
            job_id = self.enqueue(
                job_type=job_spec["job_type"],
                func=job_spec["func"],
                *job_spec.get("args", []),
                priority=job_spec.get("priority", priority),
                metadata=job_spec.get("metadata"),
                **job_spec.get("kwargs", {}),
            )
            job_ids.append(job_id)
        return job_ids

    def get_job_info(self, job_id: str) -> JobInfo | None:
        """Get information about a job.

        Args:
            job_id: Job ID.

        Returns:
            JobInfo or None if not found.
        """
        try:
            job = Job.fetch(job_id, connection=self.redis)
        except Exception:
            # Job not found in RQ, check our metadata
            meta = self._get_job_meta(job_id)
            if not meta:
                return None

            return JobInfo(
                job_id=job_id,
                job_type=JobType(meta.get("job_type", "document_ingest")),
                status=JobStatus.CANCELED,
                created_at=datetime.fromisoformat(meta["created_at"]),
                metadata=meta,
            )

        # Get our custom metadata
        meta = self._get_job_meta(job_id) or {}
        progress_data = self._get_job_progress(job_id)

        # Map RQ status to our status
        status_map = {
            "queued": JobStatus.QUEUED,
            "started": JobStatus.STARTED,
            "deferred": JobStatus.DEFERRED,
            "finished": JobStatus.FINISHED,
            "failed": JobStatus.FAILED,
            "stopped": JobStatus.STOPPED,
            "scheduled": JobStatus.SCHEDULED,
            "canceled": JobStatus.CANCELED,
        }
        status = status_map.get(job.get_status(), JobStatus.QUEUED)

        return JobInfo(
            job_id=job_id,
            job_type=JobType(meta.get("job_type", "document_ingest")),
            status=status,
            created_at=datetime.fromisoformat(meta["created_at"]) if meta.get("created_at") else job.created_at,
            started_at=job.started_at,
            ended_at=job.ended_at,
            result=job.result if status == JobStatus.FINISHED else None,
            error=str(job.exc_info) if job.exc_info else None,
            progress=progress_data.get("progress", 0.0),
            progress_message=progress_data.get("message"),
            metadata=meta,
        )

    def get_jobs_by_type(
        self,
        job_type: JobType,
        status: JobStatus | None = None,
        limit: int = 100,
    ) -> list[JobInfo]:
        """Get jobs by type and optionally status.

        Args:
            job_type: Type of jobs to find.
            status: Optional status filter.
            limit: Maximum number of jobs to return.

        Returns:
            List of JobInfo objects.
        """
        # This is a simplified implementation
        # In production, you'd use Redis SCAN with pattern matching
        jobs = []

        # Check all queues
        for queue in [self.default_queue, get_high_priority_queue(), get_low_priority_queue()]:
            for job_id in queue.job_ids[:limit]:
                info = self.get_job_info(job_id)
                if info and info.job_type == job_type:
                    if status is None or info.status == status:
                        jobs.append(info)

        return jobs[:limit]

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a queued job.

        Args:
            job_id: Job ID.

        Returns:
            True if canceled, False if not found or already running.
        """
        try:
            job = Job.fetch(job_id, connection=self.redis)
            if job.get_status() == "queued":
                job.cancel()
                return True
            return False
        except Exception:
            return False

    def update_progress(
        self,
        job_id: str,
        progress: float,
        message: str | None = None,
    ) -> None:
        """Update job progress. Called from within job functions.

        Args:
            job_id: Job ID.
            progress: Progress percentage (0.0 - 100.0).
            message: Optional progress message.
        """
        data = {
            "progress": min(100.0, max(0.0, progress)),
            "message": message,
            "updated_at": datetime.utcnow().isoformat(),
        }
        key = f"{self.JOB_PROGRESS_PREFIX}{job_id}"
        self.redis.hset(key, mapping={k: str(v) if v is not None else "" for k, v in data.items()})
        self.redis.expire(key, self.settings.redis_result_ttl)

    def _store_job_meta(self, job_id: str, meta: dict) -> None:
        """Store job metadata in Redis."""
        key = f"{self.JOB_META_PREFIX}{job_id}"
        self.redis.hset(key, mapping={k: str(v) for k, v in meta.items()})
        self.redis.expire(key, self.settings.redis_result_ttl)

    def _get_job_meta(self, job_id: str) -> dict | None:
        """Get job metadata from Redis."""
        key = f"{self.JOB_META_PREFIX}{job_id}"
        data = self.redis.hgetall(key)
        if not data:
            return None
        return {k.decode(): v.decode() for k, v in data.items()}

    def _get_job_progress(self, job_id: str) -> dict:
        """Get job progress from Redis."""
        key = f"{self.JOB_PROGRESS_PREFIX}{job_id}"
        data = self.redis.hgetall(key)
        if not data:
            return {"progress": 0.0, "message": None}

        decoded = {k.decode(): v.decode() for k, v in data.items()}
        return {
            "progress": float(decoded.get("progress", 0)),
            "message": decoded.get("message") or None,
        }


# Global job manager instance
_job_manager: JobManager | None = None


def get_job_manager() -> JobManager:
    """Get global job manager instance."""
    global _job_manager
    if _job_manager is None:
        _job_manager = JobManager()
    return _job_manager
