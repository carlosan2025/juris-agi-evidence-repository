"""Job-related schemas for API."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class JobResponse(BaseModel):
    """Response schema for job information."""

    job_id: str = Field(..., description="Unique job identifier")
    job_type: str = Field(..., description="Type of job")
    status: str = Field(..., description="Current job status")
    created_at: datetime | None = Field(None, description="Job creation timestamp")
    started_at: datetime | None = Field(None, description="Job start timestamp")
    ended_at: datetime | None = Field(None, description="Job completion timestamp")
    result: Any | None = Field(None, description="Job result (if completed)")
    error: str | None = Field(None, description="Error message (if failed)")
    progress: float = Field(0.0, description="Progress percentage (0-100)")
    progress_message: str | None = Field(None, description="Current progress message")
    metadata: dict = Field(default_factory=dict, description="Additional job metadata")


class JobEnqueueResponse(BaseModel):
    """Response after enqueueing a job."""

    job_id: str = Field(..., description="Job ID for tracking")
    job_type: str = Field(..., description="Type of job")
    status: str = Field(default="queued", description="Initial status")
    message: str = Field(..., description="Confirmation message")


class BulkJobEnqueueResponse(BaseModel):
    """Response after enqueueing multiple jobs."""

    job_ids: list[str] = Field(..., description="List of job IDs")
    total_jobs: int = Field(..., description="Number of jobs enqueued")
    message: str = Field(..., description="Confirmation message")


# =============================================================================
# Generic Job Enqueue Request
# =============================================================================


class JobEnqueueRequest(BaseModel):
    """Generic request to enqueue a job.

    This endpoint allows enqueueing any supported job type with a payload.

    Supported job types:
    - process_document_version: Process a specific document version
    - ingest_folder: Bulk ingest files from a folder
    - ingest_url: Download and ingest a file from a URL
    """

    type: str = Field(
        ...,
        description="Job type (e.g., 'document_ingest', 'bulk_folder_ingest', 'bulk_url_ingest')",
        examples=["document_process_full", "bulk_folder_ingest", "bulk_url_ingest"],
    )
    payload: dict[str, Any] = Field(
        ...,
        description="Job-specific input data",
        examples=[
            {"folder_path": "/data/documents", "recursive": True},
            {"url": "https://example.com/document.pdf"},
        ],
    )
    priority: int = Field(
        default=0,
        ge=-100,
        le=100,
        description="Job priority (-100 to 100). Higher = more urgent. 10+ uses high priority queue, <0 uses low priority queue.",
    )


# =============================================================================
# Request Schemas
# =============================================================================


class DocumentUploadRequest(BaseModel):
    """Request to upload and process a document asynchronously."""

    process_full: bool = Field(
        default=True,
        description="Run full processing pipeline (ingest + extract + embed)",
    )
    skip_embedding: bool = Field(
        default=False,
        description="Skip embedding generation (only valid if process_full=True)",
    )
    metadata: dict = Field(
        default_factory=dict,
        description="Additional metadata to store with document",
    )


class BulkFolderIngestRequest(BaseModel):
    """Request to ingest files from a local folder."""

    folder_path: str = Field(..., description="Absolute path to folder to scan")
    recursive: bool = Field(
        default=True,
        description="Include files in subfolders",
    )
    process_full: bool = Field(
        default=True,
        description="Run full processing (extract + embed) for each file",
    )


class URLIngestRequest(BaseModel):
    """Request to ingest a file from a URL."""

    url: str = Field(..., description="URL to download file from")
    filename: str | None = Field(
        None,
        description="Optional filename override (auto-detected if not provided)",
    )
    process_full: bool = Field(
        default=True,
        description="Run full processing pipeline",
    )


class BatchExtractRequest(BaseModel):
    """Request to extract text from multiple documents."""

    document_ids: list[str] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Document IDs to extract (max 100)",
    )


class BatchEmbedRequest(BaseModel):
    """Request to generate embeddings for multiple documents."""

    document_ids: list[str] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Document IDs to embed (max 100)",
    )


# =============================================================================
# Job List Response
# =============================================================================


class JobListResponse(BaseModel):
    """Response for listing jobs."""

    jobs: list[JobResponse] = Field(..., description="List of jobs")
    total: int = Field(..., description="Total number of jobs")
