"""Job model for persistent job tracking in database."""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from evidence_repository.models.base import Base, UUIDMixin


class JobStatus(str, enum.Enum):
    """Job execution status."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"
    RETRYING = "retrying"


class JobType(str, enum.Enum):
    """Type of background job."""

    # Document processing
    DOCUMENT_INGEST = "document_ingest"
    DOCUMENT_EXTRACT = "document_extract"
    DOCUMENT_EMBED = "document_embed"
    DOCUMENT_PROCESS_FULL = "document_process_full"

    # Version processing pipeline (idempotent 5-step pipeline)
    PROCESS_DOCUMENT_VERSION = "process_document_version"

    # Bulk operations
    BULK_FOLDER_INGEST = "bulk_folder_ingest"
    BULK_URL_INGEST = "bulk_url_ingest"
    BATCH_EXTRACT = "batch_extract"
    BATCH_EMBED = "batch_embed"

    # Evidence processing
    SPAN_EXTRACT = "span_extract"
    CLAIM_EXTRACT = "claim_extract"
    METRIC_EXTRACT = "metric_extract"
    FACT_EXTRACT = "fact_extract"

    # Multi-level extraction (with process_context support)
    MULTILEVEL_EXTRACT = "multilevel_extract"
    MULTILEVEL_EXTRACT_BATCH = "multilevel_extract_batch"
    UPGRADE_EXTRACTION_LEVEL = "upgrade_extraction_level"

    # Quality analysis
    QUALITY_CHECK = "quality_check"

    # Maintenance
    CLEANUP = "cleanup"
    REINDEX = "reindex"


class Job(Base, UUIDMixin):
    """Persistent job record for tracking background processing.

    Jobs are queued for async processing and their status is tracked
    in the database for durability and queryability.
    """

    __tablename__ = "jobs"

    # Job type and status
    type: Mapped[JobType] = mapped_column(
        Enum(JobType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        index=True,
    )
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, values_callable=lambda x: [e.value for e in x]),
        default=JobStatus.QUEUED,
        nullable=False,
        index=True,
    )

    # Priority (higher = more urgent, default 0)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Payload: input data for the job
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # Result: output data from successful job
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    # Error: error message/details if job failed
    error: Mapped[str | None] = mapped_column(Text)

    # Retry tracking
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)

    # Progress tracking (0-100)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    progress_message: Mapped[str | None] = mapped_column(String(500))

    # Worker identification
    worker_id: Mapped[str | None] = mapped_column(String(255))

    # External queue reference (RQ job ID, SQS message ID, etc.)
    queue_job_id: Mapped[str | None] = mapped_column(String(255), index=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Indexes for common queries
    __table_args__ = (
        Index("ix_jobs_status_created_at", "status", "created_at"),
        Index("ix_jobs_type_status", "type", "status"),
        Index("ix_jobs_priority_created_at", "priority", "created_at"),
    )

    @property
    def is_terminal(self) -> bool:
        """Check if job is in a terminal state."""
        return self.status in (JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELED)

    @property
    def can_retry(self) -> bool:
        """Check if job can be retried."""
        return self.status == JobStatus.FAILED and self.attempts < self.max_attempts

    @property
    def duration_seconds(self) -> float | None:
        """Calculate job duration in seconds."""
        if self.started_at and self.finished_at:
            return (self.finished_at - self.started_at).total_seconds()
        return None
