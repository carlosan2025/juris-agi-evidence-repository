"""Search-related schemas."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from evidence_repository.schemas.common import BaseSchema


class SearchQuery(BaseModel):
    """Search query parameters."""

    query: str = Field(..., min_length=1, description="Search query text")
    project_id: UUID | None = Field(
        default=None, description="Optional: limit search to specific project"
    )
    document_ids: list[UUID] | None = Field(
        default=None, description="Optional: limit search to specific documents"
    )
    limit: int = Field(default=10, ge=1, le=100, description="Maximum results to return")
    similarity_threshold: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Minimum similarity score (0-1)",
    )
    include_text: bool = Field(
        default=True, description="Include matching text in results"
    )


class SearchResultItem(BaseSchema):
    """Single search result item."""

    chunk_id: UUID = Field(..., description="Embedding chunk ID")
    document_id: UUID = Field(..., description="Document ID")
    document_version_id: UUID = Field(..., description="Document version ID")
    span_id: UUID | None = Field(default=None, description="Associated span ID")

    # Content
    text: str = Field(..., description="Matching text chunk")
    similarity: float = Field(..., description="Similarity score (0-1)")

    # Context
    chunk_index: int = Field(..., description="Chunk position in document")
    char_start: int | None = Field(default=None, description="Start character offset")
    char_end: int | None = Field(default=None, description="End character offset")

    # Document info
    document_filename: str = Field(..., description="Document filename")
    document_content_type: str = Field(..., description="Document MIME type")

    # Metadata
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Chunk metadata",
        alias="metadata_",
    )


class SearchResult(BaseModel):
    """Search results response."""

    query: str = Field(..., description="Original query")
    results: list[SearchResultItem] = Field(..., description="Search results")
    total: int = Field(..., description="Total number of results")
    search_time_ms: float = Field(..., description="Search execution time in ms")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Search timestamp"
    )


class ProjectSearchQuery(BaseModel):
    """Search query within a project context."""

    query: str = Field(..., min_length=1, description="Search query text")
    include_claims: bool = Field(
        default=True, description="Include claims in search"
    )
    include_metrics: bool = Field(
        default=True, description="Include metrics in search"
    )
    limit: int = Field(default=10, ge=1, le=100, description="Maximum results")
    similarity_threshold: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Minimum similarity score",
    )
