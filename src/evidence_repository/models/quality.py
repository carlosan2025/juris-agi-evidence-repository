"""Quality models for extraction quality tracking: conflicts, open questions."""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from evidence_repository.models.base import Base, UUIDMixin

if TYPE_CHECKING:
    from evidence_repository.models.document import Document, DocumentVersion
    from evidence_repository.models.extraction_level import FactExtractionRun

# Import ProcessContext for use in column definitions
from evidence_repository.models.extraction_level import ProcessContext


# =============================================================================
# Enums for Quality
# =============================================================================


class ConflictSeverity(str, enum.Enum):
    """Severity of detected conflicts."""

    CRITICAL = "critical"  # Must be resolved before proceeding
    HIGH = "high"  # Significant discrepancy
    MEDIUM = "medium"  # Notable inconsistency
    LOW = "low"  # Minor discrepancy
    INFORMATIONAL = "informational"  # FYI, may not need resolution


class QuestionCategory(str, enum.Enum):
    """Category of open questions."""

    MISSING_DATA = "missing_data"  # Data not found in documents
    AMBIGUOUS = "ambiguous"  # Unclear or contradictory information
    VERIFICATION = "verification"  # Needs external verification
    CLARIFICATION = "clarification"  # Needs clarification from source
    METHODOLOGY = "methodology"  # Questions about calculation method
    TEMPORAL = "temporal"  # Time-related questions (outdated, etc.)


# =============================================================================
# QualityConflict Model
# =============================================================================


class QualityConflict(Base, UUIDMixin):
    """Detected conflict between extracted facts.

    Conflicts are identified when facts from the same or different
    documents contradict each other, requiring resolution.
    """

    __tablename__ = "quality_conflicts"

    # Document reference
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Extraction context (profile + process_context + level)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("extraction_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    process_context: Mapped[ProcessContext] = mapped_column(
        Enum(ProcessContext),
        default=ProcessContext.UNSPECIFIED,
        nullable=False,
        index=True,
        comment="Business process context",
    )
    level_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("extraction_levels.id", ondelete="CASCADE"),
        nullable=False,
    )
    extraction_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("extraction_runs_multilevel.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Conflict details
    topic: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Topic or subject of the conflict",
    )
    severity: Mapped[ConflictSeverity] = mapped_column(
        Enum(ConflictSeverity),
        default=ConflictSeverity.MEDIUM,
        nullable=False,
        index=True,
    )

    # Related facts (IDs of conflicting claims/metrics)
    claim_ids: Mapped[list | None] = mapped_column(
        JSONB,
        comment="List of conflicting claim IDs",
    )
    metric_ids: Mapped[list | None] = mapped_column(
        JSONB,
        comment="List of conflicting metric IDs",
    )

    # Explanation
    reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Explanation of why this is a conflict",
    )

    # Resolution (if resolved)
    resolution: Mapped[str | None] = mapped_column(
        Text,
        comment="How the conflict was resolved",
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[str | None] = mapped_column(String(255))

    # Additional metadata
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    document: Mapped["Document"] = relationship("Document")
    document_version: Mapped["DocumentVersion"] = relationship("DocumentVersion")
    extraction_run: Mapped["FactExtractionRun"] = relationship(
        "FactExtractionRun",
        back_populates="quality_conflicts",
    )

    __table_args__ = (
        Index(
            "ix_quality_conflicts_version_profile_context_level",
            "version_id",
            "profile_id",
            "process_context",
            "level_id",
        ),
        Index("ix_quality_conflicts_severity", "severity"),
    )


# =============================================================================
# QualityOpenQuestion Model
# =============================================================================


class QualityOpenQuestion(Base, UUIDMixin):
    """Open question identified during extraction.

    Questions are raised when information is missing, ambiguous,
    or requires external verification.
    """

    __tablename__ = "quality_open_questions"

    # Document reference
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Extraction context (profile + process_context + level)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("extraction_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    process_context: Mapped[ProcessContext] = mapped_column(
        Enum(ProcessContext),
        default=ProcessContext.UNSPECIFIED,
        nullable=False,
        index=True,
        comment="Business process context",
    )
    level_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("extraction_levels.id", ondelete="CASCADE"),
        nullable=False,
    )
    extraction_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("extraction_runs_multilevel.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Question details
    question: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="The open question",
    )
    category: Mapped[QuestionCategory] = mapped_column(
        Enum(QuestionCategory),
        default=QuestionCategory.MISSING_DATA,
        nullable=False,
        index=True,
    )

    # Context
    context: Mapped[str | None] = mapped_column(
        Text,
        comment="Additional context about why this question was raised",
    )

    # Related facts
    related_claim_ids: Mapped[list | None] = mapped_column(
        JSONB,
        comment="Related claim IDs",
    )
    related_metric_ids: Mapped[list | None] = mapped_column(
        JSONB,
        comment="Related metric IDs",
    )

    # Answer (if answered)
    answer: Mapped[str | None] = mapped_column(Text)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    answered_by: Mapped[str | None] = mapped_column(String(255))

    # Additional metadata
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    document: Mapped["Document"] = relationship("Document")
    document_version: Mapped["DocumentVersion"] = relationship("DocumentVersion")
    extraction_run: Mapped["FactExtractionRun"] = relationship(
        "FactExtractionRun",
        back_populates="quality_open_questions",
    )

    __table_args__ = (
        Index(
            "ix_quality_open_questions_version_profile_context_level",
            "version_id",
            "profile_id",
            "process_context",
            "level_id",
        ),
        Index("ix_quality_open_questions_category", "category"),
    )
