"""Tests for quality analysis service."""

import uuid
from datetime import date, timedelta

import pytest

from evidence_repository.models.facts import FactCertainty, FactClaim, FactMetric, SourceReliability
from evidence_repository.models.quality import ConflictSeverity, QuestionCategory
from evidence_repository.services.quality_analysis import (
    ClaimConflict,
    MetricConflict,
    OpenQuestion,
    QualityAnalysisService,
)


class TestMetricConflictDetection:
    """Tests for metric conflict detection logic."""

    def _create_metric(
        self,
        metric_name: str = "arr",
        entity_id: str | None = "company-1",
        value_numeric: float | None = 10000000.0,
        value_raw: str | None = "$10M",
        period_start: date | None = None,
        period_end: date | None = None,
        as_of: date | None = None,
        period_type: str | None = None,
        unit: str | None = None,
        currency: str | None = None,
    ) -> FactMetric:
        """Create a mock FactMetric for testing."""
        metric = FactMetric(
            id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            version_id=uuid.uuid4(),
            profile_id=uuid.uuid4(),
            level_id=uuid.uuid4(),
            extraction_run_id=uuid.uuid4(),
            metric_name=metric_name,
            entity_id=entity_id,
            value_numeric=value_numeric,
            value_raw=value_raw,
            period_start=period_start,
            period_end=period_end,
            as_of=as_of,
            period_type=period_type,
            unit=unit,
            currency=currency,
            certainty=FactCertainty.DEFINITE,
            source_reliability=SourceReliability.OFFICIAL,
        )
        return metric

    def test_no_conflict_single_metric(self):
        """Test no conflict detected with single metric."""
        service = QualityAnalysisService.__new__(QualityAnalysisService)
        metrics = [self._create_metric()]

        conflicts = service._detect_metric_conflicts(metrics)

        assert len(conflicts) == 0

    def test_no_conflict_different_metrics(self):
        """Test no conflict between different metric names."""
        service = QualityAnalysisService.__new__(QualityAnalysisService)
        metrics = [
            self._create_metric(metric_name="arr", value_numeric=10000000),
            self._create_metric(metric_name="mrr", value_numeric=833333),
        ]

        conflicts = service._detect_metric_conflicts(metrics)

        assert len(conflicts) == 0

    def test_no_conflict_same_values(self):
        """Test no conflict when metrics have same values."""
        service = QualityAnalysisService.__new__(QualityAnalysisService)
        metrics = [
            self._create_metric(value_numeric=10000000, as_of=date(2024, 12, 31)),
            self._create_metric(value_numeric=10000000, as_of=date(2024, 12, 31)),
        ]

        conflicts = service._detect_metric_conflicts(metrics)

        assert len(conflicts) == 0

    def test_conflict_same_metric_different_values_same_period(self):
        """Test conflict detected when same metric has different values for same period."""
        service = QualityAnalysisService.__new__(QualityAnalysisService)
        metrics = [
            self._create_metric(
                value_numeric=10000000,
                period_start=date(2024, 1, 1),
                period_end=date(2024, 12, 31),
            ),
            self._create_metric(
                value_numeric=12000000,
                period_start=date(2024, 1, 1),
                period_end=date(2024, 12, 31),
            ),
        ]

        conflicts = service._detect_metric_conflicts(metrics)

        assert len(conflicts) == 1
        assert conflicts[0].metric_name == "arr"
        assert len(conflicts[0].metric_ids) == 2

    def test_conflict_overlapping_periods(self):
        """Test conflict detected when periods overlap."""
        service = QualityAnalysisService.__new__(QualityAnalysisService)
        metrics = [
            self._create_metric(
                value_numeric=10000000,
                period_start=date(2024, 1, 1),
                period_end=date(2024, 12, 31),
            ),
            self._create_metric(
                value_numeric=12000000,
                period_start=date(2024, 7, 1),
                period_end=date(2025, 6, 30),
            ),
        ]

        conflicts = service._detect_metric_conflicts(metrics)

        assert len(conflicts) == 1

    def test_no_conflict_non_overlapping_periods(self):
        """Test no conflict when periods don't overlap."""
        service = QualityAnalysisService.__new__(QualityAnalysisService)
        metrics = [
            self._create_metric(
                value_numeric=10000000,
                period_start=date(2023, 1, 1),
                period_end=date(2023, 12, 31),
            ),
            self._create_metric(
                value_numeric=12000000,
                period_start=date(2024, 1, 1),
                period_end=date(2024, 12, 31),
            ),
        ]

        conflicts = service._detect_metric_conflicts(metrics)

        assert len(conflicts) == 0

    def test_conflict_severity_critical_large_difference(self):
        """Test critical severity for >50% value difference."""
        service = QualityAnalysisService.__new__(QualityAnalysisService)
        metrics = [
            self._create_metric(value_numeric=10000000, as_of=date(2024, 12, 31)),
            self._create_metric(value_numeric=20000000, as_of=date(2024, 12, 31)),
        ]

        conflicts = service._detect_metric_conflicts(metrics)

        assert len(conflicts) == 1
        assert conflicts[0].severity == ConflictSeverity.CRITICAL

    def test_conflict_severity_high_medium_difference(self):
        """Test high severity for 25-50% value difference."""
        service = QualityAnalysisService.__new__(QualityAnalysisService)
        metrics = [
            self._create_metric(value_numeric=10000000, as_of=date(2024, 12, 31)),
            self._create_metric(value_numeric=13000000, as_of=date(2024, 12, 31)),
        ]

        conflicts = service._detect_metric_conflicts(metrics)

        assert len(conflicts) == 1
        assert conflicts[0].severity == ConflictSeverity.HIGH

    def test_conflict_severity_medium_small_difference(self):
        """Test medium severity for 10-25% value difference."""
        service = QualityAnalysisService.__new__(QualityAnalysisService)
        metrics = [
            self._create_metric(value_numeric=10000000, as_of=date(2024, 12, 31)),
            self._create_metric(value_numeric=11500000, as_of=date(2024, 12, 31)),
        ]

        conflicts = service._detect_metric_conflicts(metrics)

        assert len(conflicts) == 1
        assert conflicts[0].severity == ConflictSeverity.MEDIUM

    def test_conflict_severity_low_tiny_difference(self):
        """Test low severity for 1-10% value difference."""
        service = QualityAnalysisService.__new__(QualityAnalysisService)
        metrics = [
            self._create_metric(value_numeric=10000000, as_of=date(2024, 12, 31)),
            self._create_metric(value_numeric=10500000, as_of=date(2024, 12, 31)),
        ]

        conflicts = service._detect_metric_conflicts(metrics)

        assert len(conflicts) == 1
        assert conflicts[0].severity == ConflictSeverity.LOW

    def test_no_conflict_different_entities(self):
        """Test no conflict when entity IDs differ."""
        service = QualityAnalysisService.__new__(QualityAnalysisService)
        metrics = [
            self._create_metric(entity_id="company-1", value_numeric=10000000),
            self._create_metric(entity_id="company-2", value_numeric=20000000),
        ]

        conflicts = service._detect_metric_conflicts(metrics)

        assert len(conflicts) == 0


