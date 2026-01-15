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
- `two_stage`: Metadata filter + semantic ranking
- `discovery`: Find documents with comprehensive topic coverage

**Keyword Filtering:**
- `keywords`: List of terms that MUST appear in results (AND logic)
- `exclude_keywords`: Terms to exclude from results

**Metadata Filtering (for two_stage/discovery):**
- `sectors`: Filter by industry sectors
- `topics`: Filter by main topics
- `document_types`: Filter by document type
- `geographies`: Filter by geographic regions
- `companies`: Filter by company names

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
    # Use two-stage search for these modes
    if query.mode in (SearchMode.TWO_STAGE, SearchMode.DISCOVERY):
        return await _two_stage_search(query, db)

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


async def _two_stage_search(
    query: SearchQuery,
    db: AsyncSession,
) -> SearchResult:
    """Execute two-stage or discovery search."""
    from evidence_repository.services.two_stage_search import (
        TwoStageSearch,
        SearchMode as TSSearchMode,
        SearchFilters,
    )

    # Build filters
    filters = SearchFilters(
        sectors=query.sectors,
        topics=query.topics,
        document_types=query.document_types,
        geographies=query.geographies,
        companies=query.companies,
        project_id=query.project_id,
        document_ids=query.document_ids,
    )

    # Determine search mode
    ts_mode = TSSearchMode.TWO_STAGE
    if query.mode == SearchMode.DISCOVERY:
        ts_mode = TSSearchMode.DISCOVERY

    # Execute search
    search_service = TwoStageSearch(db=db)

    try:
        response = await search_service.search(
            query=query.query,
            filters=filters,
            mode=ts_mode,
            limit=query.limit,
            similarity_threshold=query.similarity_threshold,
            metadata_weight=query.metadata_weight,
            semantic_weight=query.semantic_weight,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Two-stage search failed: {e}",
        )

    # Convert to response format
    results = []
    for item in response.results:
        # Create a simplified citation for two-stage results
        locator = SpanLocator(
            type="text",
            page=item.page,
            char_offset_start=None,
            char_offset_end=None,
        )
        citation = Citation(
            span_id=item.span_id or item.id,
            document_id=item.document_id,
            document_version_id=item.version_id,
            document_filename=item.document_filename,
            span_type=item.span_type or "text",
            locator=locator,
            text_excerpt=item.text[:500] if item.text else "",
        )

        results.append(
            SearchResultItem(
                result_id=item.id,
                similarity=item.combined_score,
                citation=citation,
                matched_text=item.text[:500] if item.text else "",
                highlight_ranges=None,
                metadata={
                    "semantic_score": item.semantic_score,
                    "metadata_score": item.metadata_score,
                    "combined_score": item.combined_score,
                    **item.document_metadata,
                },
            )
        )

    return SearchResult(
        query=query.query,
        mode=query.mode,
        results=results,
        total=response.total_hits,
        search_time_ms=response.total_time_ms,
        timestamp=datetime.utcnow(),
        filters_applied={
            "mode": response.mode.value,
            "stage1_time_ms": response.stage1_time_ms,
            "stage2_time_ms": response.stage2_time_ms,
            "documents_searched": response.documents_searched,
            "chunks_searched": response.chunks_searched,
            **response.filters_applied,
        },
    )


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
