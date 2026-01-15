"""Project-related schemas."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from evidence_repository.schemas.common import BaseSchema
from evidence_repository.schemas.document import DocumentResponse


class ProjectCreate(BaseModel):
    """Request schema for creating a project."""

    name: str = Field(..., min_length=1, max_length=255, description="Project name")
    description: str | None = Field(default=None, description="Project description")
    case_ref: str | None = Field(
        default=None, max_length=255, description="External case reference"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Custom project metadata"
    )


class ProjectUpdate(BaseModel):
    """Request schema for updating a project."""

    name: str | None = Field(
        default=None, min_length=1, max_length=255, description="Project name"
    )
    description: str | None = Field(default=None, description="Project description")
    case_ref: str | None = Field(
        default=None, max_length=255, description="External case reference"
    )
    metadata: dict[str, Any] | None = Field(
        default=None, description="Custom project metadata"
    )


class ProjectResponse(BaseSchema):
    """Response schema for project."""

    id: UUID = Field(..., description="Project ID")
    name: str = Field(..., description="Project name")
    description: str | None = Field(default=None, description="Project description")
    case_ref: str | None = Field(default=None, description="External case reference")
    created_at: datetime = Field(..., description="Project creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    deleted_at: datetime | None = Field(
        default=None, description="Soft deletion timestamp"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Project metadata",
        alias="metadata_",
    )

    # Counts
    document_count: int = Field(default=0, description="Number of attached documents")
    claim_count: int = Field(default=0, description="Number of claims")
    metric_count: int = Field(default=0, description="Number of metrics")


class ProjectListResponse(BaseSchema):
    """Response schema for project list item."""

    id: UUID
    name: str
    description: str | None = None
    case_ref: str | None = None
    created_at: datetime
    updated_at: datetime
    document_count: int = 0


class AttachDocumentRequest(BaseModel):
    """Request schema for attaching a document to a project."""

    document_id: UUID = Field(..., description="Document ID to attach")
    pinned_version_id: UUID | None = Field(
        default=None,
        description="Optional: pin to specific version (null = latest)",
    )
    folder_id: UUID | None = Field(
        default=None,
        description="Folder to place document in (null = project root)",
    )
    notes: str | None = Field(
        default=None, description="Notes about why document was attached"
    )


class ProjectDocumentResponse(BaseSchema):
    """Response schema for a document attached to a project."""

    id: UUID = Field(..., description="ProjectDocument junction ID")
    project_id: UUID = Field(..., description="Project ID")
    document_id: UUID = Field(..., description="Document ID")
    pinned_version_id: UUID | None = Field(
        default=None, description="Pinned version ID (null = latest)"
    )
    folder_id: UUID | None = Field(
        default=None, description="Folder ID (null = project root)"
    )
    attached_at: datetime = Field(..., description="When document was attached")
    attached_by: str | None = Field(default=None, description="Who attached it")
    notes: str | None = Field(default=None, description="Attachment notes")

    # Include document details
    document: DocumentResponse | None = Field(
        default=None, description="Attached document details"
    )