class TestClaimConflictDetection:
    """Tests for claim conflict detection logic."""

    def _create_claim(
        self,
        predicate: str = "has_soc2",
        subject: dict | None = None,
        object_value: dict | None = None,
        claim_type: str = "compliance",
    ) -> FactClaim:
        """Create a mock FactClaim for testing."""
        if subject is None:
            subject = {"type": "company", "name": "Acme Corp"}
        if object_value is None:
            object_value = {"value": True}

        claim = FactClaim(
            id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            version_id=uuid.uuid4(),
            profile_id=uuid.uuid4(),
            level_id=uuid.uuid4(),
            extraction_run_id=uuid.uuid4(),
            subject=subject,
            predicate=predicate,
            object=object_value,
            claim_type=claim_type,
            certainty=FactCertainty.DEFINITE,
            source_reliability=SourceReliability.OFFICIAL,
        )
        return claim

    def test_no_conflict_single_claim(self):
        """Test no conflict with single claim."""
        service = QualityAnalysisService.__new__(QualityAnalysisService)
        claims = [self._create_claim()]

        conflicts = service._detect_claim_conflicts(claims)

        assert len(conflicts) == 0

    def test_no_conflict_different_predicates(self):
        """Test no conflict between different predicates."""
        service = QualityAnalysisService.__new__(QualityAnalysisService)
        claims = [
            self._create_claim(predicate="has_soc2", object_value={"value": True}),
            self._create_claim(predicate="is_iso27001", object_value={"value": False}),
        ]

        conflicts = service._detect_claim_conflicts(claims)

        assert len(conflicts) == 0

    def test_no_conflict_same_boolean_values(self):
        """Test no conflict when boolean claims agree."""
        service = QualityAnalysisService.__new__(QualityAnalysisService)
        claims = [
            self._create_claim(predicate="has_soc2", object_value={"value": True}),
            self._create_claim(predicate="has_soc2", object_value={"value": True}),
        ]

        conflicts = service._detect_claim_conflicts(claims)

        assert len(conflicts) == 0

    def test_conflict_boolean_true_vs_false(self):
        """Test conflict detected when boolean claims contradict."""
        service = QualityAnalysisService.__new__(QualityAnalysisService)
        claims = [
            self._create_claim(predicate="has_soc2", object_value={"value": True}),
            self._create_claim(predicate="has_soc2", object_value={"value": False}),
        ]

        conflicts = service._detect_claim_conflicts(claims)

        assert len(conflicts) == 1
        assert conflicts[0].predicate == "has_soc2"
        assert conflicts[0].severity == ConflictSeverity.HIGH
        assert len(conflicts[0].claim_ids) == 2

    def test_conflict_boolean_yes_no_strings(self):
        """Test conflict detected with yes/no string values."""
        service = QualityAnalysisService.__new__(QualityAnalysisService)
        claims = [
            self._create_claim(predicate="has_soc2", object_value={"value": "yes"}),
            self._create_claim(predicate="has_soc2", object_value={"value": "no"}),
        ]

        conflicts = service._detect_claim_conflicts(claims)

        assert len(conflicts) == 1

    def test_no_conflict_different_subjects(self):
        """Test no conflict when subjects differ."""
        service = QualityAnalysisService.__new__(QualityAnalysisService)
        claims = [
            self._create_claim(
                subject={"type": "company", "name": "Acme Corp"},
                object_value={"value": True},
            ),
            self._create_claim(
                subject={"type": "company", "name": "Beta Inc"},
                object_value={"value": False},
            ),
        ]

        conflicts = service._detect_claim_conflicts(claims)

        assert len(conflicts) == 0


