"""Folder-related schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from evidence_repository.schemas.common import BaseSchema


class FolderCreate(BaseModel):
    """Request schema for creating a folder."""

    name: str = Field(..., min_length=1, max_length=255, description="Folder name")
    description: str | None = Field(default=None, description="Folder description")
    parent_folder_id: UUID | None = Field(
        default=None,
        description="Parent folder ID (null for root level)",
    )
    color: str | None = Field(
        default=None,
        pattern=r"^#[0-9A-Fa-f]{6}$",
        description="Folder color (hex format, e.g., #FF5733)",
    )
    icon: str | None = Field(
        default=None,
        max_length=50,
        description="Icon identifier",
    )
    metadata: dict[str, Any] = Field(default_factory=dict, description="Custom metadata")


class FolderUpdate(BaseModel):
    """Request schema for updating a folder."""

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        description="Folder name",
    )
    description: str | None = Field(default=None, description="Folder description")
    parent_folder_id: UUID | None = Field(
        default=None,
        description="Parent folder ID (null for root level)",
    )
    display_order: int | None = Field(
        default=None,
        ge=0,
        description="Display order within parent",
    )
    color: str | None = Field(
        default=None,
        pattern=r"^#[0-9A-Fa-f]{6}$",
        description="Folder color (hex)",
    )
    icon: str | None = Field(default=None, max_length=50, description="Icon identifier")
    metadata: dict[str, Any] | None = Field(default=None, description="Custom metadata")


class FolderResponse(BaseSchema):
    """Response schema for folder."""

    id: UUID = Field(..., description="Folder ID")
    name: str = Field(..., description="Folder name")
    description: str | None = Field(default=None)
    project_id: UUID = Field(..., description="Project ID")
    parent_folder_id: UUID | None = Field(default=None, description="Parent folder ID")
    display_order: int = Field(default=0, description="Display order")
    color: str | None = Field(default=None)
    icon: str | None = Field(default=None)
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    deleted_at: datetime | None = Field(default=None)
    metadata: dict[str, Any] = Field(default_factory=dict, alias="metadata_")

    # Counts (computed fields)
    document_count: int = Field(default=0, description="Documents in this folder")
    subfolder_count: int = Field(default=0, description="Direct child folders")


class FolderTreeNode(BaseModel):
    """Folder node for tree response (recursive structure)."""

    id: UUID
    name: str
    description: str | None = None
    parent_folder_id: UUID | None = None
    display_order: int = 0
    color: str | None = None
    icon: str | None = None
    document_count: int = 0
    children: list[FolderTreeNode] = Field(default_factory=list)

    model_config = {"from_attributes": True}


# Enable forward reference for recursive type
FolderTreeNode.model_rebuild()


class FolderTreeResponse(BaseModel):
    """Response for folder tree structure."""

    project_id: UUID
    root_document_count: int = Field(
        default=0,
        description="Documents at project root (no folder)",
    )
    folders: list[FolderTreeNode] = Field(
        default_factory=list,
        description="Root-level folders with nested children",
    )


class MoveDocumentRequest(BaseModel):
    """Request to move a document to a folder."""

    folder_id: UUID | None = Field(
        default=None,
        description="Target folder ID (null to move to project root)",
    )


class MoveFolderRequest(BaseModel):
    """Request to move a folder to a new parent."""

    parent_folder_id: UUID | None = Field(
        default=None,
        description="New parent folder ID (null for root level)",
    )


class BulkMoveDocumentsRequest(BaseModel):
    """Request to move multiple documents to a folder."""

    document_ids: list[UUID] = Field(
        ...,
        min_length=1,
        description="Document IDs to move",
    )
    folder_id: UUID | None = Field(
        default=None,
        description="Target folder ID (null for project root)",
    )
