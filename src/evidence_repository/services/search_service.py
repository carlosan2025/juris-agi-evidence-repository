"""Search business service layer."""

import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from evidence_repository.embeddings.openai_client import OpenAIEmbeddingClient
from evidence_repository.models.document import Document, DocumentVersion
from evidence_repository.models.embedding import EmbeddingChunk
from evidence_repository.models.evidence import Span, SpanType
from evidence_repository.models.project import ProjectDocument


class SearchMode(str, Enum):
    """Search mode options."""

    SEMANTIC = "semantic"  # Vector similarity search only
    KEYWORD = "keyword"  # Full-text keyword search only
    HYBRID = "hybrid"  # Combined semantic + keyword search


@dataclass
class SpanLocator:
    """Location reference within a document."""

    type: str
    page: int | None = None
    bbox: dict[str, float] | None = None
    sheet: str | None = None
    cell_range: str | None = None
    char_offset_start: int | None = None
    char_offset_end: int | None = None


@dataclass
class Citation:
    """Citation reference to a document span."""

    span_id: uuid.UUID
    document_id: uuid.UUID
    document_version_id: uuid.UUID
    document_filename: str
    span_type: str
    locator: SpanLocator
    text_excerpt: str


@dataclass
class SearchResultItem:
    """Single search result with citation."""

    result_id: uuid.UUID
    similarity: float
    citation: Citation
    matched_text: str
    highlight_ranges: list[dict[str, int]] | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class SearchResults:
    """Collection of search results."""

    query: str
    mode: SearchMode
    results: list[SearchResultItem]
    total: int
    search_time_ms: float
    timestamp: datetime
    filters_applied: dict[str, Any] = field(default_factory=dict)