class TestOpenQuestionDetection:
    """Tests for open question detection logic."""

    def _create_metric(
        self,
        metric_name: str = "arr",
        value_numeric: float | None = 10000000.0,
        unit: str | None = None,
        currency: str | None = None,
        period_start: date | None = None,
        period_end: date | None = None,
        as_of: date | None = None,
    ) -> FactMetric:
        """Create a mock FactMetric for testing."""
        metric = FactMetric(
            id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            version_id=uuid.uuid4(),
            profile_id=uuid.uuid4(),
            level_id=uuid.uuid4(),
            extraction_run_id=uuid.uuid4(),
            metric_name=metric_name,
            value_numeric=value_numeric,
            unit=unit,
            currency=currency,
            period_start=period_start,
            period_end=period_end,
            as_of=as_of,
            certainty=FactCertainty.DEFINITE,
            source_reliability=SourceReliability.OFFICIAL,
        )
        return metric

    def test_question_missing_unit(self):
        """Test question raised for missing unit."""
        service = QualityAnalysisService.__new__(QualityAnalysisService)
        metrics = [self._create_metric(unit=None)]

        questions = service._detect_open_questions(metrics, [])

        unit_questions = [q for q in questions if "unit" in q.question.lower()]
        assert len(unit_questions) >= 1
        assert unit_questions[0].category == QuestionCategory.MISSING_DATA

    def test_question_missing_currency(self):
        """Test question raised for missing currency on monetary metric."""
        service = QualityAnalysisService.__new__(QualityAnalysisService)
        metrics = [self._create_metric(metric_name="revenue", currency=None)]

        questions = service._detect_open_questions(metrics, [])

        currency_questions = [q for q in questions if "currency" in q.question.lower()]
        assert len(currency_questions) >= 1
        assert currency_questions[0].category == QuestionCategory.MISSING_DATA

    def test_question_missing_period(self):
        """Test question raised for missing time period."""
        service = QualityAnalysisService.__new__(QualityAnalysisService)
        metrics = [
            self._create_metric(
                period_start=None,
                period_end=None,
                as_of=None,
            )
        ]

        questions = service._detect_open_questions(metrics, [])

        period_questions = [q for q in questions if "period" in q.question.lower() or "time" in q.question.lower()]
        assert len(period_questions) >= 1
        assert period_questions[0].category == QuestionCategory.MISSING_DATA

    def test_question_stale_financial_metric(self):
        """Test question raised for stale financial metric (>12 months old)."""
        service = QualityAnalysisService.__new__(QualityAnalysisService)
        old_date = date.today() - timedelta(days=400)  # ~13 months ago
        metrics = [
            self._create_metric(
                metric_name="revenue",
                as_of=old_date,
            )
        ]

        questions = service._detect_open_questions(metrics, [])

        stale_questions = [q for q in questions if q.category == QuestionCategory.TEMPORAL]
        assert len(stale_questions) >= 1
        assert "current" in stale_questions[0].question.lower() or "old" in stale_questions[0].question.lower()

    def test_no_question_recent_financial_metric(self):
        """Test no staleness question for recent metric."""
        service = QualityAnalysisService.__new__(QualityAnalysisService)
        recent_date = date.today() - timedelta(days=100)  # ~3 months ago
        metrics = [
            self._create_metric(
                metric_name="revenue",
                as_of=recent_date,
                unit="USD",
                currency="USD",
            )
        ]

        questions = service._detect_open_questions(metrics, [])

        stale_questions = [q for q in questions if q.category == QuestionCategory.TEMPORAL]
        assert len(stale_questions) == 0

    def test_no_question_complete_metric(self):
        """Test no questions for complete metric."""
        service = QualityAnalysisService.__new__(QualityAnalysisService)
        metrics = [
            self._create_metric(
                metric_name="headcount",  # Not financial
                unit="FTE",
                as_of=date.today() - timedelta(days=30),
            )
        ]

        questions = service._detect_open_questions(metrics, [])

        # Should have no questions since non-financial metric with unit and date
        assert len(questions) == 0


