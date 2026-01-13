"""Extraction run models for tracking document extraction."""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from evidence_repository.models.base import Base, UUIDMixin

if TYPE_CHECKING:
    from evidence_repository.models.document import DocumentVersion


class ExtractionRunStatus(str, enum.Enum):
    """Status of an extraction run."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ExtractionRun(Base, UUIDMixin):
    """Record of an extraction run for a document version.

    Tracks the extraction process including timing, artifacts produced,
    and any errors encountered. Artifacts are stored under:
    /data/extracted/{document_id}/{version_id}/
    """

    __tablename__ = "extraction_runs"

    # Foreign key to document version
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Status tracking
    status: Mapped[ExtractionRunStatus] = mapped_column(
        Enum(ExtractionRunStatus),
        default=ExtractionRunStatus.PENDING,
        nullable=False,
        index=True,
    )

    # Extractor information
    extractor_name: Mapped[str] = mapped_column(String(100), nullable=False)
    extractor_version: Mapped[str] = mapped_column(String(50), default="1.0.0")

    # Artifact storage
    artifact_path: Mapped[str | None] = mapped_column(
        Text,
        comment="Path to extraction artifacts directory",
    )

    # Extracted content summary
    has_text: Mapped[bool] = mapped_column(default=False)
    has_tables: Mapped[bool] = mapped_column(default=False)
    has_images: Mapped[bool] = mapped_column(default=False)

    # Content metrics
    char_count: Mapped[int | None] = mapped_column(Integer)
    word_count: Mapped[int | None] = mapped_column(Integer)
    page_count: Mapped[int | None] = mapped_column(Integer)
    table_count: Mapped[int | None] = mapped_column(Integer)
    image_count: Mapped[int | None] = mapped_column(Integer)

    # Timing
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processing_time_ms: Mapped[int | None] = mapped_column(Integer)

    # Error tracking
    error_message: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(String(100))
    warnings: Mapped[list] = mapped_column(JSON, default=list)

    # Additional metadata (extractor-specific details)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    document_version: Mapped["DocumentVersion"] = relationship(
        "DocumentVersion",
        back_populates="extraction_runs",
    )

    # Indexes
    __table_args__ = (
        Index("ix_extraction_runs_version_status", "document_version_id", "status"),
        Index("ix_extraction_runs_extractor", "extractor_name"),
        Index("ix_extraction_runs_created_at", "created_at"),
    )

    @property
    def is_terminal(self) -> bool:
        """Check if run is in a terminal state."""
        return self.status in (
            ExtractionRunStatus.COMPLETED,
            ExtractionRunStatus.FAILED,
            ExtractionRunStatus.SKIPPED,
        )

    @property
    def duration_seconds(self) -> float | None:
        """Calculate run duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None
