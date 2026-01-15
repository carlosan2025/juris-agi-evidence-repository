"""Search-related schemas."""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from evidence_repository.schemas.common import BaseSchema


class SearchMode(str, Enum):
    """Search mode options."""

    SEMANTIC = "semantic"  # Vector similarity search only
    KEYWORD = "keyword"  # Full-text keyword search only
    HYBRID = "hybrid"  # Combined semantic + keyword search
    TWO_STAGE = "two_stage"  # Metadata filter + semantic ranking
    DISCOVERY = "discovery"  # Find comprehensive document coverage


class SpanTypeFilter(str, Enum):
    """Span types for filtering."""

    TEXT = "text"
    TABLE = "table"
    FIGURE = "figure"
    CITATION = "citation"
    HEADING = "heading"
    FOOTNOTE = "footnote"
    OTHER = "other"


class SearchQuery(BaseModel):
    """Search query parameters."""

    query: str = Field(..., min_length=1, description="Search query text")
    project_id: UUID | None = Field(
        default=None, description="Limit search to specific project"
    )
    document_ids: list[UUID] | None = Field(
        default=None, description="Limit search to specific documents"
    )
    limit: int = Field(default=10, ge=1, le=100, description="Maximum results to return")
    similarity_threshold: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Minimum similarity score (0-1) for semantic search",
    )
    # Keyword filtering
    keywords: list[str] | None = Field(
        default=None,
        description="Optional keywords that must appear in results (AND logic)",
    )
    exclude_keywords: list[str] | None = Field(
        default=None,
        description="Optional keywords to exclude from results",
    )
    # Search mode
    mode: SearchMode = Field(
        default=SearchMode.SEMANTIC,
        description="Search mode: semantic, keyword, hybrid, two_stage, or discovery",
    )
    # Span filtering
    span_types: list[SpanTypeFilter] | None = Field(
        default=None,
        description="Filter by span types (e.g., text, table, figure)",
    )
    spans_only: bool = Field(
        default=False,
        description="Only return results that have associated spans",
    )

    # Two-stage search metadata filters
    sectors: list[str] | None = Field(
        default=None,
        description="Filter by industry sectors (for two_stage/discovery modes)",
    )
    topics: list[str] | None = Field(
        default=None,
        description="Filter by main topics (for two_stage/discovery modes)",
    )
    document_types: list[str] | None = Field(
        default=None,
        description="Filter by document types (for two_stage/discovery modes)",
    )
    geographies: list[str] | None = Field(
        default=None,
        description="Filter by geographic regions (for two_stage/discovery modes)",
    )
    companies: list[str] | None = Field(
        default=None,
        description="Filter by company names (for two_stage/discovery modes)",
    )

    # Two-stage search weights
    metadata_weight: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="Weight for metadata score in two_stage mode",
    )
    semantic_weight: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Weight for semantic score in two_stage mode",
    )


# =============================================================================
# Citation Schema - Core output format
# =============================================================================


class SpanLocator(BaseModel):
    """Location reference within a document."""

    type: str = Field(..., description="Locator type (pdf, spreadsheet, text)")
    page: int | None = Field(default=None, description="Page number for PDFs")
    bbox: dict[str, float] | None = Field(
        default=None, description="Bounding box for PDFs"
    )
    sheet: str | None = Field(default=None, description="Sheet name for spreadsheets")
    cell_range: str | None = Field(
        default=None, description="Cell range for spreadsheets"
    )
    char_offset_start: int | None = Field(
        default=None, description="Start character offset"
    )
    char_offset_end: int | None = Field(
        default=None, description="End character offset"
    )


class Citation(BaseModel):
    """Citation reference to a document span."""

    span_id: UUID = Field(..., description="Unique span identifier")
    document_id: UUID = Field(..., description="Document ID")
    document_version_id: UUID = Field(..., description="Document version ID")
    document_filename: str = Field(..., description="Document filename")
    span_type: str = Field(..., description="Type of span (text, table, figure, etc.)")
    locator: SpanLocator = Field(..., description="Location within document")
    text_excerpt: str = Field(..., description="Text content excerpt")


class SearchResultItem(BaseSchema):
    """Single search result with citation."""

    # Result identification
    result_id: UUID = Field(..., description="Unique result identifier (chunk/span ID)")
    similarity: float = Field(..., description="Relevance/similarity score (0-1)")

    # Citation (always present - never raw embeddings)
    citation: Citation = Field(..., description="Citation reference to source")

    # Match context
    matched_text: str = Field(..., description="Text that matched the query")
    highlight_ranges: list[dict[str, int]] | None = Field(
        default=None,
        description="Character ranges for keyword highlights [{start, end}, ...]",
    )

    # Metadata
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata",
    )


class SearchResult(BaseModel):
    """Search results response."""

    query: str = Field(..., description="Original query")
    mode: SearchMode = Field(..., description="Search mode used")
    results: list[SearchResultItem] = Field(..., description="Search results with citations")
    total: int = Field(..., description="Total number of results returned")
    search_time_ms: float = Field(..., description="Search execution time in milliseconds")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Search timestamp"
    )
    # Filter info
    filters_applied: dict[str, Any] = Field(
        default_factory=dict,
        description="Summary of filters that were applied",
    )


class ProjectSearchQuery(BaseModel):
    """Search query within a project context."""

    query: str = Field(..., min_length=1, description="Search query text")
    limit: int = Field(default=10, ge=1, le=100, description="Maximum results")
    similarity_threshold: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Minimum similarity score",
    )
    # Keyword filtering
    keywords: list[str] | None = Field(
        default=None,
        description="Keywords that must appear in results",
    )
    exclude_keywords: list[str] | None = Field(
        default=None,
        description="Keywords to exclude",
    )
    mode: SearchMode = Field(
        default=SearchMode.SEMANTIC,
        description="Search mode",
    )
    span_types: list[SpanTypeFilter] | None = Field(
        default=None,
        description="Filter by span types",
    )
    spans_only: bool = Field(
        default=False,
        description="Only return span-based results",
    )
    # Project-specific filters
    document_ids: list[UUID] | None = Field(
        default=None,
        description="Limit to specific documents within the project",
    )