class TestPeriodsOverlap:
    """Tests for period overlap detection."""

    def _create_metric(
        self,
        period_start: date | None = None,
        period_end: date | None = None,
        as_of: date | None = None,
        period_type: str | None = None,
    ) -> FactMetric:
        """Create a minimal metric for overlap testing."""
        metric = FactMetric(
            id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            version_id=uuid.uuid4(),
            profile_id=uuid.uuid4(),
            level_id=uuid.uuid4(),
            extraction_run_id=uuid.uuid4(),
            metric_name="test",
            period_start=period_start,
            period_end=period_end,
            as_of=as_of,
            period_type=period_type,
            certainty=FactCertainty.DEFINITE,
            source_reliability=SourceReliability.OFFICIAL,
        )
        return metric

    def test_same_as_of_dates_overlap(self):
        """Test same as_of dates overlap."""
        service = QualityAnalysisService.__new__(QualityAnalysisService)
        m1 = self._create_metric(as_of=date(2024, 12, 31))
        m2 = self._create_metric(as_of=date(2024, 12, 31))

        assert service._periods_overlap(m1, m2) is True

    def test_different_as_of_dates_no_overlap(self):
        """Test different as_of dates don't overlap."""
        service = QualityAnalysisService.__new__(QualityAnalysisService)
        m1 = self._create_metric(as_of=date(2024, 12, 31))
        m2 = self._create_metric(as_of=date(2023, 12, 31))

        assert service._periods_overlap(m1, m2) is False

    def test_overlapping_ranges(self):
        """Test overlapping date ranges."""
        service = QualityAnalysisService.__new__(QualityAnalysisService)
        m1 = self._create_metric(
            period_start=date(2024, 1, 1),
            period_end=date(2024, 12, 31),
        )
        m2 = self._create_metric(
            period_start=date(2024, 6, 1),
            period_end=date(2025, 5, 31),
        )

        assert service._periods_overlap(m1, m2) is True

    def test_non_overlapping_ranges(self):
        """Test non-overlapping date ranges."""
        service = QualityAnalysisService.__new__(QualityAnalysisService)
        m1 = self._create_metric(
            period_start=date(2023, 1, 1),
            period_end=date(2023, 12, 31),
        )
        m2 = self._create_metric(
            period_start=date(2024, 1, 1),
            period_end=date(2024, 12, 31),
        )

        assert service._periods_overlap(m1, m2) is False

    def test_as_of_within_range_overlaps(self):
        """Test as_of date within range overlaps."""
        service = QualityAnalysisService.__new__(QualityAnalysisService)
        m1 = self._create_metric(as_of=date(2024, 6, 30))
        m2 = self._create_metric(
            period_start=date(2024, 1, 1),
            period_end=date(2024, 12, 31),
        )

        assert service._periods_overlap(m1, m2) is True

    def test_same_period_type_overlaps(self):
        """Test same period type implies overlap."""
        service = QualityAnalysisService.__new__(QualityAnalysisService)
        m1 = self._create_metric(period_type="annual")
        m2 = self._create_metric(period_type="annual")

        assert service._periods_overlap(m1, m2) is True

    def test_no_period_info_assumes_overlap(self):
        """Test no period info assumes potential overlap."""
        service = QualityAnalysisService.__new__(QualityAnalysisService)
        m1 = self._create_metric()
        m2 = self._create_metric()

        assert service._periods_overlap(m1, m2) is True


