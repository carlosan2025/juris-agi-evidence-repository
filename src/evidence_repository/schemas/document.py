"""Document-related schemas."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from evidence_repository.schemas.common import BaseSchema


class DocumentCreate(BaseModel):
    """Request schema for document creation (metadata only, file sent separately)."""

    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Custom document metadata"
    )


class DocumentVersionResponse(BaseSchema):
    """Response schema for document version."""

    id: UUID = Field(..., description="Version ID")
    document_id: UUID = Field(..., description="Parent document ID")
    version_number: int = Field(..., description="Version number")
    file_size: int = Field(..., description="File size in bytes")
    file_hash: str = Field(..., description="SHA-256 hash of file content")
    upload_status: str = Field(
        default="uploaded", description="Upload status: pending, uploaded, or failed"
    )
    processing_status: str | None = Field(
        default="pending",
        description="Overall processing status: pending, uploaded, extracted, spans_built, embedded, facts_extracted, quality_checked, or failed"
    )
    extraction_status: str = Field(..., description="Text extraction status")
    extraction_error: str | None = Field(
        default=None, description="Extraction error message if failed"
    )
    extracted_at: datetime | None = Field(
        default=None, description="When extraction completed"
    )
    page_count: int | None = Field(
        default=None, description="Number of pages (for PDFs)"
    )
    created_at: datetime = Field(..., description="Version creation timestamp")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Version metadata",
        alias="metadata_",
    )


class DocumentResponse(BaseSchema):
    """Response schema for document."""

    id: UUID = Field(..., description="Document ID")
    filename: str = Field(..., description="Storage filename")
    original_filename: str = Field(..., description="Original uploaded filename")
    content_type: str = Field(..., description="MIME type")
    file_hash: str | None = Field(
        default=None, description="SHA-256 hash for deduplication"
    )
    profile_code: str = Field(
        default="general",
        description="Industry profile for extraction (vc, pharma, insurance, general)",
    )
    created_at: datetime = Field(..., description="Document creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    deleted_at: datetime | None = Field(
        default=None, description="Soft deletion timestamp"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Document metadata",
        alias="metadata_",
    )

    # Deletion tracking fields
    deletion_status: str = Field(
        default="active",
        description="Deletion status: active, marked, deleting, failed, deleted",
    )
    deletion_requested_at: datetime | None = Field(
        default=None, description="When deletion was requested"
    )
    deletion_error: str | None = Field(
        default=None, description="Last deletion error if failed"
    )

    # Include latest version info
    latest_version: DocumentVersionResponse | None = Field(
        default=None, description="Latest document version"
    )


class DocumentListResponse(BaseSchema):
    """Response schema for document list item (lighter than full response)."""

    id: UUID
    filename: str
    original_filename: str
    content_type: str
    created_at: datetime
    updated_at: datetime
    version_count: int = Field(default=0, description="Number of versions")
    latest_extraction_status: str | None = Field(
        default=None, description="Extraction status of latest version"
    )


class ExtractionTriggerResponse(BaseModel):
    """Response after triggering extraction."""

    document_id: UUID = Field(..., description="Document ID")
    version_id: UUID = Field(..., description="Version being extracted")
    status: str = Field(..., description="Extraction status")
    message: str = Field(..., description="Status message")


class DocumentUploadResponse(BaseModel):
    """Response after uploading a document (async processing)."""

    document_id: UUID = Field(..., description="Document ID")
    version_id: UUID = Field(..., description="Version ID created")
    job_id: str = Field(..., description="Job ID for tracking processing status")
    message: str = Field(default="Document queued for processing", description="Status message")


class VersionUploadResponse(BaseModel):
    """Response after uploading a new document version (async processing)."""

    document_id: UUID = Field(..., description="Parent document ID")
    version_id: UUID = Field(..., description="New version ID")
    version_number: int = Field(..., description="Version number")
    job_id: str = Field(..., description="Job ID for tracking processing status")
    message: str = Field(default="Version queued for processing", description="Status message")


class PresignedUploadRequest(BaseModel):
    """Request to generate a presigned upload URL."""

    filename: str = Field(..., description="Original filename")
    content_type: str = Field(..., description="MIME type of the file")
    file_size: int = Field(..., ge=1, description="File size in bytes")
    profile_code: str = Field(
        default="general",
        description="Industry profile for extraction (vc, pharma, insurance, general)",
    )


class PresignedUploadResponse(BaseModel):
    """Response with presigned URL for direct upload to storage."""

    upload_url: str = Field(..., description="Presigned URL for PUT upload")
    document_id: UUID = Field(..., description="Document ID (created)")
    version_id: UUID = Field(..., description="Version ID (created)")
    key: str = Field(..., description="Storage key for the file")
    content_type: str = Field(..., description="Expected content type")
    expires_in: int = Field(..., description="URL expiration in seconds")
    message: str = Field(
        default="Upload file directly to the presigned URL using PUT",
        description="Instructions",
    )


class ConfirmUploadRequest(BaseModel):
    """Request to confirm a presigned upload completed."""

    document_id: UUID = Field(..., description="Document ID from presigned response")
    version_id: UUID = Field(..., description="Version ID from presigned response")


class ConfirmUploadResponse(BaseModel):
    """Response after confirming upload."""

    document_id: UUID = Field(..., description="Document ID")
    version_id: UUID = Field(..., description="Version ID")
    job_id: str | None = Field(None, description="Job ID for tracking (None if processed synchronously)")
    message: str = Field(default="Upload confirmed, processing queued", description="Status message")
