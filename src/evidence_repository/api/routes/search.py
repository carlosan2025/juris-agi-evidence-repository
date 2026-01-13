"""Search endpoints for semantic document search."""

import uuid
from dataclasses import asdict
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from evidence_repository.api.dependencies import User, get_current_user
from evidence_repository.db.session import get_db_session
from evidence_repository.models.evidence import SpanType
from evidence_repository.models.project import Project
from evidence_repository.schemas.search import (
    Citation,
    ProjectSearchQuery,
    SearchMode,
    SearchQuery,
    SearchResult,
    SearchResultItem,
    SpanLocator,
    SpanTypeFilter,
)
from evidence_repository.services.search_service import SearchService
from evidence_repository.services.search_service import SearchMode as ServiceSearchMode

router = APIRouter()


def _convert_search_mode(mode: SearchMode) -> ServiceSearchMode:
    """Convert schema search mode to service search mode."""
    return ServiceSearchMode(mode.value)


def _convert_span_types(span_types: list[SpanTypeFilter] | None) -> list[SpanType] | None:
    """Convert schema span types to model span types."""
    if not span_types:
        return None
    return [SpanType(st.value) for st in span_types]


def _service_result_to_response(
    query: str,
    service_result,
) -> SearchResult:
    """Convert service search results to API response."""
    results = []
    for item in service_result.results:
        # Convert dataclass Citation to Pydantic model
        citation_data = item.citation
        locator = SpanLocator(
            type=citation_data.locator.type,
            page=citation_data.locator.page,
            bbox=citation_data.locator.bbox,
            sheet=citation_data.locator.sheet,
            cell_range=citation_data.locator.cell_range,
            char_offset_start=citation_data.locator.char_offset_start,
            char_offset_end=citation_data.locator.char_offset_end,
        )
        citation = Citation(
            span_id=citation_data.span_id,
            document_id=citation_data.document_id,
            document_version_id=citation_data.document_version_id,
            document_filename=citation_data.document_filename,
            span_type=citation_data.span_type,
            locator=locator,
            text_excerpt=citation_data.text_excerpt,
        )

        results.append(
            SearchResultItem(
                result_id=item.result_id,
                similarity=item.similarity,
                citation=citation,
                matched_text=item.matched_text,
                highlight_ranges=item.highlight_ranges,
                metadata=item.metadata,
            )
        )

    return SearchResult(
        query=query,
        mode=SearchMode(service_result.mode.value),
        results=results,
        total=service_result.total,
        search_time_ms=service_result.search_time_ms,
        timestamp=service_result.timestamp,
        filters_applied=service_result.filters_applied,
    )


@router.post(
    "",
    response_model=SearchResult,
    summary="Semantic Search",
    description="""
Perform semantic search across all documents with optional keyword filtering.

**Search Modes:**
- `semantic` (default): Vector similarity search using embeddings
- `keyword`: Full-text keyword search
- `hybrid`: Combined semantic + keyword search with score fusion

**Keyword Filtering:**
- `keywords`: List of terms that MUST appear in results (AND logic)
- `exclude_keywords`: Terms to exclude from results

**Span Filtering:**
- `span_types`: Filter by span type (text, table, figure, etc.)
- `spans_only`: Only return results with associated spans

Returns citations only (never raw embeddings).
    """,
)
async def search_documents(
    query: SearchQuery,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> SearchResult:
    """Perform semantic search using vector similarity.

    Uses pgvector for efficient similarity search against document embeddings.
    Returns spans with citations only.
    """
    service = SearchService(db=db)

    try:
        result = await service.search(
            query=query.query,
            limit=query.limit,
            similarity_threshold=query.similarity_threshold,
            project_id=query.project_id,
            document_ids=query.document_ids,
            mode=_convert_search_mode(query.mode),
            span_types=_convert_span_types(query.span_types),
            keywords=query.keywords,
            exclude_keywords=query.exclude_keywords,
            spans_only=query.spans_only,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Search failed: {e}",
        )

    return _service_result_to_response(query.query, result)


@router.post(
    "/projects/{project_id}",
    response_model=SearchResult,
    summary="Search Within Project",
    description="""
Search documents within a specific project context.

All search features are available (semantic, keyword, hybrid modes).
Results are automatically scoped to documents attached to the project.
    """,
)
async def search_project(
    project_id: uuid.UUID,
    query: ProjectSearchQuery,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> SearchResult:
    """Search within a specific project."""
    # Verify project exists
    project_result = await db.execute(select(Project).where(Project.id == project_id))
    if not project_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )

    service = SearchService(db=db)

    try:
        result = await service.search(
            query=query.query,
            limit=query.limit,
            similarity_threshold=query.similarity_threshold,
            project_id=project_id,
            document_ids=query.document_ids,
            mode=_convert_search_mode(query.mode),
            span_types=_convert_span_types(query.span_types),
            keywords=query.keywords,
            exclude_keywords=query.exclude_keywords,
            spans_only=query.spans_only,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Search failed: {e}",
        )

    return _service_result_to_response(query.query, result)
