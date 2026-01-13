"""Embedding generation and management service."""

import logging
import uuid

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from evidence_repository.config import get_settings
from evidence_repository.embeddings.chunker import TextChunk, TextChunker
from evidence_repository.embeddings.openai_client import OpenAIEmbeddingClient
from evidence_repository.models.document import DocumentVersion
from evidence_repository.models.embedding import EmbeddingChunk
from evidence_repository.models.evidence import Span

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Service for generating and managing embeddings.

    Handles:
    - Text chunking
    - Embedding generation via OpenAI
    - Storage in pgvector
    - Linking embeddings to document versions and spans
    """

    def __init__(
        self,
        db: AsyncSession,
        embedding_client: OpenAIEmbeddingClient | None = None,
        chunker: TextChunker | None = None,
    ):
        """Initialize embedding service.

        Args:
            db: Database session.
            embedding_client: OpenAI client (created from settings if not provided).
            chunker: Text chunker (created from settings if not provided).
        """
        self.db = db

        settings = get_settings()

        self.embedding_client = embedding_client or OpenAIEmbeddingClient()
        self.chunker = chunker or TextChunker(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
        )

    async def embed_document_version(
        self,
        version: DocumentVersion,
        reprocess: bool = False,
    ) -> list[EmbeddingChunk]:
        """Generate embeddings for a document version.

        Chunks the extracted text and generates embeddings for each chunk.

        Args:
            version: Document version with extracted text.
            reprocess: If True, delete existing embeddings first.

        Returns:
            List of created EmbeddingChunk records.

        Raises:
            ValueError: If document has no extracted text.
        """
        if not version.extracted_text:
            raise ValueError(
                f"Document version {version.id} has no extracted text. "
                "Run extraction first."
            )

        # Delete existing embeddings if reprocessing
        if reprocess:
            await self.db.execute(
                delete(EmbeddingChunk).where(
                    EmbeddingChunk.document_version_id == version.id
                )
            )

        # Chunk the text
        chunks = self.chunker.chunk_text(
            text=version.extracted_text,
            metadata={
                "document_id": str(version.document_id),
                "version_id": str(version.id),
                "version_number": version.version_number,
            },
        )

        if not chunks:
            logger.warning(f"No chunks generated for version {version.id}")
            return []

        # Generate embeddings in batches
        batch_size = 100
        embedding_chunks: list[EmbeddingChunk] = []

        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]
            texts = [chunk.text for chunk in batch]

            # Get embeddings from OpenAI
            embeddings = await self.embedding_client.embed_texts(texts)

            # Create embedding chunk records
            for chunk, embedding in zip(batch, embeddings):
                embedding_chunk = EmbeddingChunk(
                    document_version_id=version.id,
                    chunk_index=chunk.index,
                    text=chunk.text,
                    embedding=embedding,
                    char_start=chunk.char_start,
                    char_end=chunk.char_end,
                    metadata_=chunk.metadata,
                )
                self.db.add(embedding_chunk)
                embedding_chunks.append(embedding_chunk)

        await self.db.flush()

        logger.info(
            f"Created {len(embedding_chunks)} embeddings for version {version.id}"
        )

        return embedding_chunks

    async def embed_span(self, span: Span) -> EmbeddingChunk:
        """Generate embedding for a specific span.

        Creates a single embedding chunk linked to the span.

        Args:
            span: Span with text content.

        Returns:
            Created EmbeddingChunk record.
        """
        embedding = await self.embedding_client.embed_text(span.text_content)

        embedding_chunk = EmbeddingChunk(
            document_version_id=span.document_version_id,
            span_id=span.id,
            chunk_index=0,
            text=span.text_content,
            embedding=embedding,
            metadata_={
                "span_id": str(span.id),
                "span_type": span.span_type.value,
            },
        )
        self.db.add(embedding_chunk)
        await self.db.flush()

        return embedding_chunk

    async def embed_text(self, text: str) -> list[float]:
        """Generate embedding for arbitrary text.

        Useful for search queries.

        Args:
            text: Text to embed.

        Returns:
            Embedding vector.
        """
        return await self.embedding_client.embed_text(text)

    async def delete_version_embeddings(self, version_id: uuid.UUID) -> int:
        """Delete all embeddings for a document version.

        Args:
            version_id: Document version ID.

        Returns:
            Number of embeddings deleted.
        """
        result = await self.db.execute(
            delete(EmbeddingChunk).where(
                EmbeddingChunk.document_version_id == version_id
            )
        )
        await self.db.flush()
        return result.rowcount  # type: ignore

    async def delete_span_embeddings(self, span_id: uuid.UUID) -> int:
        """Delete all embeddings for a span.

        Args:
            span_id: Span ID.

        Returns:
            Number of embeddings deleted.
        """
        result = await self.db.execute(
            delete(EmbeddingChunk).where(EmbeddingChunk.span_id == span_id)
        )
        await self.db.flush()
        return result.rowcount  # type: ignore
