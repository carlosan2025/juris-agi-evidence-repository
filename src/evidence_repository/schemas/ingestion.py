"""Schemas for bulk ingestion endpoints."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from evidence_repository.schemas.common import BaseSchema


# =============================================================================
# Request Schemas
# =============================================================================


class FolderIngestionRequest(BaseModel):
    """Request to ingest documents from a folder."""

    path: str = Field(
        ...,
        description="Absolute path to the folder to scan",
        examples=["/data/documents", "/home/user/files"],
    )
    recursive: bool = Field(
        default=True,
        description="Scan subfolders recursively",
    )
    project_id: UUID | None = Field(
        default=None,
        description="Optional project to attach ingested documents to",
    )
    allowed_types: list[str] = Field(
        default_factory=lambda: ["pdf", "txt", "csv", "xlsx", "png", "jpg"],
        description="File extensions to include (without dots)",
        examples=[["pdf", "txt", "csv"]],
    )
    auto_process: bool = Field(
        default=True,
        description="Automatically process documents (extract text, generate embeddings)",
    )

    @field_validator("allowed_types", mode="before")
    @classmethod
    def normalize_extensions(cls, v: list[str]) -> list[str]:
        """Normalize extensions to lowercase without dots."""
        if isinstance(v, list):
            return [ext.lower().lstrip(".") for ext in v]
        return v


class URLIngestionRequest(BaseModel):
    """Request to ingest a document from a URL."""

    url: str = Field(
        ...,
        description="URL to download the document from",
        examples=["https://example.com/document.pdf"],
    )
    project_id: UUID | None = Field(
        default=None,
        description="Optional project to attach ingested document to",
    )
    auto_process: bool = Field(
        default=True,
        description="Automatically process document (extract text, generate embeddings)",
    )
    filename: str | None = Field(
        default=None,
        description="Override filename (auto-detected from URL if not provided)",
    )

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Validate URL format."""
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return v


# =============================================================================
# Response Schemas
# =============================================================================


class IngestionItemResponse(BaseSchema):
    """Response schema for an individual ingestion item."""

    id: UUID = Field(..., description="Item ID")
    source_path: str = Field(..., description="Source file path or URL")
    source_filename: str = Field(..., description="Original filename")
    status: str = Field(..., description="Processing status")
    document_id: UUID | None = Field(default=None, description="Created document ID")
    version_id: UUID | None = Field(default=None, description="Created version ID")
    error_message: str | None = Field(default=None, description="Error message if failed")
    content_type: str | None = Field(default=None, description="Detected content type")
    created_at: datetime = Field(..., description="Item creation timestamp")


class IngestionBatchResponse(BaseSchema):
    """Response schema for an ingestion batch."""

    id: UUID = Field(..., description="Batch ID")
    name: str | None = Field(default=None, description="Batch name")
    source_type: str = Field(..., description="Source type (local_folder, url, etc.)")
    source_path: str | None = Field(default=None, description="Source path or URL")
    status: str = Field(..., description="Batch status")
    total_items: int = Field(..., description="Total items in batch")
    processed_items: int = Field(..., description="Items processed so far")
    successful_items: int = Field(..., description="Successfully processed items")
    failed_items: int = Field(..., description="Failed items")
    skipped_items: int = Field(..., description="Skipped items (duplicates, etc.)")
    progress_percent: float = Field(..., description="Progress percentage 0-100")
    job_id: str | None = Field(default=None, description="Associated job ID")
    created_at: datetime = Field(..., description="Batch creation timestamp")
    started_at: datetime | None = Field(default=None, description="Processing start time")
    completed_at: datetime | None = Field(default=None, description="Processing completion time")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class FolderIngestionResponse(BaseModel):
    """Response after initiating folder ingestion."""

    batch_id: UUID = Field(..., description="Ingestion batch ID for tracking")
    job_id: str = Field(..., description="Job ID for progress tracking")
    total_files: int = Field(..., description="Number of files found to process")
    message: str = Field(..., description="Status message")


class URLIngestionResponse(BaseModel):
    """Response after initiating URL ingestion."""

    batch_id: UUID = Field(..., description="Ingestion batch ID for tracking")
    item_id: UUID = Field(..., description="Ingestion item ID")
    job_id: str = Field(..., description="Job ID for progress tracking")
    message: str = Field(..., description="Status message")


class IngestionBatchListResponse(BaseModel):
    """Response for listing ingestion batches."""

    batches: list[IngestionBatchResponse] = Field(..., description="List of batches")
    total: int = Field(..., description="Total number of batches")
