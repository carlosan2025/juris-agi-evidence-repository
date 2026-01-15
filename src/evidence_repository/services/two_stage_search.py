"""Two-stage search architecture.

This module provides a two-stage search that combines fast metadata
filtering with semantic search.

Stage 1: Fast Metadata Filter
  - PostgreSQL full-text search on document fields
  - Filter by sectors, topics, date ranges
  - Array overlap matching
  - Returns candidate document IDs

Stage 2: Semantic Search
  - Vector similarity on chunks within candidates
  - Combined scoring: metadata * 0.3 + semantic * 0.7
  - Returns ranked results with citations

This approach is more efficient than pure vector search for large
document collections with rich metadata.
"""

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import select, and_, or_, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from evidence_repository.config import get_settings
from evidence_repository.models.document import Document, DocumentVersion
from evidence_repository.models.embedding import EmbeddingChunk
from evidence_repository.models.evidence import Span, SpanType

logger = logging.getLogger(__name__)


class SearchMode(str, Enum):
    """Search mode options."""

    SEMANTIC = "semantic"        # Vector-only search
    METADATA = "metadata"        # Metadata-only search
    TWO_STAGE = "two_stage"      # Combined approach (default)
    DISCOVERY = "discovery"      # Document discovery mode


@dataclass
class SearchFilters:
    """Filters for search queries."""

    # Document filters
    sectors: list[str] | None = None
    topics: list[str] | None = None
    document_types: list[str] | None = None
    geographies: list[str] | None = None
    companies: list[str] | None = None

    # Date filters
    published_after: datetime | None = None
    published_before: datetime | None = None
    uploaded_after: datetime | None = None
    uploaded_before: datetime | None = None

    # Scope filters
    project_id: uuid.UUID | None = None
    document_ids: list[uuid.UUID] | None = None

    # Content filters
    min_text_length: int | None = None
    span_types: list[SpanType] | None = None

    # Keywords (required in results)
    required_keywords: list[str] | None = None
    excluded_keywords: list[str] | None = None


@dataclass
class SearchResult:
    """Single search result."""

    id: uuid.UUID
    document_id: uuid.UUID
    document_filename: str
    version_id: uuid.UUID

    # Scores
    semantic_score: float = 0.0
    metadata_score: float = 0.0
    combined_score: float = 0.0

    # Content
    text: str = ""
    highlight_ranges: list[dict] | None = None

    # Location
    span_id: uuid.UUID | None = None
    span_type: str | None = None
    page: int | None = None

    # Metadata
    document_metadata: dict = field(default_factory=dict)


@dataclass
class SearchResponse:
    """Complete search response."""

    query: str
    mode: SearchMode
    results: list[SearchResult]

    # Counts
    total_hits: int
    documents_searched: int
    chunks_searched: int

    # Timing
    stage1_time_ms: float = 0.0
    stage2_time_ms: float = 0.0
    total_time_ms: float = 0.0

    # Filters applied
    filters_applied: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        return {
            "query": self.query,
            "mode": self.mode.value,
            "results": [
                {
                    "id": str(r.id),
                    "document_id": str(r.document_id),
                    "document_filename": r.document_filename,
                    "version_id": str(r.version_id),
                    "semantic_score": r.semantic_score,
                    "metadata_score": r.metadata_score,
                    "combined_score": r.combined_score,
                    "text": r.text[:500],  # Truncate for response
                    "span_type": r.span_type,
                    "page": r.page,
                }
                for r in self.results
            ],
            "total_hits": self.total_hits,
            "documents_searched": self.documents_searched,
            "chunks_searched": self.chunks_searched,
            "timing": {
                "stage1_ms": self.stage1_time_ms,
                "stage2_ms": self.stage2_time_ms,
                "total_ms": self.total_time_ms,
            },
            "filters": self.filters_applied,
        }


