"""Embedding chunk model for vector search."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from evidence_repository.models.base import Base, UUIDMixin

if TYPE_CHECKING:
    from evidence_repository.models.document import DocumentVersion
    from evidence_repository.models.evidence import Span


class EmbeddingChunk(Base, UUIDMixin):
    """Embedding chunk for vector similarity search.

    Chunks are derived from document text and store embeddings for semantic search.
    Each chunk can optionally be linked to a span for precise citation.
    """

    __tablename__ = "embedding_chunks"

    # Link to document version
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Optional link to span (for chunks that correspond to specific spans)
    span_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("spans.id", ondelete="SET NULL"),
        index=True,
    )

    # Chunk position within document
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)

    # Text content
    text: Mapped[str] = mapped_column(Text, nullable=False)

    # Vector embedding (1536 dimensions for OpenAI text-embedding-3-small)
    # Can be adjusted via config
    embedding: Mapped[list[float]] = mapped_column(Vector(1536), nullable=False)

    # Metadata (e.g., page number, section)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)

    # Character offsets in original text
    char_start: Mapped[int | None] = mapped_column(Integer)
    char_end: Mapped[int | None] = mapped_column(Integer)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    document_version: Mapped["DocumentVersion"] = relationship(
        "DocumentVersion",
        back_populates="embedding_chunks",
    )
    span: Mapped["Span | None"] = relationship("Span", back_populates="embedding_chunks")

    # Indexes for vector search
    __table_args__ = (
        Index("ix_embedding_chunks_document_version", "document_version_id"),
        Index("ix_embedding_chunks_chunk_index", "document_version_id", "chunk_index"),
        # Vector index will be created via migration with proper operator class
    )
