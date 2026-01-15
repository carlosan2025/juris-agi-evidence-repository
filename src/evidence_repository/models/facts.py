"""Fact models for multi-level extraction: claims, metrics, constraints, risks.

All facts are partitioned by (document_id, version_id, profile_id, level_id)
and reference source spans for traceability.
"""

import enum
import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    Date,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from evidence_repository.models.base import Base, UUIDMixin

if TYPE_CHECKING:
    from evidence_repository.models.extraction_level import FactExtractionRun
    from evidence_repository.models.document import Document, DocumentVersion

# Import ProcessContext for use in column definitions (import at runtime, not just type checking)
from evidence_repository.models.extraction_level import ProcessContext


# =============================================================================
# Enums for Facts
# =============================================================================


class FactCertainty(str, enum.Enum):
    """Certainty level of extracted facts."""

    DEFINITE = "definite"  # Explicitly stated
    PROBABLE = "probable"  # Strongly implied
    POSSIBLE = "possible"  # Mentioned but uncertain
    SPECULATIVE = "speculative"  # Inferred


class SourceReliability(str, enum.Enum):
    """Reliability of the source document."""

    AUDITED = "audited"  # Independently audited
    OFFICIAL = "official"  # Official company document
    INTERNAL = "internal"  # Internal document, unverified
    THIRD_PARTY = "third_party"  # External source
    UNKNOWN = "unknown"


class ConstraintType(str, enum.Enum):
    """Types of constraints/definitions."""

    DEFINITION = "definition"  # Defines a term or metric
    DEPENDENCY = "dependency"  # X depends on Y
    EXCLUSION = "exclusion"  # X excludes Y
    ELIGIBILITY = "eligibility"  # Eligibility criteria
    COVENANT = "covenant"  # Financial covenant
    ASSUMPTION = "assumption"  # Underlying assumption


