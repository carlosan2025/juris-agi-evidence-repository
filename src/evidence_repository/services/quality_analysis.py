"""Quality analysis service for detecting conflicts and open questions."""

import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from evidence_repository.models.document import Document, DocumentVersion
from evidence_repository.models.facts import FactClaim, FactMetric
from evidence_repository.models.quality import (
    ConflictSeverity,
    QualityConflict,
    QualityOpenQuestion,
    QuestionCategory,
)


# =============================================================================
# Result Data Classes
# =============================================================================


@dataclass
class MetricConflict:
    """A detected conflict between metric values."""

    metric_name: str
    entity_id: str | None
    metric_ids: list[uuid.UUID]
    values: list[dict[str, Any]]
    severity: ConflictSeverity
    reason: str


@dataclass
class ClaimConflict:
    """A detected conflict between claims."""

    predicate: str
    subject: dict
    claim_ids: list[uuid.UUID]
    values: list[dict[str, Any]]
    severity: ConflictSeverity
    reason: str


@dataclass
class OpenQuestion:
    """A detected open question about extracted data."""

    category: QuestionCategory
    question: str
    context: str
    related_metric_ids: list[uuid.UUID] = field(default_factory=list)
    related_claim_ids: list[uuid.UUID] = field(default_factory=list)


@dataclass
class QualityAnalysisResult:
    """Complete quality analysis result for a document."""

    document_id: uuid.UUID
    version_id: uuid.UUID
    metric_conflicts: list[MetricConflict]
    claim_conflicts: list[ClaimConflict]
    open_questions: list[OpenQuestion]
    summary: dict[str, Any]


# =============================================================================
# Quality Analysis Service
# =============================================================================