class TestValuesDiffer:
    """Tests for value difference detection."""

    def _create_metric(
        self, value_numeric: float | None = None, value_raw: str | None = None
    ) -> FactMetric:
        """Create a minimal metric for value testing."""
        metric = FactMetric(
            id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            version_id=uuid.uuid4(),
            profile_id=uuid.uuid4(),
            level_id=uuid.uuid4(),
            extraction_run_id=uuid.uuid4(),
            metric_name="test",
            value_numeric=value_numeric,
            value_raw=value_raw,
            certainty=FactCertainty.DEFINITE,
            source_reliability=SourceReliability.OFFICIAL,
        )
        return metric

    def test_same_numeric_values_no_difference(self):
        """Test same numeric values don't differ."""
        service = QualityAnalysisService.__new__(QualityAnalysisService)
        m1 = self._create_metric(value_numeric=10000000)
        m2 = self._create_metric(value_numeric=10000000)

        assert service._values_differ(m1, m2) is False

    def test_significantly_different_values(self):
        """Test significantly different values detected."""
        service = QualityAnalysisService.__new__(QualityAnalysisService)
        m1 = self._create_metric(value_numeric=10000000)
        m2 = self._create_metric(value_numeric=15000000)  # 50% difference

        assert service._values_differ(m1, m2) is True

    def test_small_difference_no_conflict(self):
        """Test small difference (< 1%) doesn't trigger conflict."""
        service = QualityAnalysisService.__new__(QualityAnalysisService)
        m1 = self._create_metric(value_numeric=10000000)
        m2 = self._create_metric(value_numeric=10050000)  # 0.5% difference

        assert service._values_differ(m1, m2) is False

    def test_both_zero_no_difference(self):
        """Test both zero values don't differ."""
        service = QualityAnalysisService.__new__(QualityAnalysisService)
        m1 = self._create_metric(value_numeric=0)
        m2 = self._create_metric(value_numeric=0)

        assert service._values_differ(m1, m2) is False

    def test_one_zero_one_nonzero_differs(self):
        """Test zero vs nonzero values differ."""
        service = QualityAnalysisService.__new__(QualityAnalysisService)
        m1 = self._create_metric(value_numeric=0)
        m2 = self._create_metric(value_numeric=10000000)

        assert service._values_differ(m1, m2) is True

    def test_raw_value_comparison_when_numeric_missing(self):
        """Test raw value comparison when numeric is missing."""
        service = QualityAnalysisService.__new__(QualityAnalysisService)
        m1 = self._create_metric(value_raw="$10M")
        m2 = self._create_metric(value_raw="$15M")

        assert service._values_differ(m1, m2) is True

    def test_same_raw_values_no_difference(self):
        """Test same raw values don't differ."""
        service = QualityAnalysisService.__new__(QualityAnalysisService)
        m1 = self._create_metric(value_raw="$10M")
        m2 = self._create_metric(value_raw="$10M")

        assert service._values_differ(m1, m2) is False