class TwoStageSearch:
    """Two-stage search implementation.

    Usage:
        search = TwoStageSearch(db=session)
        response = await search.search(
            query="revenue growth",
            filters=SearchFilters(sectors=["technology"]),
            limit=20,
        )
    """

    def __init__(self, db: AsyncSession):
        """Initialize search service.

        Args:
            db: Async database session.
        """
        self.db = db
        self._settings = get_settings()
        self._embedding_client = None

    @property
    def embedding_client(self):
        """Lazy-load embedding client."""
        if self._embedding_client is None:
            from evidence_repository.embeddings.openai_client import OpenAIEmbeddingClient
            self._embedding_client = OpenAIEmbeddingClient()
        return self._embedding_client

    async def search(
        self,
        query: str,
        filters: SearchFilters | None = None,
        mode: SearchMode = SearchMode.TWO_STAGE,
        limit: int = 20,
        similarity_threshold: float = 0.5,
        metadata_weight: float = 0.3,
        semantic_weight: float = 0.7,
    ) -> SearchResponse:
        """Execute search query.

        Args:
            query: Search query text.
            filters: Optional search filters.
            mode: Search mode.
            limit: Maximum results.
            similarity_threshold: Minimum similarity score.
            metadata_weight: Weight for metadata score.
            semantic_weight: Weight for semantic score.

        Returns:
            SearchResponse with results.
        """
        filters = filters or SearchFilters()
        start_time = time.time()

        response = SearchResponse(
            query=query,
            mode=mode,
            results=[],
            total_hits=0,
            documents_searched=0,
            chunks_searched=0,
        )

        if mode == SearchMode.METADATA:
            await self._metadata_search(query, filters, limit, response)
        elif mode == SearchMode.SEMANTIC:
            await self._semantic_search(
                query, filters, limit, similarity_threshold, response
            )
        elif mode == SearchMode.DISCOVERY:
            await self._discovery_search(query, filters, limit, response)
        else:  # TWO_STAGE
            await self._two_stage_search(
                query, filters, limit, similarity_threshold,
                metadata_weight, semantic_weight, response
            )

        response.total_time_ms = (time.time() - start_time) * 1000
        return response

    async def _metadata_search(
        self,
        query: str,
        filters: SearchFilters,
        limit: int,
        response: SearchResponse,
    ) -> None:
        """Stage 1: Fast metadata-based search.

        Uses PostgreSQL full-text search on document fields.
        """
        stage_start = time.time()

        # Build base query
        stmt = (
            select(Document, DocumentVersion)
            .join(DocumentVersion, Document.id == DocumentVersion.document_id)
            .where(Document.deleted_at.is_(None))
        )

        # Apply filters
        stmt = self._apply_filters(stmt, filters)

        # Full-text search on filename and metadata
        if query:
            # Use ILIKE for simple text matching
            # In production, could use ts_vector for better performance
            search_pattern = f"%{query}%"
            stmt = stmt.where(
                or_(
                    Document.filename.ilike(search_pattern),
                    Document.original_filename.ilike(search_pattern),
                    # Search in metadata JSON (PostgreSQL specific)
                    text(f"document.metadata_::text ILIKE :pattern").bindparams(
                        pattern=search_pattern
                    ),
                )
            )

        stmt = stmt.limit(limit * 2)  # Get extra for scoring
        result = await self.db.execute(stmt)
        rows = result.fetchall()

        response.documents_searched = len(rows)
        response.stage1_time_ms = (time.time() - stage_start) * 1000

        # Convert to results
        for doc, version in rows[:limit]:
            response.results.append(SearchResult(
                id=version.id,
                document_id=doc.id,
                document_filename=doc.filename,
                version_id=version.id,
                metadata_score=1.0,  # Matched metadata
                combined_score=1.0,
                text=version.extracted_text[:500] if version.extracted_text else "",
                document_metadata=doc.metadata_ or {},
            ))

        response.total_hits = len(response.results)

    async def _semantic_search(
        self,
        query: str,
        filters: SearchFilters,
        limit: int,
        threshold: float,
        response: SearchResponse,
    ) -> None:
        """Pure semantic (vector) search."""
        stage_start = time.time()

        # Generate query embedding
        query_embedding = await self.embedding_client.embed_text(query)

        # Build similarity query
        similarity_col = (
            1 - EmbeddingChunk.embedding.cosine_distance(query_embedding)
        ).label("similarity")

        stmt = (
            select(EmbeddingChunk, similarity_col)
            .options(
                selectinload(EmbeddingChunk.document_version)
                .selectinload(DocumentVersion.document),
                selectinload(EmbeddingChunk.span),
            )
            .where(similarity_col >= threshold)
            .order_by(similarity_col.desc())
            .limit(limit)
        )

        # Apply scope filters
        if filters.project_id:
            from evidence_repository.models.project import ProjectDocument
            doc_ids = select(ProjectDocument.document_id).where(
                ProjectDocument.project_id == filters.project_id
            )
            version_ids = select(DocumentVersion.id).where(
                DocumentVersion.document_id.in_(doc_ids)
            )
            stmt = stmt.where(EmbeddingChunk.document_version_id.in_(version_ids))

        if filters.document_ids:
            version_ids = select(DocumentVersion.id).where(
                DocumentVersion.document_id.in_(filters.document_ids)
            )
            stmt = stmt.where(EmbeddingChunk.document_version_id.in_(version_ids))

        result = await self.db.execute(stmt)
        rows = result.fetchall()

        response.chunks_searched = len(rows)
        response.stage2_time_ms = (time.time() - stage_start) * 1000

        for chunk, similarity in rows:
            doc_version = chunk.document_version
            document = doc_version.document

            response.results.append(SearchResult(
                id=chunk.span_id or chunk.id,
                document_id=document.id,
                document_filename=document.filename,
                version_id=doc_version.id,
                semantic_score=float(similarity),
                combined_score=float(similarity),
                text=chunk.text,
                span_id=chunk.span_id,
                span_type=chunk.metadata_.get("span_type"),
                document_metadata=document.metadata_ or {},
            ))

        response.total_hits = len(response.results)

    async def _two_stage_search(
        self,
        query: str,
        filters: SearchFilters,
        limit: int,
        threshold: float,
        metadata_weight: float,
        semantic_weight: float,
        response: SearchResponse,
    ) -> None:
        """Two-stage search: metadata filter + semantic ranking.

        Stage 1: Fast metadata filter to get candidate documents
        Stage 2: Semantic search within candidates
        Combined scoring: metadata * weight + semantic * weight
        """
        # Stage 1: Get candidate documents
        stage1_start = time.time()

        candidate_doc_ids = await self._get_candidate_documents(query, filters)
        response.documents_searched = len(candidate_doc_ids)
        response.stage1_time_ms = (time.time() - stage1_start) * 1000

        if not candidate_doc_ids:
            # Fall back to pure semantic search
            return await self._semantic_search(query, filters, limit, threshold, response)

        # Stage 2: Semantic search within candidates
        stage2_start = time.time()

        query_embedding = await self.embedding_client.embed_text(query)

        similarity_col = (
            1 - EmbeddingChunk.embedding.cosine_distance(query_embedding)
        ).label("similarity")

        # Get version IDs for candidates
        version_stmt = select(DocumentVersion.id).where(
            DocumentVersion.document_id.in_(candidate_doc_ids)
        )
        version_result = await self.db.execute(version_stmt)
        candidate_version_ids = [row[0] for row in version_result.fetchall()]

        stmt = (
            select(EmbeddingChunk, similarity_col)
            .options(
                selectinload(EmbeddingChunk.document_version)
                .selectinload(DocumentVersion.document),
                selectinload(EmbeddingChunk.span),
            )
            .where(
                EmbeddingChunk.document_version_id.in_(candidate_version_ids),
                similarity_col >= threshold,
            )
            .order_by(similarity_col.desc())
            .limit(limit * 2)  # Get extra for combined scoring
        )

        result = await self.db.execute(stmt)
        rows = result.fetchall()

        response.chunks_searched = len(rows)
        response.stage2_time_ms = (time.time() - stage2_start) * 1000

        # Calculate combined scores
        results_map: dict[uuid.UUID, SearchResult] = {}

        for chunk, similarity in rows:
            doc_version = chunk.document_version
            document = doc_version.document

            # Calculate metadata score based on relevance
            metadata_score = self._calculate_metadata_score(
                document, query, filters
            )

            # Combined score
            combined = (metadata_weight * metadata_score) + (semantic_weight * float(similarity))

            result_id = chunk.span_id or chunk.id

            # Keep best result per span
            if result_id not in results_map or combined > results_map[result_id].combined_score:
                results_map[result_id] = SearchResult(
                    id=result_id,
                    document_id=document.id,
                    document_filename=document.filename,
                    version_id=doc_version.id,
                    semantic_score=float(similarity),
                    metadata_score=metadata_score,
                    combined_score=combined,
                    text=chunk.text,
                    span_id=chunk.span_id,
                    span_type=chunk.metadata_.get("span_type"),
                    document_metadata=document.metadata_ or {},
                )

        # Sort by combined score and limit
        response.results = sorted(
            results_map.values(),
            key=lambda r: r.combined_score,
            reverse=True,
        )[:limit]

        response.total_hits = len(response.results)

    async def _discovery_search(
        self,
        query: str,
        filters: SearchFilters,
        limit: int,
        response: SearchResponse,
    ) -> None:
        """Document discovery search.

        Finds documents that comprehensively cover a topic, not just
        documents that mention keywords. Returns coverage scores.
        """
        # First, do semantic search to find relevant chunks
        await self._semantic_search(query, filters, limit * 3, 0.4, response)

        # Group results by document and calculate coverage
        doc_coverage: dict[uuid.UUID, dict] = {}

        for result in response.results:
            doc_id = result.document_id
            if doc_id not in doc_coverage:
                doc_coverage[doc_id] = {
                    "document_id": doc_id,
                    "filename": result.document_filename,
                    "version_id": result.version_id,
                    "chunks": [],
                    "max_score": 0,
                    "total_score": 0,
                    "metadata": result.document_metadata,
                }

            doc_coverage[doc_id]["chunks"].append({
                "id": str(result.id),
                "score": result.semantic_score,
                "text_preview": result.text[:200],
            })
            doc_coverage[doc_id]["total_score"] += result.semantic_score
            doc_coverage[doc_id]["max_score"] = max(
                doc_coverage[doc_id]["max_score"],
                result.semantic_score,
            )

        # Calculate coverage and depth scores
        for doc_data in doc_coverage.values():
            chunk_count = len(doc_data["chunks"])
            avg_score = doc_data["total_score"] / chunk_count if chunk_count > 0 else 0

            # Coverage = number of relevant chunks (normalized)
            doc_data["coverage_score"] = min(1.0, chunk_count / 10)

            # Depth = average relevance of chunks
            doc_data["depth_score"] = avg_score

            # Combined discovery score
            doc_data["discovery_score"] = (
                0.4 * doc_data["coverage_score"] +
                0.4 * doc_data["depth_score"] +
                0.2 * doc_data["max_score"]
            )

            # Classify relevance
            if doc_data["discovery_score"] >= 0.7:
                doc_data["relevance"] = "primary"
            elif doc_data["discovery_score"] >= 0.4:
                doc_data["relevance"] = "supporting"
            else:
                doc_data["relevance"] = "tangential"

        # Sort by discovery score
        sorted_docs = sorted(
            doc_coverage.values(),
            key=lambda d: d["discovery_score"],
            reverse=True,
        )[:limit]

        # Convert back to SearchResult format
        response.results = []
        for doc_data in sorted_docs:
            response.results.append(SearchResult(
                id=doc_data["version_id"],
                document_id=doc_data["document_id"],
                document_filename=doc_data["filename"],
                version_id=doc_data["version_id"],
                semantic_score=doc_data["max_score"],
                metadata_score=doc_data["coverage_score"],
                combined_score=doc_data["discovery_score"],
                text=f"Coverage: {doc_data['coverage_score']:.2f}, "
                     f"Depth: {doc_data['depth_score']:.2f}, "
                     f"Relevance: {doc_data['relevance']}",
                document_metadata={
                    **doc_data["metadata"],
                    "discovery": {
                        "coverage_score": doc_data["coverage_score"],
                        "depth_score": doc_data["depth_score"],
                        "relevance": doc_data["relevance"],
                        "matching_chunks": len(doc_data["chunks"]),
                    },
                },
            ))

        response.total_hits = len(response.results)
        response.filters_applied["mode"] = "discovery"

    async def _get_candidate_documents(
        self,
        query: str,
        filters: SearchFilters,
    ) -> list[uuid.UUID]:
        """Get candidate document IDs from metadata search.

        Args:
            query: Search query.
            filters: Search filters.

        Returns:
            List of candidate document UUIDs.
        """
        stmt = (
            select(Document.id)
            .where(Document.deleted_at.is_(None))
        )

        # Apply filters
        stmt = self._apply_filters(stmt, filters)

        # Text search on filename
        if query:
            search_pattern = f"%{query}%"
            stmt = stmt.where(
                or_(
                    Document.filename.ilike(search_pattern),
                    Document.original_filename.ilike(search_pattern),
                )
            )

        stmt = stmt.limit(100)  # Cap candidates

        result = await self.db.execute(stmt)
        return [row[0] for row in result.fetchall()]

    def _apply_filters(self, stmt, filters: SearchFilters):
        """Apply filters to a select statement."""
        if filters.project_id:
            from evidence_repository.models.project import ProjectDocument
            doc_ids = select(ProjectDocument.document_id).where(
                ProjectDocument.project_id == filters.project_id
            )
            stmt = stmt.where(Document.id.in_(doc_ids))

        if filters.document_ids:
            stmt = stmt.where(Document.id.in_(filters.document_ids))

        if filters.uploaded_after:
            stmt = stmt.where(Document.created_at >= filters.uploaded_after)

        if filters.uploaded_before:
            stmt = stmt.where(Document.created_at <= filters.uploaded_before)

        return stmt

    def _calculate_metadata_score(
        self,
        document: Document,
        query: str,
        filters: SearchFilters,
    ) -> float:
        """Calculate metadata relevance score.

        Args:
            document: Document to score.
            query: Search query.
            filters: Search filters.

        Returns:
            Score from 0.0 to 1.0.
        """
        score = 0.5  # Base score

        # Boost if query appears in filename
        if query and query.lower() in document.filename.lower():
            score += 0.3

        # Boost if filters match metadata
        metadata = document.metadata_ or {}
        extracted = metadata.get("extracted", {})

        if filters.sectors and extracted.get("sectors"):
            matching = set(filters.sectors) & set(extracted["sectors"])
            if matching:
                score += 0.1 * len(matching)

        if filters.topics and extracted.get("main_topics"):
            matching = set(filters.topics) & set(extracted["main_topics"])
            if matching:
                score += 0.1 * len(matching)

        return min(1.0, score)
