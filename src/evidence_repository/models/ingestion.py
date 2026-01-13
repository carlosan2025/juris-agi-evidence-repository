"""Ingestion models for batch document processing."""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from evidence_repository.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from evidence_repository.models.document import Document, DocumentVersion
    from evidence_repository.models.job import Job


class IngestionBatchStatus(str, enum.Enum):
    """Status of an ingestion batch."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    PARTIAL = "partial"  # Some items failed
    FAILED = "failed"
    CANCELED = "canceled"


class IngestionItemStatus(str, enum.Enum):
    """Status of an individual ingestion item."""

    PENDING = "pending"
    DOWNLOADING = "downloading"
    PROCESSING = "processing"
    EXTRACTING = "extracting"
    EMBEDDING = "embedding"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"  # e.g., duplicate file


class IngestionSource(str, enum.Enum):
    """Source type for ingestion."""

    FILE_UPLOAD = "file_upload"
    LOCAL_FOLDER = "local_folder"
    URL = "url"
    S3_BUCKET = "s3_bucket"
    API_IMPORT = "api_import"


class IngestionBatch(Base, UUIDMixin, TimestampMixin):
    """Batch of documents being ingested together.

    Tracks the overall progress of a bulk ingestion operation,
    whether from a folder, URL list, or other source.
    """

    __tablename__ = "ingestion_batches"

    # Batch metadata
    name: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)

    # Source information
    source_type: Mapped[IngestionSource] = mapped_column(
        Enum(IngestionSource),
        nullable=False,
    )
    source_path: Mapped[str | None] = mapped_column(Text)  # Folder path, base URL, etc.

    # Status tracking
    status: Mapped[IngestionBatchStatus] = mapped_column(
        Enum(IngestionBatchStatus),
        default=IngestionBatchStatus.PENDING,
        nullable=False,
        index=True,
    )

    # Progress counters
    total_items: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    processed_items: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    successful_items: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_items: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    skipped_items: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Link to processing job (optional)
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="SET NULL"),
        index=True,
    )

    # Creator tracking
    created_by: Mapped[str | None] = mapped_column(String(255))

    # Additional metadata
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)

    # Timestamps for batch lifecycle
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    items: Mapped[list["IngestionItem"]] = relationship(
        "IngestionItem",
        back_populates="batch",
        cascade="all, delete-orphan",
        order_by="IngestionItem.created_at",
    )
    job: Mapped["Job | None"] = relationship("Job")

    # Indexes
    __table_args__ = (
        Index("ix_ingestion_batches_status_created_at", "status", "created_at"),
        Index("ix_ingestion_batches_source_type", "source_type"),
    )

    @property
    def progress_percent(self) -> float:
        """Calculate progress percentage."""
        if self.total_items == 0:
            return 0.0
        return (self.processed_items / self.total_items) * 100


class IngestionItem(Base, UUIDMixin):
    """Individual item within an ingestion batch.

    Tracks the processing of each file/URL in a batch operation.
    """

    __tablename__ = "ingestion_items"

    # Parent batch
    batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ingestion_batches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Source information
    source_path: Mapped[str] = mapped_column(Text, nullable=False)  # File path or URL
    source_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    source_size: Mapped[int | None] = mapped_column(Integer)  # Bytes

    # Processing status
    status: Mapped[IngestionItemStatus] = mapped_column(
        Enum(IngestionItemStatus),
        default=IngestionItemStatus.PENDING,
        nullable=False,
        index=True,
    )

    # Result tracking
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        index=True,
    )
    document_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_versions.id", ondelete="SET NULL"),
    )

    # Error tracking
    error_message: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(String(100))

    # Processing metadata
    content_type: Mapped[str | None] = mapped_column(String(255))
    file_hash: Mapped[str | None] = mapped_column(String(64))  # SHA-256

    # Retry tracking
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Additional metadata
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)

    # Relationships
    batch: Mapped["IngestionBatch"] = relationship(
        "IngestionBatch",
        back_populates="items",
    )
    document: Mapped["Document | None"] = relationship("Document")
    document_version: Mapped["DocumentVersion | None"] = relationship("DocumentVersion")

    # Indexes
    __table_args__ = (
        Index("ix_ingestion_items_batch_status", "batch_id", "status"),
        Index("ix_ingestion_items_file_hash", "file_hash"),
    )

    @property
    def is_terminal(self) -> bool:
        """Check if item is in a terminal state."""
        return self.status in (
            IngestionItemStatus.COMPLETED,
            IngestionItemStatus.FAILED,
            IngestionItemStatus.SKIPPED,
        )
