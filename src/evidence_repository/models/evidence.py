"""Evidence models: Span, Claim, Metric, EvidencePack."""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from evidence_repository.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from evidence_repository.models.document import DocumentVersion
    from evidence_repository.models.embedding import EmbeddingChunk
    from evidence_repository.models.project import Project


class SpanType(str, enum.Enum):
    """Type of evidence span."""

    TEXT = "text"
    TABLE = "table"
    FIGURE = "figure"
    CITATION = "citation"
    HEADING = "heading"
    FOOTNOTE = "footnote"
    OTHER = "other"


class Span(Base, UUIDMixin):
    """Evidence span pointing to a specific location in a document version.

    Spans are stable references to document content with precise locators
    (page/bbox for PDFs, sheet/cell for spreadsheets, char offsets for text).
    """

    __tablename__ = "spans"

    # Link to specific document version (immutable reference)
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Hash for idempotency (computed from version_id + locators + text)
    # Used to prevent duplicate span creation
    span_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # Locator: JSON object describing exact position
    # PDF: {"type": "pdf", "page": 5, "bbox": {"x1": 100, "y1": 200, "x2": 500, "y2": 250}}
    # Spreadsheet: {"type": "spreadsheet", "sheet": "Summary", "cell_range": "A1:D10"}
    # Text: {"type": "text", "char_offset_start": 1000, "char_offset_end": 1500}
    start_locator: Mapped[dict] = mapped_column(JSON, nullable=False)
    end_locator: Mapped[dict | None] = mapped_column(JSON)

    # Extracted text content of the span
    text_content: Mapped[str] = mapped_column(Text, nullable=False)

    # Classification
    span_type: Mapped[SpanType] = mapped_column(
        Enum(SpanType, name="spantype", create_type=False, values_callable=lambda x: [e.value for e in x]),
        default=SpanType.TEXT,
        nullable=False,
    )

    # Metadata
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    document_version: Mapped["DocumentVersion"] = relationship(
        "DocumentVersion",
        back_populates="spans",
    )
    claims: Mapped[list["Claim"]] = relationship(
        "Claim",
        back_populates="span",
        cascade="all, delete-orphan",
    )
    metrics: Mapped[list["Metric"]] = relationship(
        "Metric",
        back_populates="span",
        cascade="all, delete-orphan",
    )
    embedding_chunks: Mapped[list["EmbeddingChunk"]] = relationship(
        "EmbeddingChunk",
        back_populates="span",
        cascade="all, delete-orphan",
    )
    evidence_pack_items: Mapped[list["EvidencePackItem"]] = relationship(
        "EvidencePackItem",
        back_populates="span",
        cascade="all, delete-orphan",
    )

    # Indexes and constraints
    __table_args__ = (
        Index("ix_spans_span_type", "span_type"),
        # Unique constraint for idempotency
        UniqueConstraint(
            "document_version_id",
            "span_hash",
            name="uq_spans_version_hash",
        ),
    )


class ClaimType(str, enum.Enum):
    """Type of compliance/legal claim."""

    SOC2 = "soc2"
    ISO27001 = "iso27001"
    GDPR = "gdpr"
    HIPAA = "hipaa"
    IP_OWNERSHIP = "ip_ownership"
    SECURITY_INCIDENT = "security_incident"
    COMPLIANCE = "compliance"
    CERTIFICATION = "certification"
    AUDIT = "audit"
    POLICY = "policy"
    OTHER = "other"


class Certainty(str, enum.Enum):
    """Certainty level of extracted information."""

    DEFINITE = "definite"  # Explicitly stated fact
    PROBABLE = "probable"  # Strongly implied
    POSSIBLE = "possible"  # Mentioned but uncertain
    SPECULATIVE = "speculative"  # Inferred, not stated


class Reliability(str, enum.Enum):
    """Reliability of the source."""

    VERIFIED = "verified"  # Audited/certified source
    OFFICIAL = "official"  # Official company document
    INTERNAL = "internal"  # Internal document, unverified
    THIRD_PARTY = "third_party"  # External source
    UNKNOWN = "unknown"


class Claim(Base, UUIDMixin):
    """Extracted claim citing an evidence span.

    Claims are assertions extracted from documents that reference
    specific spans as evidence. Used for compliance, certifications,
    and legal assertions.
    """

    __tablename__ = "claims"

    # Context: project this claim belongs to
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Evidence: span this claim cites
    span_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("spans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Claim content
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    claim_type: Mapped[ClaimType] = mapped_column(
        Enum(ClaimType),
        default=ClaimType.OTHER,
        nullable=False,
        index=True,
    )

    # Time scope (e.g., "Q4 2024", "FY2023", "as of 2024-01-15")
    time_scope: Mapped[str | None] = mapped_column(String(100))

    # Certainty: how certain is this claim?
    certainty: Mapped[Certainty] = mapped_column(
        Enum(Certainty),
        default=Certainty.PROBABLE,
        nullable=False,
    )

    # Reliability: how reliable is the source?
    reliability: Mapped[Reliability] = mapped_column(
        Enum(Reliability),
        default=Reliability.UNKNOWN,
        nullable=False,
    )

    # Extraction confidence (0.0 - 1.0): ML model confidence
    extraction_confidence: Mapped[float | None] = mapped_column(Float)

    # Legacy confidence field (deprecated, use extraction_confidence)
    confidence: Mapped[float | None] = mapped_column(Float)

    # Metadata
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="claims")
    span: Mapped["Span"] = relationship("Span", back_populates="claims")
    evidence_pack_items: Mapped[list["EvidencePackItem"]] = relationship(
        "EvidencePackItem",
        back_populates="claim",
    )