class RiskSeverity(str, enum.Enum):
    """Severity levels for identified risks."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFORMATIONAL = "informational"


# =============================================================================
# FactClaim Model
# =============================================================================


class FactClaim(Base, UUIDMixin):
    """Extracted claim/assertion from a document.

    Claims represent boolean or categorical assertions extracted from
    documents, with full provenance tracking.
    """

    __tablename__ = "facts_claims"

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

    # Claim structure (subject-predicate-object)
    subject: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="Subject of the claim (e.g., {'type': 'company', 'name': 'Acme'})",
    )
    predicate: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="Predicate/assertion type from controlled vocabulary",
    )
    object: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="Object/value of the claim",
    )

    # Claim classification
    claim_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="High-level claim category (compliance, security, financial, etc.)",
    )

    # Time scope
    time_scope: Mapped[dict | None] = mapped_column(
        JSONB,
        comment="Time period/scope (e.g., {'period': 'Q4 2024', 'as_of': '2024-12-31'})",
    )

    # Quality indicators
    certainty: Mapped[FactCertainty] = mapped_column(
        Enum(FactCertainty),
        default=FactCertainty.PROBABLE,
        nullable=False,
    )
    source_reliability: Mapped[SourceReliability] = mapped_column(
        Enum(SourceReliability),
        default=SourceReliability.UNKNOWN,
        nullable=False,
    )
    extraction_confidence: Mapped[float | None] = mapped_column(
        Float,
        comment="ML model confidence score (0.0-1.0)",
    )

    # Provenance: span references
    span_refs: Mapped[list] = mapped_column(
        JSONB,
        default=list,
        nullable=False,
        comment="List of span IDs supporting this claim",
    )

    # Raw evidence quote
    evidence_quote: Mapped[str | None] = mapped_column(Text)

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
        back_populates="facts_claims",
    )

    __table_args__ = (
        Index(
            "ix_facts_claims_version_profile_context_level",
            "version_id",
            "profile_id",
            "process_context",
            "level_id",
        ),
        Index("ix_facts_claims_predicate", "predicate"),
        Index("ix_facts_claims_claim_type", "claim_type"),
    )


# =============================================================================
# FactMetric Model
# =============================================================================


class FactMetric(Base, UUIDMixin):
    """Extracted metric/numeric value from a document.

    Metrics represent quantitative values with units, time periods,
    and full provenance tracking.
    """

    __tablename__ = "facts_metrics"

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

    # Entity reference (what this metric is about)
    entity_id: Mapped[str | None] = mapped_column(
        String(255),
        index=True,
        comment="Entity identifier (e.g., company ID, product ID)",
    )
    entity_type: Mapped[str | None] = mapped_column(
        String(100),
        comment="Type of entity (company, product, segment)",
    )

    # Metric identification
    metric_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="Metric name from controlled vocabulary",
    )
    metric_category: Mapped[str | None] = mapped_column(
        String(100),
        index=True,
        comment="Category (revenue, profitability, efficiency, etc.)",
    )

    # Value
    value_numeric: Mapped[float | None] = mapped_column(
        Float,
        comment="Numeric value (parsed)",
    )
    value_raw: Mapped[str | None] = mapped_column(
        String(255),
        comment="Raw value as stated in document",
    )
    unit: Mapped[str | None] = mapped_column(
        String(50),
        comment="Unit of measurement",
    )
    currency: Mapped[str | None] = mapped_column(
        String(10),
        comment="Currency code (USD, EUR, etc.)",
    )

    # Time scope
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    as_of: Mapped[date | None] = mapped_column(
        Date,
        comment="Point-in-time value date",
    )
    period_type: Mapped[str | None] = mapped_column(
        String(50),
        comment="Period type (monthly, quarterly, annual, ytd, ltm)",
    )

    # Calculation method
    method: Mapped[str | None] = mapped_column(
        String(100),
        comment="Calculation method or basis (GAAP, non-GAAP, etc.)",
    )

    # Quality indicators
    certainty: Mapped[FactCertainty] = mapped_column(
        Enum(FactCertainty),
        default=FactCertainty.PROBABLE,
        nullable=False,
    )
    source_reliability: Mapped[SourceReliability] = mapped_column(
        Enum(SourceReliability),
        default=SourceReliability.UNKNOWN,
        nullable=False,
    )
    extraction_confidence: Mapped[float | None] = mapped_column(Float)

    # Quality flags (e.g., estimated, restated, pro_forma)
    quality_flags: Mapped[list | None] = mapped_column(
        JSONB,
        comment="Quality flags (estimated, restated, pro_forma, etc.)",
    )

    # Provenance
    span_refs: Mapped[list] = mapped_column(
        JSONB,
        default=list,
        nullable=False,
    )
    evidence_quote: Mapped[str | None] = mapped_column(Text)

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
        back_populates="facts_metrics",
    )

    __table_args__ = (
        Index(
            "ix_facts_metrics_version_profile_context_level",
            "version_id",
            "profile_id",
            "process_context",
            "level_id",
        ),
        Index("ix_facts_metrics_metric_name", "metric_name"),
        Index("ix_facts_metrics_entity", "entity_id", "metric_name"),
    )


# =============================================================================
# FactConstraint Model
# =============================================================================


class FactConstraint(Base, UUIDMixin):
    """Extracted constraint, definition, or dependency.

    Constraints capture definitions, dependencies, exclusions, and
    other structural relationships between facts.
    """

    __tablename__ = "facts_constraints"

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

    # Constraint type
    constraint_type: Mapped[ConstraintType] = mapped_column(
        Enum(ConstraintType),
        nullable=False,
        index=True,
    )

    # What this constraint applies to (references to claims/metrics)
    applies_to: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="References to claim_ids/metric_ids this constraint applies to",
    )

    # Statement
    statement: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="The constraint statement/definition",
    )

    # Quality indicators
    certainty: Mapped[FactCertainty] = mapped_column(
        Enum(FactCertainty),
        default=FactCertainty.PROBABLE,
        nullable=False,
    )
    extraction_confidence: Mapped[float | None] = mapped_column(Float)

    # Provenance
    span_refs: Mapped[list] = mapped_column(
        JSONB,
        default=list,
        nullable=False,
    )

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
        back_populates="facts_constraints",
    )

    __table_args__ = (
        Index(
            "ix_facts_constraints_version_profile_context_level",
            "version_id",
            "profile_id",
            "process_context",
            "level_id",
        ),
        Index("ix_facts_constraints_type", "constraint_type"),
    )


# =============================================================================
# FactRisk Model
# =============================================================================


class FactRisk(Base, UUIDMixin):
    """Extracted risk identification.

    Risks capture potential issues, concerns, or areas of uncertainty
    identified during extraction.
    """

    __tablename__ = "facts_risks"

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

    # Risk classification
    risk_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="Risk type from controlled vocabulary",
    )
    risk_category: Mapped[str | None] = mapped_column(
        String(100),
        comment="Risk category (financial, operational, legal, etc.)",
    )
    severity: Mapped[RiskSeverity] = mapped_column(
        Enum(RiskSeverity),
        default=RiskSeverity.MEDIUM,
        nullable=False,
        index=True,
    )

    # Risk statement
    statement: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Risk description",
    )
    rationale: Mapped[str | None] = mapped_column(
        Text,
        comment="Why this was identified as a risk",
    )

    # Related facts
    related_claims: Mapped[list | None] = mapped_column(
        JSONB,
        comment="Related claim IDs",
    )
    related_metrics: Mapped[list | None] = mapped_column(
        JSONB,
        comment="Related metric IDs",
    )

    # Quality indicators
    extraction_confidence: Mapped[float | None] = mapped_column(Float)

    # Provenance
    span_refs: Mapped[list] = mapped_column(
        JSONB,
        default=list,
        nullable=False,
    )

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
        back_populates="facts_risks",
    )

    __table_args__ = (
        Index(
            "ix_facts_risks_version_profile_context_level",
            "version_id",
            "profile_id",
            "process_context",
            "level_id",
        ),
        Index("ix_facts_risks_type_severity", "risk_type", "severity"),
    )
