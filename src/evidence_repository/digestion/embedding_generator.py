"""Embedding generator for document sections.

Generates vector embeddings for sections using OpenAI's embedding API.
"""

import logging
from typing import List

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from evidence_repository.config import get_settings
from evidence_repository.models.document import DocumentVersion
from evidence_repository.models.embedding import EmbeddingChunk
from evidence_repository.models.evidence import Span, SpanType

logger = logging.getLogger(__name__)

# Span types that should be embedded
EMBEDDABLE_SPAN_TYPES = {
    SpanType.TEXT,
    SpanType.HEADING,
    SpanType.CITATION,
    SpanType.FOOTNOTE,
}


async def generate_embeddings(
    db: AsyncSession,
    version: DocumentVersion,
    force_regenerate: bool = False,
    batch_size: int = 50,
) -> int:
    """Generate embeddings for all embeddable spans.

    Args:
        db: Async database session.
        version: DocumentVersion to embed.
        force_regenerate: Delete existing embeddings first.
        batch_size: Embeddings to generate per batch.

    Returns:
        Number of embeddings created.
    """
    from evidence_repository.embeddings.openai_client import OpenAIEmbeddingClient

    # Get embeddable spans
    spans_result = await db.execute(
        select(Span)
        .where(
            Span.document_version_id == version.id,
            Span.span_type.in_(EMBEDDABLE_SPAN_TYPES),
        )
        .order_by(Span.created_at)
    )
    spans = spans_result.scalars().all()

    if not spans:
        logger.info(f"No embeddable spans for version {version.id}")
        return 0

    # Get existing embeddings
    existing_span_ids = set()
    if not force_regenerate:
        existing_result = await db.execute(
            select(EmbeddingChunk.span_id)
            .where(
                EmbeddingChunk.document_version_id == version.id,
                EmbeddingChunk.span_id.isnot(None),
            )
        )
        existing_span_ids = {row[0] for row in existing_result.fetchall()}
    else:
        # Delete existing embeddings
        await db.execute(
            delete(EmbeddingChunk)
            .where(EmbeddingChunk.document_version_id == version.id)
        )
        await db.flush()

    # Filter spans that need embedding
    spans_to_embed = [
        s for s in spans
        if s.id not in existing_span_ids
        and s.text_content
        and s.text_content.strip()
    ]

    if not spans_to_embed:
        logger.info(f"All spans already embedded for version {version.id}")
        return len(spans)

    # Generate embeddings in batches
    client = OpenAIEmbeddingClient()
    created = 0

    for batch_start in range(0, len(spans_to_embed), batch_size):
        batch_end = min(batch_start + batch_size, len(spans_to_embed))
        batch_spans = spans_to_embed[batch_start:batch_end]

        texts = [s.text_content for s in batch_spans]

        try:
            embeddings = await client.embed_texts(texts)

            for span, embedding in zip(batch_spans, embeddings):
                chunk = EmbeddingChunk(
                    document_version_id=version.id,
                    span_id=span.id,
                    chunk_index=created,
                    text=span.text_content,
                    embedding=embedding,
                    metadata_={
                        "span_type": span.span_type.value,
                        "span_hash": span.span_hash,
                    },
                )
                db.add(chunk)
                created += 1

            await db.flush()

        except Exception as e:
            logger.error(f"Batch embedding failed: {e}")
            raise

    logger.info(
        f"Created {created} embeddings for version {version.id} "
        f"(tokens: {client.get_token_usage()})"
    )

    return created
