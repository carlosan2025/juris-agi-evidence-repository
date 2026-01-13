"""Analysis models: Conflict and OpenQuestion for evidence analysis."""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from evidence_repository.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from evidence_repository.models.evidence import Claim, Metric, Span
    from evidence_repository.models.project import Project


class ConflictType(str, enum.Enum):
    """Type of evidence conflict."""

    CONTRADICTION = "contradiction"  # Claims directly contradict each other
    INCONSISTENCY = "inconsistency"  # Data doesn't align but not direct contradiction
    METRIC_MISMATCH = "metric_mismatch"  # Same metric with different values
    TEMPORAL = "temporal"  # Timeline/date conflicts
    NUMERIC = "numeric"  # Numerical discrepancies
    FACTUAL = "factual"  # Factual claims that conflict
    OTHER = "other"


class ConflictStatus(str, enum.Enum):
    """Resolution status of a conflict."""

    OPEN = "open"
    UNDER_REVIEW = "under_review"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"  # Determined to be non-issue
    ESCALATED = "escalated"


class ConflictSeverity(str, enum.Enum):
    """Severity level of the conflict."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Conflict(Base, UUIDMixin, TimestampMixin):
    """Evidence conflict between claims, metrics, or spans.

    Tracks contradictions or inconsistencies found during evidence analysis.
    """

    __tablename__ = "conflicts"

    # Context
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Conflict classification
    conflict_type: Mapped[ConflictType] = mapped_column(
        Enum(ConflictType),
        default=ConflictType.OTHER,
        nullable=False,
        index=True,
    )
    severity: Mapped[ConflictSeverity] = mapped_column(
        Enum(ConflictSeverity),
        default=ConflictSeverity.MEDIUM,
        nullable=False,
        index=True,
    )
    status: Mapped[ConflictStatus] = mapped_column(
        Enum(ConflictStatus),
        default=ConflictStatus.OPEN,
        nullable=False,
        index=True,
    )

    # Conflict description
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    # Confidence that this is a real conflict (0.0 - 1.0)
    confidence: Mapped[float | None] = mapped_column(Float)

    # Primary evidence items in conflict
    # These can reference claims, metrics, or spans
    claim_a_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("claims.id", ondelete="SET NULL"),
        index=True,
    )
    claim_b_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("claims.id", ondelete="SET NULL"),
        index=True,
    )
    metric_a_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("metrics.id", ondelete="SET NULL"),
        index=True,
    )
    metric_b_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("metrics.id", ondelete="SET NULL"),
        index=True,
    )
    span_a_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("spans.id", ondelete="SET NULL"),
        index=True,
    )
    span_b_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("spans.id", ondelete="SET NULL"),
        index=True,
    )

    # Resolution
    resolution: Mapped[str | None] = mapped_column(Text)
    resolved_by: Mapped[str | None] = mapped_column(String(255))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Tracking
    detected_by: Mapped[str | None] = mapped_column(String(255))  # System, user, etc.
    assigned_to: Mapped[str | None] = mapped_column(String(255))

    # Additional metadata
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)

    # Relationships
    project: Mapped["Project"] = relationship("Project")
    claim_a: Mapped["Claim | None"] = relationship("Claim", foreign_keys=[claim_a_id])
    claim_b: Mapped["Claim | None"] = relationship("Claim", foreign_keys=[claim_b_id])
    metric_a: Mapped["Metric | None"] = relationship("Metric", foreign_keys=[metric_a_id])
    metric_b: Mapped["Metric | None"] = relationship("Metric", foreign_keys=[metric_b_id])
    span_a: Mapped["Span | None"] = relationship("Span", foreign_keys=[span_a_id])
    span_b: Mapped["Span | None"] = relationship("Span", foreign_keys=[span_b_id])

    # Indexes
    __table_args__ = (
        Index("ix_conflicts_project_status", "project_id", "status"),
        Index("ix_conflicts_severity_status", "severity", "status"),
        Index("ix_conflicts_type_status", "conflict_type", "status"),
    )


class QuestionPriority(str, enum.Enum):
    """Priority level for open questions."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class QuestionStatus(str, enum.Enum):
    """Status of an open question."""

    OPEN = "open"
    IN_PROGRESS = "in_progress"
    ANSWERED = "answered"
    DEFERRED = "deferred"
    CLOSED = "closed"


class QuestionCategory(str, enum.Enum):
    """Category of open question."""

    MISSING_EVIDENCE = "missing_evidence"
    CLARIFICATION = "clarification"
    VERIFICATION = "verification"
    AMBIGUITY = "ambiguity"
    FOLLOW_UP = "follow_up"
    METHODOLOGY = "methodology"
    OTHER = "other"


class OpenQuestion(Base, UUIDMixin, TimestampMixin):
    """Open question requiring investigation or clarification.

    Tracks unresolved questions that arise during evidence analysis.
    """

    __tablename__ = "open_questions"

    # Context
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Question content
    question: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[str | None] = mapped_column(Text)  # Background/context for the question

    # Classification
    category: Mapped[QuestionCategory] = mapped_column(
        Enum(QuestionCategory),
        default=QuestionCategory.OTHER,
        nullable=False,
        index=True,
    )
    priority: Mapped[QuestionPriority] = mapped_column(
        Enum(QuestionPriority),
        default=QuestionPriority.MEDIUM,
        nullable=False,
        index=True,
    )
    status: Mapped[QuestionStatus] = mapped_column(
        Enum(QuestionStatus),
        default=QuestionStatus.OPEN,
        nullable=False,
        index=True,
    )

    # Related evidence (what prompted this question)
    span_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("spans.id", ondelete="SET NULL"),
        index=True,
    )
    claim_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("claims.id", ondelete="SET NULL"),
        index=True,
    )
    conflict_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conflicts.id", ondelete="SET NULL"),
        index=True,
    )

    # Answer/resolution
    answer: Mapped[str | None] = mapped_column(Text)
    answer_source: Mapped[str | None] = mapped_column(Text)  # Where the answer came from

    # Tracking
    raised_by: Mapped[str | None] = mapped_column(String(255))
    assigned_to: Mapped[str | None] = mapped_column(String(255))
    answered_by: Mapped[str | None] = mapped_column(String(255))
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Due date (if applicable)
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Additional metadata
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)

    # Relationships
    project: Mapped["Project"] = relationship("Project")
    span: Mapped["Span | None"] = relationship("Span")
    claim: Mapped["Claim | None"] = relationship("Claim")
    conflict: Mapped["Conflict | None"] = relationship("Conflict")

    # Indexes
    __table_args__ = (
        Index("ix_open_questions_project_status", "project_id", "status"),
        Index("ix_open_questions_priority_status", "priority", "status"),
        Index("ix_open_questions_category", "category"),
        Index("ix_open_questions_due_date", "due_date"),
    )

    @property
    def is_overdue(self) -> bool:
        """Check if question is past due date."""
        if self.due_date and self.status == QuestionStatus.OPEN:
            return datetime.now(self.due_date.tzinfo) > self.due_date
        return False