class SearchService:
    """Semantic search service using pgvector with keyword filtering."""

    def __init__(
        self,
        db: AsyncSession,
        embedding_client: OpenAIEmbeddingClient | None = None,
    ):
        """Initialize search service.

        Args:
            db: Database session.
            embedding_client: OpenAI client for query embedding.
        """
        self.db = db
        self.embedding_client = embedding_client or OpenAIEmbeddingClient()

    async def search(
        self,
        query: str,
        limit: int = 10,
        similarity_threshold: float = 0.7,
        project_id: uuid.UUID | None = None,
        document_ids: list[uuid.UUID] | None = None,
        mode: SearchMode = SearchMode.SEMANTIC,
        span_types: list[SpanType] | None = None,
        keywords: list[str] | None = None,
        exclude_keywords: list[str] | None = None,
        spans_only: bool = False,
    ) -> SearchResults:
        """Perform search across documents with citations.

        Args:
            query: Search query text.
            limit: Maximum number of results.
            similarity_threshold: Minimum similarity score (0-1).
            project_id: Optional project to scope search to.
            document_ids: Optional specific documents to search.
            mode: Search mode (SEMANTIC, KEYWORD, HYBRID).
            span_types: Optional filter for specific span types.
            keywords: Keywords that must appear in results (AND logic).
            exclude_keywords: Keywords to exclude from results.
            spans_only: Only return results with associated spans.

        Returns:
            SearchResults with matching spans/chunks as citations.
        """
        start_time = time.time()
        filters_applied: dict[str, Any] = {}

        # Build base query depending on mode
        if mode == SearchMode.KEYWORD:
            # Keyword-only search
            results = await self._keyword_search(
                query=query,
                limit=limit,
                project_id=project_id,
                document_ids=document_ids,
                span_types=span_types,
                keywords=keywords,
                exclude_keywords=exclude_keywords,
                spans_only=spans_only,
            )
            filters_applied["mode"] = "keyword"
        elif mode == SearchMode.HYBRID:
            # Combined semantic + keyword search
            results = await self._hybrid_search(
                query=query,
                limit=limit,
                similarity_threshold=similarity_threshold,
                project_id=project_id,
                document_ids=document_ids,
                span_types=span_types,
                keywords=keywords,
                exclude_keywords=exclude_keywords,
                spans_only=spans_only,
            )
            filters_applied["mode"] = "hybrid"
        else:
            # Semantic search (default)
            results = await self._semantic_search(
                query=query,
                limit=limit,
                similarity_threshold=similarity_threshold,
                project_id=project_id,
                document_ids=document_ids,
                span_types=span_types,
                keywords=keywords,
                exclude_keywords=exclude_keywords,
                spans_only=spans_only,
            )
            filters_applied["mode"] = "semantic"

        # Record filters applied
        if project_id:
            filters_applied["project_id"] = str(project_id)
        if document_ids:
            filters_applied["document_ids"] = [str(d) for d in document_ids]
        if span_types:
            filters_applied["span_types"] = [st.value for st in span_types]
        if keywords:
            filters_applied["keywords"] = keywords
        if exclude_keywords:
            filters_applied["exclude_keywords"] = exclude_keywords
        if spans_only:
            filters_applied["spans_only"] = True

        return SearchResults(
            query=query,
            mode=mode,
            results=results,
            total=len(results),
            search_time_ms=(time.time() - start_time) * 1000,
            timestamp=datetime.utcnow(),
            filters_applied=filters_applied,
        )

    async def _semantic_search(
        self,
        query: str,
        limit: int,
        similarity_threshold: float,
        project_id: uuid.UUID | None,
        document_ids: list[uuid.UUID] | None,
        span_types: list[SpanType] | None,
        keywords: list[str] | None,
        exclude_keywords: list[str] | None,
        spans_only: bool,
    ) -> list[SearchResultItem]:
        """Perform vector similarity search with optional keyword filtering."""
        # Generate query embedding
        query_embedding = await self.embedding_client.embed_text(query)

        # Build similarity expression
        similarity_col = (
            1 - EmbeddingChunk.embedding.cosine_distance(query_embedding)
        ).label("similarity")

        # Base query with eager loading - fetch more to allow for keyword filtering
        fetch_limit = limit * 3 if (keywords or exclude_keywords) else limit

        search_query = (
            select(EmbeddingChunk, similarity_col)
            .options(
                selectinload(EmbeddingChunk.document_version).selectinload(
                    DocumentVersion.document
                ),
                selectinload(EmbeddingChunk.span),
            )
            .where(similarity_col >= similarity_threshold)
            .order_by(similarity_col.desc())
            .limit(fetch_limit)
        )

        # Apply spans_only filter
        if spans_only:
            search_query = search_query.where(EmbeddingChunk.span_id.isnot(None))

        # Apply span type filter
        if span_types:
            span_type_subquery = select(Span.id).where(
                Span.span_type.in_(span_types)
            )
            if spans_only:
                search_query = search_query.where(
                    EmbeddingChunk.span_id.in_(span_type_subquery)
                )
            else:
                search_query = search_query.where(
                    or_(
                        EmbeddingChunk.span_id.in_(span_type_subquery),
                        EmbeddingChunk.span_id.is_(None),
                    )
                )

        # Apply project filter
        if project_id:
            doc_ids_subquery = select(ProjectDocument.document_id).where(
                ProjectDocument.project_id == project_id
            )
            version_ids_subquery = select(DocumentVersion.id).where(
                DocumentVersion.document_id.in_(doc_ids_subquery)
            )
            search_query = search_query.where(
                EmbeddingChunk.document_version_id.in_(version_ids_subquery)
            )

        # Apply document filter
        if document_ids:
            version_ids_subquery = select(DocumentVersion.id).where(
                DocumentVersion.document_id.in_(document_ids)
            )
            search_query = search_query.where(
                EmbeddingChunk.document_version_id.in_(version_ids_subquery)
            )

        # Execute search
        result = await self.db.execute(search_query)
        rows = result.fetchall()

        # Build results with keyword filtering
        results = []
        for chunk, similarity in rows:
            if len(results) >= limit:
                break

            text = chunk.text
            span = chunk.span

            # Apply keyword filters
            if not self._passes_keyword_filter(text, keywords, exclude_keywords):
                continue

            # Build citation
            citation = self._build_citation(chunk, span)

            # Calculate highlight ranges for keywords
            highlight_ranges = self._calculate_highlights(text, keywords)

            results.append(
                SearchResultItem(
                    result_id=span.id if span else chunk.id,
                    similarity=float(similarity),
                    citation=citation,
                    matched_text=text,
                    highlight_ranges=highlight_ranges,
                    metadata=chunk.metadata_,
                )
            )

        return results

    async def _keyword_search(
        self,
        query: str,
        limit: int,
        project_id: uuid.UUID | None,
        document_ids: list[uuid.UUID] | None,
        span_types: list[SpanType] | None,
        keywords: list[str] | None,
        exclude_keywords: list[str] | None,
        spans_only: bool,
    ) -> list[SearchResultItem]:
        """Perform full-text keyword search."""
        # Combine query terms with keywords for search
        search_terms = [query]
        if keywords:
            search_terms.extend(keywords)

        # Build query using ILIKE for keyword matching
        conditions = []
        for term in search_terms:
            conditions.append(EmbeddingChunk.text.ilike(f"%{term}%"))

        search_query = (
            select(EmbeddingChunk)
            .options(
                selectinload(EmbeddingChunk.document_version).selectinload(
                    DocumentVersion.document
                ),
                selectinload(EmbeddingChunk.span),
            )
            .where(and_(*conditions))
            .limit(limit * 2)  # Fetch extra for filtering
        )

        # Apply spans_only filter
        if spans_only:
            search_query = search_query.where(EmbeddingChunk.span_id.isnot(None))

        # Apply span type filter
        if span_types:
            span_type_subquery = select(Span.id).where(
                Span.span_type.in_(span_types)
            )
            if spans_only:
                search_query = search_query.where(
                    EmbeddingChunk.span_id.in_(span_type_subquery)
                )
            else:
                search_query = search_query.where(
                    or_(
                        EmbeddingChunk.span_id.in_(span_type_subquery),
                        EmbeddingChunk.span_id.is_(None),
                    )
                )

        # Apply project filter
        if project_id:
            doc_ids_subquery = select(ProjectDocument.document_id).where(
                ProjectDocument.project_id == project_id
            )
            version_ids_subquery = select(DocumentVersion.id).where(
                DocumentVersion.document_id.in_(doc_ids_subquery)
            )
            search_query = search_query.where(
                EmbeddingChunk.document_version_id.in_(version_ids_subquery)
            )

        # Apply document filter
        if document_ids:
            version_ids_subquery = select(DocumentVersion.id).where(
                DocumentVersion.document_id.in_(document_ids)
            )
            search_query = search_query.where(
                EmbeddingChunk.document_version_id.in_(version_ids_subquery)
            )

        # Execute search
        result = await self.db.execute(search_query)
        chunks = result.scalars().all()

        # Build results with exclude filtering and scoring
        results = []
        for chunk in chunks:
            if len(results) >= limit:
                break

            text = chunk.text
            span = chunk.span

            # Apply exclude keyword filter
            if exclude_keywords:
                if not self._passes_keyword_filter(text, None, exclude_keywords):
                    continue

            # Calculate relevance score based on keyword matches
            relevance = self._calculate_keyword_relevance(text, search_terms)

            # Build citation
            citation = self._build_citation(chunk, span)

            # Calculate highlight ranges
            highlight_ranges = self._calculate_highlights(text, search_terms)

            results.append(
                SearchResultItem(
                    result_id=span.id if span else chunk.id,
                    similarity=relevance,
                    citation=citation,
                    matched_text=text,
                    highlight_ranges=highlight_ranges,
                    metadata=chunk.metadata_,
                )
            )

        # Sort by relevance
        results.sort(key=lambda x: x.similarity, reverse=True)
        return results[:limit]

    async def _hybrid_search(
        self,
        query: str,
        limit: int,
        similarity_threshold: float,
        project_id: uuid.UUID | None,
        document_ids: list[uuid.UUID] | None,
        span_types: list[SpanType] | None,
        keywords: list[str] | None,
        exclude_keywords: list[str] | None,
        spans_only: bool,
    ) -> list[SearchResultItem]:
        """Perform combined semantic + keyword search with score fusion."""
        # Get semantic results
        semantic_results = await self._semantic_search(
            query=query,
            limit=limit,
            similarity_threshold=similarity_threshold,
            project_id=project_id,
            document_ids=document_ids,
            span_types=span_types,
            keywords=keywords,
            exclude_keywords=exclude_keywords,
            spans_only=spans_only,
        )

        # Get keyword results
        keyword_results = await self._keyword_search(
            query=query,
            limit=limit,
            project_id=project_id,
            document_ids=document_ids,
            span_types=span_types,
            keywords=keywords,
            exclude_keywords=exclude_keywords,
            spans_only=spans_only,
        )

        # Merge and deduplicate using Reciprocal Rank Fusion (RRF)
        k = 60  # RRF constant
        scores: dict[uuid.UUID, float] = {}
        results_map: dict[uuid.UUID, SearchResultItem] = {}

        for rank, result in enumerate(semantic_results):
            rrf_score = 1.0 / (k + rank + 1)
            scores[result.result_id] = scores.get(result.result_id, 0) + rrf_score
            results_map[result.result_id] = result

        for rank, result in enumerate(keyword_results):
            rrf_score = 1.0 / (k + rank + 1)
            scores[result.result_id] = scores.get(result.result_id, 0) + rrf_score
            if result.result_id not in results_map:
                results_map[result.result_id] = result

        # Sort by combined score and return top results
        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)

        results = []
        for result_id in sorted_ids[:limit]:
            result = results_map[result_id]
            # Update similarity to reflect combined score
            result.similarity = min(1.0, scores[result_id] * 10)  # Normalize
            results.append(result)

        return results

    def _build_citation(self, chunk: EmbeddingChunk, span: Span | None) -> Citation:
        """Build a citation from a chunk and optional span."""
        doc_version = chunk.document_version
        document = doc_version.document

        if span:
            # Use span information for citation
            locator_data = span.start_locator
            locator = SpanLocator(
                type=locator_data.get("type", "text"),
                page=locator_data.get("page"),
                bbox=locator_data.get("bbox"),
                sheet=locator_data.get("sheet"),
                cell_range=locator_data.get("cell_range"),
                char_offset_start=locator_data.get("char_offset_start"),
                char_offset_end=locator_data.get("char_offset_end"),
            )
            return Citation(
                span_id=span.id,
                document_id=document.id,
                document_version_id=doc_version.id,
                document_filename=document.filename,
                span_type=span.span_type.value,
                locator=locator,
                text_excerpt=span.text_content[:500] if span.text_content else "",
            )
        else:
            # Create citation from chunk info
            locator = SpanLocator(
                type="text",
                char_offset_start=chunk.char_start,
                char_offset_end=chunk.char_end,
            )
            return Citation(
                span_id=chunk.id,  # Use chunk ID as fallback
                document_id=document.id,
                document_version_id=doc_version.id,
                document_filename=document.filename,
                span_type="text",
                locator=locator,
                text_excerpt=chunk.text[:500] if chunk.text else "",
            )

    def _passes_keyword_filter(
        self,
        text: str,
        keywords: list[str] | None,
        exclude_keywords: list[str] | None,
    ) -> bool:
        """Check if text passes keyword inclusion/exclusion filters."""
        text_lower = text.lower()

        # Check required keywords (AND logic)
        if keywords:
            for keyword in keywords:
                if keyword.lower() not in text_lower:
                    return False

        # Check excluded keywords
        if exclude_keywords:
            for keyword in exclude_keywords:
                if keyword.lower() in text_lower:
                    return False

        return True

    def _calculate_keyword_relevance(
        self, text: str, keywords: list[str]
    ) -> float:
        """Calculate relevance score based on keyword frequency."""
        if not keywords:
            return 0.5

        text_lower = text.lower()
        total_matches = 0
        total_possible = len(keywords)

        for keyword in keywords:
            keyword_lower = keyword.lower()
            # Count occurrences
            count = text_lower.count(keyword_lower)
            if count > 0:
                total_matches += min(count, 3)  # Cap at 3 matches per keyword

        # Normalize to 0-1 range
        return min(1.0, total_matches / (total_possible * 2))

    def _calculate_highlights(
        self, text: str, keywords: list[str] | None
    ) -> list[dict[str, int]] | None:
        """Calculate character ranges for keyword highlights."""
        if not keywords:
            return None

        highlights = []
        text_lower = text.lower()

        for keyword in keywords:
            keyword_lower = keyword.lower()
            start = 0
            while True:
                pos = text_lower.find(keyword_lower, start)
                if pos == -1:
                    break
                highlights.append({"start": pos, "end": pos + len(keyword)})
                start = pos + 1

        # Sort by position and merge overlapping ranges
        if not highlights:
            return None

        highlights.sort(key=lambda x: x["start"])
        merged = [highlights[0]]
        for h in highlights[1:]:
            if h["start"] <= merged[-1]["end"]:
                merged[-1]["end"] = max(merged[-1]["end"], h["end"])
            else:
                merged.append(h)

        return merged

    async def find_similar_chunks(
        self,
        chunk_id: uuid.UUID,
        limit: int = 5,
        exclude_same_document: bool = True,
    ) -> SearchResults:
        """Find chunks similar to a given chunk.

        Useful for finding related content across documents.

        Args:
            chunk_id: Source chunk ID.
            limit: Maximum results.
            exclude_same_document: Whether to exclude chunks from same document.

        Returns:
            SearchResults with similar chunks as citations.
        """
        start_time = time.time()

        # Get source chunk
        source_result = await self.db.execute(
            select(EmbeddingChunk)
            .options(
                selectinload(EmbeddingChunk.document_version),
                selectinload(EmbeddingChunk.span),
            )
            .where(EmbeddingChunk.id == chunk_id)
        )
        source_chunk = source_result.scalar_one_or_none()

        if not source_chunk:
            return SearchResults(
                query=f"similar_to:{chunk_id}",
                mode=SearchMode.SEMANTIC,
                results=[],
                total=0,
                search_time_ms=(time.time() - start_time) * 1000,
                timestamp=datetime.utcnow(),
            )

        # Search using source embedding
        similarity_col = (
            1 - EmbeddingChunk.embedding.cosine_distance(source_chunk.embedding)
        ).label("similarity")

        search_query = (
            select(EmbeddingChunk, similarity_col)
            .options(
                selectinload(EmbeddingChunk.document_version).selectinload(
                    DocumentVersion.document
                ),
                selectinload(EmbeddingChunk.span),
            )
            .where(
                EmbeddingChunk.id != chunk_id,  # Exclude source
                similarity_col >= 0.5,  # Minimum threshold
            )
            .order_by(similarity_col.desc())
            .limit(limit)
        )

        if exclude_same_document:
            search_query = search_query.where(
                EmbeddingChunk.document_version_id
                != source_chunk.document_version_id
            )

        result = await self.db.execute(search_query)
        rows = result.fetchall()

        results = []
        for chunk, similarity in rows:
            span = chunk.span
            citation = self._build_citation(chunk, span)

            results.append(
                SearchResultItem(
                    result_id=span.id if span else chunk.id,
                    similarity=float(similarity),
                    citation=citation,
                    matched_text=chunk.text,
                    metadata=chunk.metadata_,
                )
            )

        return SearchResults(
            query=f"similar_to:{chunk_id}",
            mode=SearchMode.SEMANTIC,
            results=results,
            total=len(results),
            search_time_ms=(time.time() - start_time) * 1000,
            timestamp=datetime.utcnow(),
        )