class QualityAnalysisService:
    """Service for analyzing extraction quality: conflicts and open questions."""

    # Financial metrics that are considered stale after 12 months
    FINANCIAL_METRICS = {
        "arr", "mrr", "revenue", "net_income", "gross_profit", "ebitda",
        "burn", "cash", "cash_runway", "runway", "assets", "liabilities",
        "equity", "debt", "rd_spend", "capex", "opex", "cogs",
        "gross_margin", "net_margin", "operating_margin",
    }

    # Boolean predicates where True/False conflicts matter
    BOOLEAN_PREDICATES = {
        "has_soc2", "is_iso27001", "is_gdpr_compliant", "is_hipaa_compliant",
        "has_security_incident", "owns_ip", "has_patent", "is_profitable",
        "raised_funding", "has_debt", "is_audited", "has_data_breach",
    }

    def __init__(self, db: AsyncSession):
        """Initialize quality analysis service.

        Args:
            db: Database session.
        """
        self.db = db

    async def analyze_document(
        self,
        document_id: uuid.UUID,
        version_id: uuid.UUID | None = None,
        profile_id: uuid.UUID | None = None,
        level_id: uuid.UUID | None = None,
    ) -> QualityAnalysisResult:
        """Analyze quality of extracted facts for a document.

        Args:
            document_id: Document ID to analyze.
            version_id: Optional specific version (defaults to latest).
            profile_id: Optional extraction profile filter.
            level_id: Optional extraction level filter.

        Returns:
            QualityAnalysisResult with conflicts and open questions.
        """
        # Get document version
        if version_id is None:
            version_id = await self._get_latest_version_id(document_id)
            if version_id is None:
                return QualityAnalysisResult(
                    document_id=document_id,
                    version_id=uuid.UUID(int=0),
                    metric_conflicts=[],
                    claim_conflicts=[],
                    open_questions=[],
                    summary={"error": "No document version found"},
                )

        # Get metrics and claims
        metrics = await self._get_metrics(document_id, version_id, profile_id, level_id)
        claims = await self._get_claims(document_id, version_id, profile_id, level_id)

        # Detect conflicts
        metric_conflicts = self._detect_metric_conflicts(metrics)
        claim_conflicts = self._detect_claim_conflicts(claims)

        # Detect open questions
        open_questions = self._detect_open_questions(metrics, claims)

        # Build summary
        summary = {
            "total_metrics": len(metrics),
            "total_claims": len(claims),
            "metric_conflicts_count": len(metric_conflicts),
            "claim_conflicts_count": len(claim_conflicts),
            "open_questions_count": len(open_questions),
            "critical_conflicts": sum(
                1 for c in metric_conflicts + claim_conflicts
                if c.severity == ConflictSeverity.CRITICAL
            ),
            "high_conflicts": sum(
                1 for c in metric_conflicts + claim_conflicts
                if c.severity == ConflictSeverity.HIGH
            ),
        }

        return QualityAnalysisResult(
            document_id=document_id,
            version_id=version_id,
            metric_conflicts=metric_conflicts,
            claim_conflicts=claim_conflicts,
            open_questions=open_questions,
            summary=summary,
        )

    # =========================================================================
    # Metric Conflict Detection
    # =========================================================================

    def _detect_metric_conflicts(
        self, metrics: list[FactMetric]
    ) -> list[MetricConflict]:
        """Detect conflicts between metrics.

        Conflicts occur when:
        - Same metric_name + entity_id
        - Overlapping time periods
        - Different numeric values

        Args:
            metrics: List of extracted metrics.

        Returns:
            List of detected metric conflicts.
        """
        conflicts: list[MetricConflict] = []

        # Group metrics by (metric_name, entity_id)
        grouped: dict[tuple[str, str | None], list[FactMetric]] = {}
        for metric in metrics:
            key = (metric.metric_name, metric.entity_id)
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(metric)

        # Check each group for conflicts
        for (metric_name, entity_id), group in grouped.items():
            if len(group) < 2:
                continue

            # Check all pairs for overlapping periods with different values
            for i, m1 in enumerate(group):
                for m2 in group[i + 1:]:
                    if self._periods_overlap(m1, m2) and self._values_differ(m1, m2):
                        # Determine severity based on value difference
                        severity = self._calculate_metric_conflict_severity(m1, m2)

                        conflict = MetricConflict(
                            metric_name=metric_name,
                            entity_id=entity_id,
                            metric_ids=[m1.id, m2.id],
                            values=[
                                self._metric_to_value_dict(m1),
                                self._metric_to_value_dict(m2),
                            ],
                            severity=severity,
                            reason=self._build_metric_conflict_reason(m1, m2),
                        )
                        conflicts.append(conflict)

        return conflicts

    def _periods_overlap(self, m1: FactMetric, m2: FactMetric) -> bool:
        """Check if two metrics have overlapping time periods."""
        # If both have as_of dates, compare them (point-in-time values)
        if m1.as_of and m2.as_of:
            return m1.as_of == m2.as_of

        # If both have period ranges
        if m1.period_start and m1.period_end and m2.period_start and m2.period_end:
            # Periods overlap if one starts before the other ends
            return m1.period_start <= m2.period_end and m2.period_start <= m1.period_end

        # If one has as_of and other has period range
        if m1.as_of and m2.period_start and m2.period_end:
            return m2.period_start <= m1.as_of <= m2.period_end
        if m2.as_of and m1.period_start and m1.period_end:
            return m1.period_start <= m2.as_of <= m1.period_end

        # If both have same period_type (e.g., both annual), consider overlap
        if m1.period_type and m2.period_type and m1.period_type == m2.period_type:
            return True

        # No period info available - assume potential overlap
        return True

    def _values_differ(self, m1: FactMetric, m2: FactMetric) -> bool:
        """Check if two metrics have different values."""
        if m1.value_numeric is None or m2.value_numeric is None:
            # Compare raw values if numeric not available
            return m1.value_raw != m2.value_raw

        # Check for significant difference (> 1% difference)
        if m1.value_numeric == 0 and m2.value_numeric == 0:
            return False
        if m1.value_numeric == 0 or m2.value_numeric == 0:
            return True

        relative_diff = abs(m1.value_numeric - m2.value_numeric) / max(
            abs(m1.value_numeric), abs(m2.value_numeric)
        )
        return relative_diff > 0.01  # More than 1% difference

    def _calculate_metric_conflict_severity(
        self, m1: FactMetric, m2: FactMetric
    ) -> ConflictSeverity:
        """Calculate severity of metric conflict based on value difference."""
        if m1.value_numeric is None or m2.value_numeric is None:
            return ConflictSeverity.MEDIUM

        if m1.value_numeric == 0 or m2.value_numeric == 0:
            return ConflictSeverity.HIGH

        relative_diff = abs(m1.value_numeric - m2.value_numeric) / max(
            abs(m1.value_numeric), abs(m2.value_numeric)
        )

        if relative_diff > 0.50:  # > 50% difference
            return ConflictSeverity.CRITICAL
        elif relative_diff > 0.25:  # > 25% difference
            return ConflictSeverity.HIGH
        elif relative_diff > 0.10:  # > 10% difference
            return ConflictSeverity.MEDIUM
        else:
            return ConflictSeverity.LOW

    def _metric_to_value_dict(self, metric: FactMetric) -> dict[str, Any]:
        """Convert metric to a value dictionary for conflict reporting."""
        return {
            "id": str(metric.id),
            "value_numeric": metric.value_numeric,
            "value_raw": metric.value_raw,
            "unit": metric.unit,
            "currency": metric.currency,
            "period_start": str(metric.period_start) if metric.period_start else None,
            "period_end": str(metric.period_end) if metric.period_end else None,
            "as_of": str(metric.as_of) if metric.as_of else None,
            "period_type": metric.period_type,
            "certainty": metric.certainty.value if metric.certainty else None,
            "source_reliability": metric.source_reliability.value if metric.source_reliability else None,
        }

    def _build_metric_conflict_reason(
        self, m1: FactMetric, m2: FactMetric
    ) -> str:
        """Build human-readable conflict reason for metrics."""
        period_desc = ""
        if m1.as_of and m2.as_of:
            period_desc = f" as of {m1.as_of}"
        elif m1.period_type:
            period_desc = f" for {m1.period_type} period"

        val1 = f"{m1.value_numeric}" if m1.value_numeric else m1.value_raw
        val2 = f"{m2.value_numeric}" if m2.value_numeric else m2.value_raw

        if m1.currency:
            val1 = f"{m1.currency} {val1}"
            val2 = f"{m2.currency} {val2}"

        return (
            f"Conflicting values for '{m1.metric_name}'{period_desc}: "
            f"{val1} vs {val2}"
        )

    # =========================================================================
    # Claim Conflict Detection
    # =========================================================================

    def _detect_claim_conflicts(self, claims: list[FactClaim]) -> list[ClaimConflict]:
        """Detect conflicts between claims.

        Conflicts occur when:
        - Same predicate (especially boolean predicates)
        - Same subject
        - Different object values (True vs False)

        Args:
            claims: List of extracted claims.

        Returns:
            List of detected claim conflicts.
        """
        conflicts: list[ClaimConflict] = []

        # Group claims by (predicate, subject_key)
        grouped: dict[tuple[str, str], list[FactClaim]] = {}
        for claim in claims:
            subject_key = self._subject_to_key(claim.subject)
            key = (claim.predicate, subject_key)
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(claim)

        # Check each group for conflicts
        for (predicate, subject_key), group in grouped.items():
            if len(group) < 2:
                continue

            # For boolean predicates, check for True/False conflicts
            if predicate in self.BOOLEAN_PREDICATES:
                conflict = self._check_boolean_claim_conflict(predicate, group)
                if conflict:
                    conflicts.append(conflict)
            else:
                # For non-boolean predicates, check for different object values
                conflict = self._check_object_value_conflict(predicate, group)
                if conflict:
                    conflicts.append(conflict)

        return conflicts

    def _subject_to_key(self, subject: dict) -> str:
        """Convert subject dict to a comparable key."""
        # Use type + name/id as key
        subject_type = subject.get("type", "unknown")
        subject_name = subject.get("name") or subject.get("id") or "unknown"
        return f"{subject_type}:{subject_name}"

    def _check_boolean_claim_conflict(
        self, predicate: str, claims: list[FactClaim]
    ) -> ClaimConflict | None:
        """Check for boolean claim conflicts (True vs False)."""
        true_claims: list[FactClaim] = []
        false_claims: list[FactClaim] = []

        for claim in claims:
            obj_value = claim.object.get("value")
            if obj_value is True or str(obj_value).lower() in ("true", "yes", "1"):
                true_claims.append(claim)
            elif obj_value is False or str(obj_value).lower() in ("false", "no", "0"):
                false_claims.append(claim)

        if true_claims and false_claims:
            # Conflict: some say True, others say False
            all_claims = true_claims + false_claims
            return ClaimConflict(
                predicate=predicate,
                subject=claims[0].subject,
                claim_ids=[c.id for c in all_claims],
                values=[
                    {
                        "id": str(c.id),
                        "value": c.object.get("value"),
                        "certainty": c.certainty.value if c.certainty else None,
                        "time_scope": c.time_scope,
                    }
                    for c in all_claims
                ],
                severity=ConflictSeverity.HIGH,
                reason=(
                    f"Conflicting boolean values for '{predicate}': "
                    f"{len(true_claims)} claim(s) say True, "
                    f"{len(false_claims)} claim(s) say False"
                ),
            )

        return None

    def _check_object_value_conflict(
        self, predicate: str, claims: list[FactClaim]
    ) -> ClaimConflict | None:
        """Check for non-boolean claim object value conflicts."""
        # Group by object value
        values: dict[str, list[FactClaim]] = {}
        for claim in claims:
            obj_key = str(claim.object.get("value", claim.object))
            if obj_key not in values:
                values[obj_key] = []
            values[obj_key].append(claim)

        if len(values) > 1:
            # Multiple different values for same predicate+subject
            all_claims = [c for group in values.values() for c in group]
            return ClaimConflict(
                predicate=predicate,
                subject=claims[0].subject,
                claim_ids=[c.id for c in all_claims],
                values=[
                    {
                        "id": str(c.id),
                        "value": c.object.get("value", c.object),
                        "certainty": c.certainty.value if c.certainty else None,
                    }
                    for c in all_claims
                ],
                severity=ConflictSeverity.MEDIUM,
                reason=(
                    f"Multiple different values for '{predicate}': "
                    f"{list(values.keys())}"
                ),
            )

        return None

    # =========================================================================
    # Open Question Detection
    # =========================================================================

    def _detect_open_questions(
        self, metrics: list[FactMetric], claims: list[FactClaim]
    ) -> list[OpenQuestion]:
        """Detect open questions about extracted data.

        Detects:
        - Missing units, currency, or periods on metrics
        - Financial metrics older than 12 months

        Args:
            metrics: List of extracted metrics.
            claims: List of extracted claims.

        Returns:
            List of detected open questions.
        """
        questions: list[OpenQuestion] = []

        # Check metrics for missing data
        for metric in metrics:
            # Missing unit
            if metric.value_numeric is not None and not metric.unit:
                questions.append(OpenQuestion(
                    category=QuestionCategory.MISSING_DATA,
                    question=f"What is the unit for '{metric.metric_name}'?",
                    context=(
                        f"Metric '{metric.metric_name}' has value {metric.value_numeric} "
                        f"but no unit specified."
                    ),
                    related_metric_ids=[metric.id],
                ))

            # Missing currency for monetary metrics
            if self._is_monetary_metric(metric) and not metric.currency:
                questions.append(OpenQuestion(
                    category=QuestionCategory.MISSING_DATA,
                    question=f"What is the currency for '{metric.metric_name}'?",
                    context=(
                        f"Metric '{metric.metric_name}' appears to be monetary "
                        f"but no currency specified."
                    ),
                    related_metric_ids=[metric.id],
                ))

            # Missing time period
            if not metric.period_start and not metric.period_end and not metric.as_of:
                questions.append(OpenQuestion(
                    category=QuestionCategory.MISSING_DATA,
                    question=f"What is the time period for '{metric.metric_name}'?",
                    context=(
                        f"Metric '{metric.metric_name}' has no time period or as-of date. "
                        f"Value: {metric.value_raw or metric.value_numeric}"
                    ),
                    related_metric_ids=[metric.id],
                ))

            # Stale financial metrics (older than 12 months)
            if metric.metric_name.lower() in self.FINANCIAL_METRICS:
                stale_question = self._check_stale_financial(metric)
                if stale_question:
                    questions.append(stale_question)

        return questions

    def _is_monetary_metric(self, metric: FactMetric) -> bool:
        """Check if a metric is likely monetary based on name or unit."""
        monetary_keywords = {
            "revenue", "arr", "mrr", "income", "profit", "loss", "burn",
            "cash", "debt", "equity", "assets", "liabilities", "capex",
            "opex", "cogs", "ebitda", "spend", "cost", "price", "value",
        }
        name_lower = metric.metric_name.lower()
        return any(kw in name_lower for kw in monetary_keywords)

    def _check_stale_financial(self, metric: FactMetric) -> OpenQuestion | None:
        """Check if a financial metric is stale (older than 12 months)."""
        today = date.today()
        cutoff = today - timedelta(days=365)

        reference_date: date | None = None
        date_type = ""

        if metric.as_of:
            reference_date = metric.as_of
            date_type = "as-of date"
        elif metric.period_end:
            reference_date = metric.period_end
            date_type = "period end date"

        if reference_date and reference_date < cutoff:
            age_months = (today - reference_date).days // 30
            return OpenQuestion(
                category=QuestionCategory.TEMPORAL,
                question=(
                    f"Is the '{metric.metric_name}' value still current? "
                    f"Data is {age_months} months old."
                ),
                context=(
                    f"Financial metric '{metric.metric_name}' has {date_type} of "
                    f"{reference_date}, which is more than 12 months ago. "
                    f"Current value: {metric.value_raw or metric.value_numeric}"
                ),
                related_metric_ids=[metric.id],
            )

        return None

    # =========================================================================
    # Database Helpers
    # =========================================================================

    async def _get_latest_version_id(
        self, document_id: uuid.UUID
    ) -> uuid.UUID | None:
        """Get the latest version ID for a document."""
        result = await self.db.execute(
            select(DocumentVersion.id)
            .where(DocumentVersion.document_id == document_id)
            .order_by(DocumentVersion.version_number.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        return row

    async def _get_metrics(
        self,
        document_id: uuid.UUID,
        version_id: uuid.UUID,
        profile_id: uuid.UUID | None = None,
        level_id: uuid.UUID | None = None,
    ) -> list[FactMetric]:
        """Get metrics for a document version."""
        conditions = [
            FactMetric.document_id == document_id,
            FactMetric.version_id == version_id,
        ]
        if profile_id:
            conditions.append(FactMetric.profile_id == profile_id)
        if level_id:
            conditions.append(FactMetric.level_id == level_id)

        result = await self.db.execute(
            select(FactMetric).where(and_(*conditions))
        )
        return list(result.scalars().all())

    async def _get_claims(
        self,
        document_id: uuid.UUID,
        version_id: uuid.UUID,
        profile_id: uuid.UUID | None = None,
        level_id: uuid.UUID | None = None,
    ) -> list[FactClaim]:
        """Get claims for a document version."""
        conditions = [
            FactClaim.document_id == document_id,
            FactClaim.version_id == version_id,
        ]
        if profile_id:
            conditions.append(FactClaim.profile_id == profile_id)
        if level_id:
            conditions.append(FactClaim.level_id == level_id)

        result = await self.db.execute(
            select(FactClaim).where(and_(*conditions))
        )
        return list(result.scalars().all())
