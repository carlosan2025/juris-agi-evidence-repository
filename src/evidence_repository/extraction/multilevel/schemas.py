"""Pydantic schemas for multi-level extraction results."""

from datetime import date
from pydantic import BaseModel, Field


class ExtractedFact(BaseModel):
    """Base class for extracted facts."""

    span_refs: list[str] = Field(default_factory=list, description="List of span IDs")
    evidence_quote: str | None = Field(None, description="Direct quote from document")
    certainty: str = Field("probable", description="definite, probable, possible, speculative")
    extraction_confidence: float | None = Field(None, ge=0.0, le=1.0)


class ExtractedFactClaim(ExtractedFact):
    """Extracted claim (subject-predicate-object assertion)."""

    subject: dict = Field(..., description="Subject of claim, e.g., {'type': 'company', 'name': 'Acme'}")
    predicate: str = Field(..., description="Predicate from controlled vocabulary")
    object: dict = Field(..., description="Object of claim")
    claim_type: str = Field(..., description="Claim category (compliance, security, financial)")
    time_scope: dict | None = Field(None, description="Time period/scope")
    source_reliability: str = Field("unknown", description="audited, official, internal, third_party, unknown")


class ExtractedFactMetric(ExtractedFact):
    """Extracted metric (quantitative value)."""

    entity_id: str | None = Field(None, description="Entity identifier")
    entity_type: str | None = Field(None, description="Entity type (company, product, segment)")
    metric_name: str = Field(..., description="Metric name from controlled vocabulary")
    metric_category: str | None = Field(None, description="Category (revenue, profitability, etc.)")
    value_numeric: float | None = Field(None, description="Parsed numeric value")
    value_raw: str | None = Field(None, description="Raw value as stated")
    unit: str | None = Field(None, description="Unit of measurement")
    currency: str | None = Field(None, description="Currency code (USD, EUR)")
    period_start: date | None = Field(None, description="Period start date")
    period_end: date | None = Field(None, description="Period end date")
    as_of: date | None = Field(None, description="Point-in-time value date")
    period_type: str | None = Field(None, description="monthly, quarterly, annual, ytd, ltm")
    method: str | None = Field(None, description="Calculation method (GAAP, non-GAAP)")
    source_reliability: str = Field("unknown")
    quality_flags: list[str] = Field(default_factory=list, description="estimated, restated, pro_forma")


class ExtractedFactConstraint(ExtractedFact):
    """Extracted constraint/definition/dependency."""

    constraint_type: str = Field(..., description="definition, dependency, exclusion, eligibility, covenant, assumption")
    applies_to: dict = Field(..., description="References to claim_ids/metric_ids")
    statement: str = Field(..., description="The constraint statement")


class ExtractedFactRisk(ExtractedFact):
    """Extracted risk identification."""

    risk_type: str = Field(..., description="Risk type from controlled vocabulary")
    risk_category: str | None = Field(None, description="financial, operational, legal, etc.")
    severity: str = Field("medium", description="critical, high, medium, low, informational")
    statement: str = Field(..., description="Risk description")
    rationale: str | None = Field(None, description="Why this was identified as a risk")
    related_claims: list[str] = Field(default_factory=list)
    related_metrics: list[str] = Field(default_factory=list)


class ExtractedQualityConflict(BaseModel):
    """Detected conflict between facts."""

    topic: str = Field(..., description="Topic of the conflict")
    severity: str = Field("medium", description="critical, high, medium, low, informational")
    claim_ids: list[str] = Field(default_factory=list)
    metric_ids: list[str] = Field(default_factory=list)
    reason: str = Field(..., description="Why this is a conflict")


class ExtractedQualityQuestion(BaseModel):
    """Open question identified during extraction."""

    question: str = Field(..., description="The open question")
    category: str = Field("missing_data", description="missing_data, ambiguous, verification, clarification, methodology, temporal")
    context: str | None = Field(None, description="Additional context")
    related_claim_ids: list[str] = Field(default_factory=list)
    related_metric_ids: list[str] = Field(default_factory=list)


class MultiLevelExtractionResult(BaseModel):
    """Result of multi-level extraction."""

    profile_code: str
    level: int
    claims: list[ExtractedFactClaim] = Field(default_factory=list)
    metrics: list[ExtractedFactMetric] = Field(default_factory=list)
    constraints: list[ExtractedFactConstraint] = Field(default_factory=list)
    risks: list[ExtractedFactRisk] = Field(default_factory=list)
    conflicts: list[ExtractedQualityConflict] = Field(default_factory=list)
    open_questions: list[ExtractedQualityQuestion] = Field(default_factory=list)
    extraction_metadata: dict = Field(default_factory=dict)
