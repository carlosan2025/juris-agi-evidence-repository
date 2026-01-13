"""Search business service layer."""

import time
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from evidence_repository.embeddings.openai_client import OpenAIEmbeddingClient
from evidence_repository.models.document import Document, DocumentVersion
from evidence_repository.models.embedding import EmbeddingChunk
from evidence_repository.models.project import ProjectDocument


@dataclass
class SearchResultItem:
    """Single search result."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_version_id: uuid.UUID
    span_id: uuid.UUID | None
    text: str
    similarity: float
    chunk_index: int
    char_start: int | None
    char_end: int | None
    document_filename: str
    document_content_type: str
    metadata: dict


@dataclass
class SearchResults:
    """Collection of search results."""

    query: str
    results: list[SearchResultItem]
    total: int
    search_time_ms: float
    timestamp: datetime


class SearchService:
    """Semantic search service using pgvector."""

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
    ) -> SearchResults:
        """Perform semantic search across documents.

        Args:
            query: Search query text.
            limit: Maximum number of results.
            similarity_threshold: Minimum similarity score (0-1).
            project_id: Optional project to scope search to.
            document_ids: Optional specific documents to search.

        Returns:
            SearchResults with matching chunks.
        """
        start_time = time.time()

        # Generate query embedding
        query_embedding = await self.embedding_client.embed_text(query)

        # Build similarity expression
        similarity_col = (
            1 - EmbeddingChunk.embedding.cosine_distance(query_embedding)
        ).label("similarity")

        # Base query
        search_query = (
            select(EmbeddingChunk, similarity_col)
            .options(
                selectinload(EmbeddingChunk.document_version).selectinload(
                    DocumentVersion.document
                )
            )
            .where(similarity_col >= similarity_threshold)
            .order_by(similarity_col.desc())
            .limit(limit)
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

        # Build results
        results = []
        for chunk, similarity in rows:
            doc_version = chunk.document_version
            document = doc_version.document

            results.append(
                SearchResultItem(
                    chunk_id=chunk.id,
                    document_id=document.id,
                    document_version_id=doc_version.id,
                    span_id=chunk.span_id,
                    text=chunk.text,
                    similarity=float(similarity),
                    chunk_index=chunk.chunk_index,
                    char_start=chunk.char_start,
                    char_end=chunk.char_end,
                    document_filename=document.filename,
                    document_content_type=document.content_type,
                    metadata=chunk.metadata_,
                )
            )

        return SearchResults(
            query=query,
            results=results,
            total=len(results),
            search_time_ms=(time.time() - start_time) * 1000,
            timestamp=datetime.utcnow(),
        )

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
            SearchResults with similar chunks.
        """
        start_time = time.time()

        # Get source chunk
        source_result = await self.db.execute(
            select(EmbeddingChunk)
            .options(selectinload(EmbeddingChunk.document_version))
            .where(EmbeddingChunk.id == chunk_id)
        )
        source_chunk = source_result.scalar_one_or_none()

        if not source_chunk:
            return SearchResults(
                query=f"similar_to:{chunk_id}",
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
                )
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
            doc_version = chunk.document_version
            document = doc_version.document

            results.append(
                SearchResultItem(
                    chunk_id=chunk.id,
                    document_id=document.id,
                    document_version_id=doc_version.id,
                    span_id=chunk.span_id,
                    text=chunk.text,
                    similarity=float(similarity),
                    chunk_index=chunk.chunk_index,
                    char_start=chunk.char_start,
                    char_end=chunk.char_end,
                    document_filename=document.filename,
                    document_content_type=document.content_type,
                    metadata=chunk.metadata_,
                )
            )

        return SearchResults(
            query=f"similar_to:{chunk_id}",
            results=results,
            total=len(results),
            search_time_ms=(time.time() - start_time) * 1000,
            timestamp=datetime.utcnow(),
        )
