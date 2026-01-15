"""Extraction level and profile models for multi-level fact extraction."""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Boolean,
    func,
    CheckConstraint,
)
from sqlalchemy.dialects.postgresql import JSON, UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from evidence_repository.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from evidence_repository.models.document import Document, DocumentVersion
    from evidence_repository.models.project import Project


# =============================================================================
# Enums
# =============================================================================


class ExtractionLevelCode(str, enum.Enum):
    """Extraction level of detail codes."""

    L1_BASIC = "L1_BASIC"  # Minimal key metrics + few claims
    L2_STANDARD = "L2_STANDARD"  # Expanded metrics + compliance claims + constraints
    L3_DEEP = "L3_DEEP"  # Entity resolution, time-series, table-aware, risks
    L4_FORENSIC = "L4_FORENSIC"  # Maximum extraction, cross-doc reconciliation


class ExtractionProfileCode(str, enum.Enum):
    """Extraction profile codes for domain-specific extraction."""

    GENERAL = "general"
    VC = "vc"  # Venture Capital / Startup due diligence
    PHARMA = "pharma"  # Pharmaceutical / Life Sciences
    INSURANCE = "insurance"  # Insurance underwriting


class ComputeMode(str, enum.Enum):
    """How to compute missing extraction levels."""

    EXACT_ONLY = "exact_only"  # Compute only the requested level
    ALL_UP_TO = "all_up_to"  # Compute all levels up to requested