class MetricType(str, enum.Enum):
    """Type of financial/business metric."""

    ARR = "arr"  # Annual Recurring Revenue
    MRR = "mrr"  # Monthly Recurring Revenue
    REVENUE = "revenue"
    BURN = "burn"  # Burn rate
    RUNWAY = "runway"  # Cash runway
    CASH = "cash"  # Cash on hand
    HEADCOUNT = "headcount"
    CHURN = "churn"  # Customer churn rate
    NRR = "nrr"  # Net Revenue Retention
    GROSS_MARGIN = "gross_margin"
    CAC = "cac"  # Customer Acquisition Cost
    LTV = "ltv"  # Lifetime Value
    EBITDA = "ebitda"
    GROWTH_RATE = "growth_rate"
    OTHER = "other"


class Metric(Base, UUIDMixin):
    """Extracted metric citing an evidence span.

    Metrics are quantitative values extracted from documents that reference
    specific spans as evidence. Used for financial and business KPIs.
    """

    __tablename__ = "metrics"

    # Context: project this metric belongs to
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Evidence: span this metric cites
    span_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("spans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Metric content
    metric_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    metric_type: Mapped[MetricType] = mapped_column(
        Enum(MetricType),
        default=MetricType.OTHER,
        nullable=False,
        index=True,
    )
    metric_value: Mapped[str] = mapped_column(String(255), nullable=False)
    numeric_value: Mapped[float | None] = mapped_column(Float)  # Parsed numeric value
    unit: Mapped[str | None] = mapped_column(String(100))

    # Time scope (e.g., "Q4 2024", "FY2023", "as of 2024-01-15")
    time_scope: Mapped[str | None] = mapped_column(String(100))

    # Certainty: how certain is this metric?
    certainty: Mapped[Certainty] = mapped_column(
        Enum(Certainty),
        default=Certainty.PROBABLE,
        nullable=False,
    )

    # Reliability: how reliable is the source?
    reliability: Mapped[Reliability] = mapped_column(
        Enum(Reliability),
        default=Reliability.UNKNOWN,
        nullable=False,
    )

    # Extraction confidence (0.0 - 1.0): ML model confidence
    extraction_confidence: Mapped[float | None] = mapped_column(Float)

    # Metadata
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="metrics")
    span: Mapped["Span"] = relationship("Span", back_populates="metrics")
    evidence_pack_items: Mapped[list["EvidencePackItem"]] = relationship(
        "EvidencePackItem",
        back_populates="metric",
    )


class EvidencePack(Base, UUIDMixin, TimestampMixin):
    """Collection of evidence items for export/presentation.

    Evidence packs bundle spans, claims, and metrics for a specific purpose
    (e.g., a legal brief, a report section).
    """

    __tablename__ = "evidence_packs"

    # Context
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Pack details
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    # Creator
    created_by: Mapped[str | None] = mapped_column(String(255))

    # Metadata
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="evidence_packs")
    items: Mapped[list["EvidencePackItem"]] = relationship(
        "EvidencePackItem",
        back_populates="evidence_pack",
        cascade="all, delete-orphan",
        order_by="EvidencePackItem.order_index",
    )


class EvidencePackItem(Base, UUIDMixin):
    """Individual item in an evidence pack."""

    __tablename__ = "evidence_pack_items"

    # Parent pack
    evidence_pack_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evidence_packs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Evidence reference (at least span required)
    span_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("spans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Optional: specific claim or metric
    claim_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("claims.id", ondelete="SET NULL"),
    )
    metric_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("metrics.id", ondelete="SET NULL"),
    )

    # Ordering within pack
    order_index: Mapped[int] = mapped_column(default=0)

    # Additional notes
    notes: Mapped[str | None] = mapped_column(Text)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    evidence_pack: Mapped["EvidencePack"] = relationship(
        "EvidencePack",
        back_populates="items",
    )
    span: Mapped["Span"] = relationship("Span", back_populates="evidence_pack_items")
    claim: Mapped["Claim | None"] = relationship("Claim", back_populates="evidence_pack_items")
    metric: Mapped["Metric | None"] = relationship("Metric", back_populates="evidence_pack_items")
