"""Quality analysis schemas for API responses."""

import uuid
from typing import Any

from pydantic import BaseModel, Field

from evidence_repository.models.quality import ConflictSeverity, QuestionCategory


class MetricValueDetail(BaseModel):
    """Details about a metric value involved in a conflict."""

    id: str = Field(..., description="Metric ID")
    value_numeric: float | None = Field(None, description="Numeric value")
    value_raw: str | None = Field(None, description="Raw value as stated")
    unit: str | None = Field(None, description="Unit of measurement")
    currency: str | None = Field(None, description="Currency code")
    period_start: str | None = Field(None, description="Period start date")
    period_end: str | None = Field(None, description="Period end date")
    as_of: str | None = Field(None, description="As-of date")
    period_type: str | None = Field(None, description="Period type")
    certainty: str | None = Field(None, description="Certainty level")
    source_reliability: str | None = Field(None, description="Source reliability")


class MetricConflictResponse(BaseModel):
    """A detected conflict between metric values."""

    metric_name: str = Field(..., description="Name of the conflicting metric")
    entity_id: str | None = Field(None, description="Entity the metric refers to")
    metric_ids: list[str] = Field(..., description="IDs of conflicting metrics")
    values: list[dict[str, Any]] = Field(..., description="Conflicting values")
    severity: str = Field(..., description="Conflict severity level")
    reason: str = Field(..., description="Human-readable conflict explanation")


class ClaimValueDetail(BaseModel):
    """Details about a claim value involved in a conflict."""

    id: str = Field(..., description="Claim ID")
    value: Any = Field(..., description="Claim value")
    certainty: str | None = Field(None, description="Certainty level")
    time_scope: dict | None = Field(None, description="Time scope")


class ClaimConflictResponse(BaseModel):
    """A detected conflict between claims."""

    predicate: str = Field(..., description="Claim predicate")
    subject: dict = Field(..., description="Claim subject")
    claim_ids: list[str] = Field(..., description="IDs of conflicting claims")
    values: list[dict[str, Any]] = Field(..., description="Conflicting values")
    severity: str = Field(..., description="Conflict severity level")
    reason: str = Field(..., description="Human-readable conflict explanation")


class OpenQuestionResponse(BaseModel):
    """A detected open question about extracted data."""

    category: str = Field(..., description="Question category")
    question: str = Field(..., description="The open question")
    context: str = Field(..., description="Additional context")
    related_metric_ids: list[str] = Field(
        default_factory=list, description="Related metric IDs"
    )
    related_claim_ids: list[str] = Field(
        default_factory=list, description="Related claim IDs"
    )


class QualitySummary(BaseModel):
    """Summary statistics for quality analysis."""

    total_metrics: int = Field(..., description="Total metrics analyzed")
    total_claims: int = Field(..., description="Total claims analyzed")
    metric_conflicts_count: int = Field(..., description="Number of metric conflicts")
    claim_conflicts_count: int = Field(..., description="Number of claim conflicts")
    open_questions_count: int = Field(..., description="Number of open questions")
    critical_conflicts: int = Field(..., description="Number of critical conflicts")
    high_conflicts: int = Field(..., description="Number of high severity conflicts")


class QualityAnalysisResponse(BaseModel):
    """Complete quality analysis response for a document."""

    document_id: uuid.UUID = Field(..., description="Document ID")
    version_id: uuid.UUID = Field(..., description="Document version ID")
    metric_conflicts: list[MetricConflictResponse] = Field(
        ..., description="Detected metric conflicts"
    )
    claim_conflicts: list[ClaimConflictResponse] = Field(
        ..., description="Detected claim conflicts"
    )
    open_questions: list[OpenQuestionResponse] = Field(
        ..., description="Detected open questions"
    )
    summary: QualitySummary = Field(..., description="Analysis summary")

    @classmethod
    def from_analysis_result(
        cls, result: "QualityAnalysisResult"
    ) -> "QualityAnalysisResponse":
        """Convert from service result to API response."""
        from evidence_repository.services.quality_analysis import QualityAnalysisResult

        return cls(
            document_id=result.document_id,
            version_id=result.version_id,
            metric_conflicts=[
                MetricConflictResponse(
                    metric_name=c.metric_name,
                    entity_id=c.entity_id,
                    metric_ids=[str(mid) for mid in c.metric_ids],
                    values=c.values,
                    severity=c.severity.value,
                    reason=c.reason,
                )
                for c in result.metric_conflicts
            ],
            claim_conflicts=[
                ClaimConflictResponse(
                    predicate=c.predicate,
                    subject=c.subject,
                    claim_ids=[str(cid) for cid in c.claim_ids],
                    values=c.values,
                    severity=c.severity.value,
                    reason=c.reason,
                )
                for c in result.claim_conflicts
            ],
            open_questions=[
                OpenQuestionResponse(
                    category=q.category.value,
                    question=q.question,
                    context=q.context,
                    related_metric_ids=[str(mid) for mid in q.related_metric_ids],
                    related_claim_ids=[str(cid) for cid in q.related_claim_ids],
                )
                for q in result.open_questions
            ],
            summary=QualitySummary(**result.summary),
        )