class ExtractionRunStatus(str, enum.Enum):
    """Status of an extraction run."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ScopeType(str, enum.Enum):
    """Scope type for extraction settings."""

    PROJECT = "project"
    DOCUMENT_VERSION = "document_version"


class ProcessContext(str, enum.Enum):
    """Process context for extraction runs.

    Defines the business process context that determines what
    facts are relevant and how they should be extracted.
    """

    # Unspecified (backward compatibility)
    UNSPECIFIED = "unspecified"

    # Venture Capital contexts
    VC_IC_DECISION = "vc.ic_decision"  # Investment committee decision
    VC_DUE_DILIGENCE = "vc.due_diligence"  # Due diligence process
    VC_PORTFOLIO_REVIEW = "vc.portfolio_review"  # Portfolio company review
    VC_MARKET_ANALYSIS = "vc.market_analysis"  # Market/competitive analysis

    # Pharmaceutical contexts
    PHARMA_CLINICAL_TRIAL = "pharma.clinical_trial"  # Clinical trial analysis
    PHARMA_REGULATORY = "pharma.regulatory"  # Regulatory submission
    PHARMA_SAFETY = "pharma.safety"  # Safety/adverse event analysis
    PHARMA_MARKET_ACCESS = "pharma.market_access"  # Market access/pricing

    # Insurance contexts
    INSURANCE_UNDERWRITING = "insurance.underwriting"  # Risk underwriting
    INSURANCE_CLAIMS = "insurance.claims"  # Claims processing
    INSURANCE_COMPLIANCE = "insurance.compliance"  # Regulatory compliance

    # General contexts
    GENERAL_RESEARCH = "general.research"  # General research
    GENERAL_COMPLIANCE = "general.compliance"  # Compliance review
    GENERAL_AUDIT = "general.audit"  # Audit support


# =============================================================================
# Extraction Profile Model
# =============================================================================


class ExtractionProfile(Base, UUIDMixin):
    """Extraction profile defining domain-specific extraction templates.

    Profiles determine what types of facts to extract and how to interpret
    domain-specific terminology.
    """

    __tablename__ = "extraction_profiles"

    name: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
    )
    code: Mapped[ExtractionProfileCode] = mapped_column(
        Enum(ExtractionProfileCode),
        unique=True,
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Profile-specific configuration
    config: Mapped[dict] = mapped_column(JSONB, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    extraction_settings: Mapped[list["ExtractionSetting"]] = relationship(
        "ExtractionSetting",
        back_populates="profile",
    )
    extraction_runs: Mapped[list["FactExtractionRun"]] = relationship(
        "FactExtractionRun",
        back_populates="profile",
    )


# =============================================================================
# Extraction Level Model
# =============================================================================


class ExtractionLevel(Base, UUIDMixin):
    """Extraction level defining depth of extraction.

    Higher levels include more comprehensive extraction with increasing
    detail and computational cost.
    """

    __tablename__ = "extraction_levels"

    code: Mapped[ExtractionLevelCode] = mapped_column(
        Enum(ExtractionLevelCode),
        unique=True,
        nullable=False,
    )
    rank: Mapped[int] = mapped_column(
        Integer,
        unique=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Level-specific configuration (e.g., extraction parameters)
    config: Mapped[dict] = mapped_column(JSONB, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    extraction_settings: Mapped[list["ExtractionSetting"]] = relationship(
        "ExtractionSetting",
        back_populates="level",
    )
    extraction_runs: Mapped[list["FactExtractionRun"]] = relationship(
        "FactExtractionRun",
        back_populates="level",
    )

    __table_args__ = (
        CheckConstraint("rank >= 1 AND rank <= 10", name="ck_extraction_levels_rank"),
    )


# =============================================================================
# Extraction Setting Model
# =============================================================================


class ExtractionSetting(Base, UUIDMixin, TimestampMixin):
    """Extraction settings for a project or document version.

    Defines the default extraction profile and level for a scope,
    with options for auto-triggering extraction jobs.
    """

    __tablename__ = "extraction_settings"

    # Scope: either project or document_version
    scope_type: Mapped[ScopeType] = mapped_column(
        Enum(ScopeType),
        nullable=False,
        index=True,
    )
    scope_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    # Extraction configuration
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("extraction_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    level_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("extraction_levels.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Compute mode: exact_only or all_up_to
    compute_mode: Mapped[ComputeMode] = mapped_column(
        Enum(ComputeMode),
        default=ComputeMode.EXACT_ONLY,
        nullable=False,
    )

    # Whether auto-extraction is enabled
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Who last updated
    updated_by: Mapped[str | None] = mapped_column(String(255))

    # Relationships
    profile: Mapped["ExtractionProfile"] = relationship(
        "ExtractionProfile",
        back_populates="extraction_settings",
    )
    level: Mapped["ExtractionLevel"] = relationship(
        "ExtractionLevel",
        back_populates="extraction_settings",
    )

    __table_args__ = (
        # Unique setting per scope
        UniqueConstraint(
            "scope_type",
            "scope_id",
            name="uq_extraction_settings_scope",
        ),
        Index("ix_extraction_settings_scope", "scope_type", "scope_id"),
    )


# =============================================================================
# Extraction Run Model
# =============================================================================


class FactExtractionRun(Base, UUIDMixin):
    """Record of a fact extraction run for a specific (version, profile, process_context, level).

    Tracks the status and results of fact extraction jobs, ensuring
    idempotency and preventing duplicate extractions. This is separate from
    the document text extraction runs (extraction.py) which extract text
    from documents.
    """

    __tablename__ = "extraction_runs_multilevel"

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

    # Extraction configuration
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("extraction_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    level_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("extraction_levels.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Process context (business process that triggered extraction)
    process_context: Mapped[ProcessContext] = mapped_column(
        Enum(ProcessContext),
        default=ProcessContext.UNSPECIFIED,
        nullable=False,
        index=True,
        comment="Business process context for this extraction",
    )

    # Schema and vocabulary versioning for reproducibility
    schema_version: Mapped[str] = mapped_column(
        String(50),
        default="1.0",
        nullable=False,
        comment="Schema version used for this extraction",
    )
    vocab_version: Mapped[str] = mapped_column(
        String(50),
        default="1.0",
        nullable=False,
        comment="Vocabulary version used for this extraction",
    )

    # Status
    status: Mapped[ExtractionRunStatus] = mapped_column(
        Enum(ExtractionRunStatus),
        default=ExtractionRunStatus.QUEUED,
        nullable=False,
        index=True,
    )

    # Timestamps
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Error tracking
    error: Mapped[str | None] = mapped_column(Text)

    # Metadata (e.g., statistics, configuration used)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)

    # Parent run (for triggered extractions)
    parent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("extraction_runs_multilevel.id", ondelete="SET NULL"),
    )

    # Job reference (RQ job ID)
    job_id: Mapped[str | None] = mapped_column(String(255))

    # Triggered by user
    triggered_by: Mapped[str | None] = mapped_column(String(255))

    # Relationships
    document: Mapped["Document"] = relationship("Document")
    document_version: Mapped["DocumentVersion"] = relationship("DocumentVersion")
    profile: Mapped["ExtractionProfile"] = relationship(
        "ExtractionProfile",
        back_populates="extraction_runs",
    )
    level: Mapped["ExtractionLevel"] = relationship(
        "ExtractionLevel",
        back_populates="extraction_runs",
    )
    parent_run: Mapped["FactExtractionRun | None"] = relationship(
        "FactExtractionRun",
        remote_side="FactExtractionRun.id",
    )

    # Facts relationships
    facts_claims: Mapped[list["FactClaim"]] = relationship(
        "FactClaim",
        back_populates="extraction_run",
        cascade="all, delete-orphan",
    )
    facts_metrics: Mapped[list["FactMetric"]] = relationship(
        "FactMetric",
        back_populates="extraction_run",
        cascade="all, delete-orphan",
    )
    facts_constraints: Mapped[list["FactConstraint"]] = relationship(
        "FactConstraint",
        back_populates="extraction_run",
        cascade="all, delete-orphan",
    )
    facts_risks: Mapped[list["FactRisk"]] = relationship(
        "FactRisk",
        back_populates="extraction_run",
        cascade="all, delete-orphan",
    )
    quality_conflicts: Mapped[list["QualityConflict"]] = relationship(
        "QualityConflict",
        back_populates="extraction_run",
        cascade="all, delete-orphan",
    )
    quality_open_questions: Mapped[list["QualityOpenQuestion"]] = relationship(
        "QualityOpenQuestion",
        back_populates="extraction_run",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        # Prevent duplicate active runs for same (version, profile, process_context, level)
        Index(
            "ix_extraction_runs_multilevel_active",
            "version_id",
            "profile_id",
            "process_context",
            "level_id",
            unique=True,
            postgresql_where=(status.in_([ExtractionRunStatus.QUEUED, ExtractionRunStatus.RUNNING])),
        ),
        Index(
            "ix_extraction_runs_multilevel_version_profile_context_level",
            "version_id",
            "profile_id",
            "process_context",
            "level_id",
        ),
        Index("ix_extraction_runs_multilevel_status_new", "status"),
        Index("ix_extraction_runs_multilevel_process_context", "process_context"),
    )


# =============================================================================
# Forward References for Type Checking
# =============================================================================

if TYPE_CHECKING:
    from evidence_repository.models.facts import (
        FactClaim,
        FactMetric,
        FactConstraint,
        FactRisk,
    )
    from evidence_repository.models.quality import (
        QualityConflict,
        QualityOpenQuestion,
    )
