"""Span embedding service for generating embeddings from text spans."""

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from evidence_repository.embeddings.openai_client import OpenAIEmbeddingClient
from evidence_repository.models.document import DocumentVersion
from evidence_repository.models.embedding import EmbeddingChunk
from evidence_repository.models.evidence import Span, SpanType

logger = logging.getLogger(__name__)


class SpanEmbeddingService:
    """Service for embedding text spans.

    Only embeds text-type spans (not tables or figures).
    Stores embeddings in embedding_chunks with span_id reference.

    Features:
    - Batch embedding for efficiency
    - Re-embedding support per version
    - Link embeddings to source spans
    - Skip non-text spans
    """

    # Span types to embed (only text content)
    EMBEDDABLE_SPAN_TYPES = {SpanType.TEXT, SpanType.HEADING, SpanType.CITATION, SpanType.FOOTNOTE}

    def __init__(
        self,
        db: AsyncSession,
        embedding_client: OpenAIEmbeddingClient | None = None,
        batch_size: int = 50,
    ):
        """Initialize span embedding service.

        Args:
            db: Database session.
            embedding_client: OpenAI client (created if not provided).
            batch_size: Number of spans to embed per batch.
        """
        self.db = db
        self.embedding_client = embedding_client or OpenAIEmbeddingClient()
        self.batch_size = batch_size

    async def embed_spans_for_version(
        self,
        version: DocumentVersion,
        reprocess: bool = False,
    ) -> list[EmbeddingChunk]:
        """Embed all text spans for a document version.

        Args:
            version: Document version with spans.
            reprocess: If True, delete existing embeddings first.

        Returns:
            List of created EmbeddingChunk records.
        """
        # Get text spans for this version
        spans = await self._get_embeddable_spans(version.id)

        if not spans:
            logger.info(f"No embeddable spans found for version {version.id}")
            return []

        # Delete existing embeddings if reprocessing
        if reprocess:
            deleted = await self.delete_version_embeddings(version.id)
            logger.info(f"Deleted {deleted} existing embeddings for version {version.id}")

        logger.info(f"Embedding {len(spans)} spans for version {version.id}")

        # Embed in batches
        all_chunks: list[EmbeddingChunk] = []

        for batch_start in range(0, len(spans), self.batch_size):
            batch_end = min(batch_start + self.batch_size, len(spans))
            batch_spans = spans[batch_start:batch_end]

            chunks = await self._embed_span_batch(batch_spans, version.id)
            all_chunks.extend(chunks)

            logger.debug(
                f"Embedded batch {batch_start // self.batch_size + 1}: "
                f"{len(chunks)} chunks"
            )

        await self.db.flush()

        logger.info(
            f"Created {len(all_chunks)} embeddings for version {version.id} "
            f"(tokens used: {self.embedding_client.get_token_usage()})"
        )

        return all_chunks

    async def embed_single_span(self, span: Span) -> EmbeddingChunk | None:
        """Embed a single span.

        Args:
            span: Span to embed.

        Returns:
            Created EmbeddingChunk or None if span is not embeddable.
        """
        if span.span_type not in self.EMBEDDABLE_SPAN_TYPES:
            logger.debug(f"Skipping non-text span {span.id} (type: {span.span_type})")
            return None

        if not span.text_content or not span.text_content.strip():
            logger.debug(f"Skipping empty span {span.id}")
            return None

        # Check for existing embedding
        existing = await self._get_span_embedding(span.id)
        if existing:
            logger.debug(f"Span {span.id} already has embedding")
            return existing

        # Generate embedding
        embedding = await self.embedding_client.embed_text(span.text_content)

        # Create chunk record
        chunk = EmbeddingChunk(
            document_version_id=span.document_version_id,
            span_id=span.id,
            chunk_index=0,
            text=span.text_content,
            embedding=embedding,
            metadata_={
                "span_type": span.span_type.value,
                "span_hash": span.span_hash,
                "locator": span.start_locator,
            },
        )
        self.db.add(chunk)
        await self.db.flush()

        return chunk

    async def reembed_version(
        self,
        version_id: UUID,
    ) -> list[EmbeddingChunk]:
        """Re-embed all spans for a version (delete and recreate).

        Args:
            version_id: Document version ID to re-embed.

        Returns:
            List of newly created EmbeddingChunk records.
        """
        # Get version with document
        result = await self.db.execute(
            select(DocumentVersion)
            .options(selectinload(DocumentVersion.document))
            .where(DocumentVersion.id == version_id)
        )
        version = result.scalar_one_or_none()

        if not version:
            raise ValueError(f"Version {version_id} not found")

        return await self.embed_spans_for_version(version, reprocess=True)

    async def _get_embeddable_spans(self, version_id: UUID) -> list[Span]:
        """Get all embeddable spans for a version.

        Args:
            version_id: Document version ID.

        Returns:
            List of text-type Span records.
        """
        result = await self.db.execute(
            select(Span)
            .where(
                Span.document_version_id == version_id,
                Span.span_type.in_(self.EMBEDDABLE_SPAN_TYPES),
            )
            .order_by(Span.created_at)
        )
        return list(result.scalars().all())

    async def _embed_span_batch(
        self,
        spans: list[Span],
        version_id: UUID,
    ) -> list[EmbeddingChunk]:
        """Embed a batch of spans.

        Args:
            spans: Spans to embed.
            version_id: Document version ID.

        Returns:
            List of created EmbeddingChunk records.
        """
        # Filter out empty spans and check for existing embeddings
        valid_spans: list[Span] = []
        existing_span_ids: set[UUID] = set()

        # Check for existing embeddings
        span_ids = [s.id for s in spans]
        result = await self.db.execute(
            select(EmbeddingChunk.span_id)
            .where(EmbeddingChunk.span_id.in_(span_ids))
        )
        existing_span_ids = {row[0] for row in result.fetchall()}

        for span in spans:
            if span.id in existing_span_ids:
                continue
            if not span.text_content or not span.text_content.strip():
                continue
            valid_spans.append(span)

        if not valid_spans:
            return []

        # Generate embeddings
        texts = [s.text_content for s in valid_spans]
        embeddings = await self.embedding_client.embed_texts(texts)

        # Create chunk records
        chunks: list[EmbeddingChunk] = []
        for span, embedding, idx in zip(valid_spans, embeddings, range(len(valid_spans))):
            chunk = EmbeddingChunk(
                document_version_id=version_id,
                span_id=span.id,
                chunk_index=idx,
                text=span.text_content,
                embedding=embedding,
                metadata_={
                    "span_type": span.span_type.value,
                    "span_hash": span.span_hash,
                    "locator": span.start_locator,
                },
            )
            self.db.add(chunk)
            chunks.append(chunk)

        return chunks

    async def _get_span_embedding(self, span_id: UUID) -> EmbeddingChunk | None:
        """Get existing embedding for a span.

        Args:
            span_id: Span ID.

        Returns:
            EmbeddingChunk or None.
        """
        result = await self.db.execute(
            select(EmbeddingChunk).where(EmbeddingChunk.span_id == span_id)
        )
        return result.scalar_one_or_none()

    async def delete_version_embeddings(self, version_id: UUID) -> int:
        """Delete all span embeddings for a version.

        Args:
            version_id: Document version ID.

        Returns:
            Number of embeddings deleted.
        """
        result = await self.db.execute(
            delete(EmbeddingChunk).where(
                EmbeddingChunk.document_version_id == version_id,
                EmbeddingChunk.span_id.isnot(None),  # Only span embeddings
            )
        )
        await self.db.flush()
        return result.rowcount

    async def delete_span_embedding(self, span_id: UUID) -> bool:
        """Delete embedding for a specific span.

        Args:
            span_id: Span ID.

        Returns:
            True if deleted, False if not found.
        """
        result = await self.db.execute(
            delete(EmbeddingChunk).where(EmbeddingChunk.span_id == span_id)
        )
        await self.db.flush()
        return result.rowcount > 0

    async def get_embedding_stats(self, version_id: UUID) -> dict[str, Any]:
        """Get embedding statistics for a version.

        Args:
            version_id: Document version ID.

        Returns:
            Dict with embedding statistics.
        """
        # Count spans by type
        spans = await self._get_embeddable_spans(version_id)
        span_count = len(spans)

        # Count existing embeddings
        result = await self.db.execute(
            select(EmbeddingChunk)
            .where(
                EmbeddingChunk.document_version_id == version_id,
                EmbeddingChunk.span_id.isnot(None),
            )
        )
        embeddings = list(result.scalars().all())
        embedding_count = len(embeddings)

        return {
            "version_id": str(version_id),
            "embeddable_spans": span_count,
            "embedded_spans": embedding_count,
            "pending_spans": span_count - embedding_count,
            "complete": span_count == embedding_count and span_count > 0,
        }
