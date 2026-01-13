"""Document and DocumentVersion models."""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from evidence_repository.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from evidence_repository.models.embedding import EmbeddingChunk
    from evidence_repository.models.evidence import Span
    from evidence_repository.models.extraction import ExtractionRun
    from evidence_repository.models.project import ProjectDocument


class ExtractionStatus(str, enum.Enum):
    """Status of text extraction for a document version."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Document(Base, UUIDMixin, TimestampMixin):
    """Global document asset.

    Documents are standalone entities that can be attached to multiple projects.
    Each document can have multiple versions.
    """

    __tablename__ = "documents"

    # Core fields
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)

    # Content hash for deduplication (SHA-256 of original file)
    file_hash: Mapped[str | None] = mapped_column(String(64), index=True)

    # Flexible metadata storage
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)

    # Soft delete support
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    versions: Mapped[list["DocumentVersion"]] = relationship(
        "DocumentVersion",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentVersion.version_number.desc()",
    )
    project_documents: Mapped[list["ProjectDocument"]] = relationship(
        "ProjectDocument",
        back_populates="document",
        cascade="all, delete-orphan",
    )

    # Indexes
    __table_args__ = (
        Index("ix_documents_filename", "filename"),
        Index("ix_documents_content_type", "content_type"),
        Index("ix_documents_deleted_at", "deleted_at"),
    )

    @property
    def latest_version(self) -> "DocumentVersion | None":
        """Get the latest version of this document."""
        return self.versions[0] if self.versions else None

    @property
    def is_deleted(self) -> bool:
        """Check if document is soft-deleted."""
        return self.deleted_at is not None


class DocumentVersion(Base, UUIDMixin):
    """Immutable version of a document.

    Each version represents a specific state of the document file.
    Versions are immutable once created - edits create new versions.
    """

    __tablename__ = "document_versions"

    # Foreign key to parent document
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Version tracking
    version_number: Mapped[int] = mapped_column(nullable=False, default=1)

    # Storage location (relative path in storage backend)
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)

    # File metadata
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    # Extracted text content
    extracted_text: Mapped[str | None] = mapped_column(Text)
    extraction_status: Mapped[ExtractionStatus] = mapped_column(
        Enum(ExtractionStatus),
        default=ExtractionStatus.PENDING,
        nullable=False,
    )
    extraction_error: Mapped[str | None] = mapped_column(Text)
    extracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Page/sheet count (for PDFs, spreadsheets)
    page_count: Mapped[int | None] = mapped_column()

    # Version metadata
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    document: Mapped["Document"] = relationship("Document", back_populates="versions")
    spans: Mapped[list["Span"]] = relationship(
        "Span",
        back_populates="document_version",
        cascade="all, delete-orphan",
    )
    embedding_chunks: Mapped[list["EmbeddingChunk"]] = relationship(
        "EmbeddingChunk",
        back_populates="document_version",
        cascade="all, delete-orphan",
    )
    extraction_runs: Mapped[list["ExtractionRun"]] = relationship(
        "ExtractionRun",
        back_populates="document_version",
        cascade="all, delete-orphan",
        order_by="ExtractionRun.created_at.desc()",
    )

    # Indexes
    __table_args__ = (
        Index("ix_document_versions_document_version", "document_id", "version_number"),
        Index("ix_document_versions_extraction_status", "extraction_status"),
    )
