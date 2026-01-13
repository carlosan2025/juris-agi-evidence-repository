"""Tests for structured extraction service."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from evidence_repository.extraction.structured_extraction import (
    ExtractedClaim,
    ExtractedMetric,
    ExtractionResult,
    ExtractionStats,
    StructuredExtractionService,
    SYSTEM_PROMPT,
    USER_PROMPT_TEMPLATE,
)
from evidence_repository.models.evidence import (
    Certainty,
    ClaimType,
    MetricType,
    Reliability,
    SpanType,
)


class TestExtractionSchemas:
    """Tests for extraction output schemas."""

    def test_extracted_metric_schema(self):
        """Test ExtractedMetric schema validation."""
        metric = ExtractedMetric(
            metric_type="arr",
            metric_name="Annual Recurring Revenue",
            metric_value="$5.2M",
            numeric_value=5200000.0,
            unit="USD",
            time_scope="Q4 2024",
            certainty="definite",
            reliability="official",
            extraction_confidence=0.95,
            evidence_quote="ARR reached $5.2M in Q4 2024",
        )

        assert metric.metric_type == "arr"
        assert metric.numeric_value == 5200000.0
        assert metric.extraction_confidence == 0.95

    def test_extracted_claim_schema(self):
        """Test ExtractedClaim schema validation."""
        claim = ExtractedClaim(
            claim_type="soc2",
            claim_text="Company achieved SOC2 Type II certification",
            time_scope="December 2024",
            certainty="definite",
            reliability="verified",
            extraction_confidence=0.98,
            evidence_quote="We completed our SOC2 Type II audit in December 2024",
        )

        assert claim.claim_type == "soc2"
        assert claim.certainty == "definite"
        assert claim.extraction_confidence == 0.98

    def test_extraction_result_schema(self):
        """Test ExtractionResult with multiple items."""
        result = ExtractionResult(
            metrics=[
                ExtractedMetric(
                    metric_type="arr",
                    metric_name="ARR",
                    metric_value="$5M",
                    extraction_confidence=0.9,
                    evidence_quote="ARR is $5M",
                ),
            ],
            claims=[
                ExtractedClaim(
                    claim_type="soc2",
                    claim_text="SOC2 certified",
                    extraction_confidence=0.95,
                    evidence_quote="SOC2 certified",
                ),
            ],
        )

        assert len(result.metrics) == 1
        assert len(result.claims) == 1


class TestEnumTypes:
    """Tests for enum type validation."""

    def test_metric_types(self):
        """Test all metric types are valid."""
        assert MetricType.ARR.value == "arr"
        assert MetricType.MRR.value == "mrr"
        assert MetricType.REVENUE.value == "revenue"
        assert MetricType.BURN.value == "burn"
        assert MetricType.RUNWAY.value == "runway"
        assert MetricType.CASH.value == "cash"
        assert MetricType.HEADCOUNT.value == "headcount"
        assert MetricType.CHURN.value == "churn"
        assert MetricType.NRR.value == "nrr"

    def test_claim_types(self):
        """Test all claim types are valid."""
        assert ClaimType.SOC2.value == "soc2"
        assert ClaimType.ISO27001.value == "iso27001"
        assert ClaimType.GDPR.value == "gdpr"
        assert ClaimType.HIPAA.value == "hipaa"
        assert ClaimType.IP_OWNERSHIP.value == "ip_ownership"
        assert ClaimType.SECURITY_INCIDENT.value == "security_incident"

    def test_certainty_levels(self):
        """Test certainty enum values."""
        assert Certainty.DEFINITE.value == "definite"
        assert Certainty.PROBABLE.value == "probable"
        assert Certainty.POSSIBLE.value == "possible"
        assert Certainty.SPECULATIVE.value == "speculative"

    def test_reliability_levels(self):
        """Test reliability enum values."""
        assert Reliability.VERIFIED.value == "verified"
        assert Reliability.OFFICIAL.value == "official"
        assert Reliability.INTERNAL.value == "internal"
        assert Reliability.THIRD_PARTY.value == "third_party"
        assert Reliability.UNKNOWN.value == "unknown"


class TestExtractionPrompts:
    """Tests for extraction prompts."""

    def test_system_prompt_includes_metrics(self):
        """Test system prompt mentions all Juris-critical metrics."""
        assert "ARR" in SYSTEM_PROMPT
        assert "Revenue" in SYSTEM_PROMPT
        assert "Burn" in SYSTEM_PROMPT
        assert "Runway" in SYSTEM_PROMPT
        assert "Cash" in SYSTEM_PROMPT
        assert "Headcount" in SYSTEM_PROMPT
        assert "Churn" in SYSTEM_PROMPT
        assert "NRR" in SYSTEM_PROMPT

    def test_system_prompt_includes_claims(self):
        """Test system prompt mentions all Juris-critical claims."""
        assert "SOC2" in SYSTEM_PROMPT
        assert "ISO27001" in SYSTEM_PROMPT
        assert "GDPR" in SYSTEM_PROMPT
        assert "HIPAA" in SYSTEM_PROMPT
        assert "IP ownership" in SYSTEM_PROMPT
        assert "Security incident" in SYSTEM_PROMPT

    def test_user_prompt_template_placeholder(self):
        """Test user prompt has text placeholder."""
        assert "{text}" in USER_PROMPT_TEMPLATE

    def test_user_prompt_template_format(self):
        """Test user prompt can be formatted."""
        formatted = USER_PROMPT_TEMPLATE.format(text="Sample text content")
        assert "Sample text content" in formatted


class TestExtractionStats:
    """Tests for ExtractionStats dataclass."""

    def test_default_values(self):
        """Test default values are zero."""
        stats = ExtractionStats()
        assert stats.spans_processed == 0
        assert stats.metrics_extracted == 0
        assert stats.claims_extracted == 0
        assert stats.errors == 0
        assert stats.tokens_used == 0

    def test_custom_values(self):
        """Test setting custom values."""
        stats = ExtractionStats(
            spans_processed=10,
            metrics_extracted=5,
            claims_extracted=3,
            errors=1,
            tokens_used=1500,
        )
        assert stats.spans_processed == 10
        assert stats.metrics_extracted == 5


class TestStructuredExtractionService:
    """Tests for StructuredExtractionService."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database session."""
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_db):
        """Create service with mocked dependencies."""
        return StructuredExtractionService(
            db=mock_db,
            api_key="test-key",
            model="gpt-4o",
        )

    def test_extractable_span_types(self, service):
        """Test extractable span types are correct."""
        expected = {SpanType.TEXT, SpanType.HEADING, SpanType.TABLE}
        assert service.EXTRACTABLE_SPAN_TYPES == expected

    def test_service_initialization(self, service):
        """Test service initializes with correct settings."""
        assert service.model == "gpt-4o"
        assert service.max_tokens == 4096
        assert service.api_key == "test-key"

    def test_client_property_requires_api_key(self):
        """Test client property raises error without API key."""
        mock_db = AsyncMock()
        service = StructuredExtractionService(db=mock_db, api_key=None)

        # Mock get_settings to return None for API key
        with patch("evidence_repository.extraction.structured_extraction.get_settings") as mock_settings:
            mock_settings.return_value.openai_api_key = None
            service = StructuredExtractionService(db=mock_db)

            with pytest.raises(ValueError, match="API key not configured"):
                _ = service.client


class TestTaskFunctions:
    """Tests for worker task functions."""

    def test_task_extract_structured_exists(self):
        """Test task_extract_structured function exists."""
        from evidence_repository.queue.tasks import task_extract_structured
        import inspect

        sig = inspect.signature(task_extract_structured)
        params = list(sig.parameters.keys())

        assert "document_id" in params
        assert "project_id" in params
        assert "version_id" in params
        assert "reprocess" in params

    def test_task_extract_structured_batch_exists(self):
        """Test task_extract_structured_batch function exists."""
        from evidence_repository.queue.tasks import task_extract_structured_batch
        import inspect

        sig = inspect.signature(task_extract_structured_batch)
        params = list(sig.parameters.keys())

        assert "document_ids" in params
        assert "project_id" in params
        assert "reprocess" in params


class TestMetricTypeMapping:
    """Tests for metric type string to enum mapping."""

    def test_valid_metric_types(self):
        """Test valid metric type strings map correctly."""
        valid_types = [
            "arr", "mrr", "revenue", "burn", "runway",
            "cash", "headcount", "churn", "nrr", "gross_margin",
            "cac", "ltv", "ebitda", "growth_rate", "other"
        ]

        for type_str in valid_types:
            metric_type = MetricType(type_str)
            assert metric_type.value == type_str

    def test_invalid_metric_type_raises(self):
        """Test invalid metric type raises ValueError."""
        with pytest.raises(ValueError):
            MetricType("invalid_type")


class TestClaimTypeMapping:
    """Tests for claim type string to enum mapping."""

    def test_valid_claim_types(self):
        """Test valid claim type strings map correctly."""
        valid_types = [
            "soc2", "iso27001", "gdpr", "hipaa", "ip_ownership",
            "security_incident", "compliance", "certification",
            "audit", "policy", "other"
        ]

        for type_str in valid_types:
            claim_type = ClaimType(type_str)
            assert claim_type.value == type_str

    def test_invalid_claim_type_raises(self):
        """Test invalid claim type raises ValueError."""
        with pytest.raises(ValueError):
            ClaimType("invalid_type")


class TestExtractionConfidenceValidation:
    """Tests for extraction confidence validation."""

    def test_valid_confidence_values(self):
        """Test valid confidence values (0.0-1.0)."""
        for conf in [0.0, 0.5, 0.95, 1.0]:
            metric = ExtractedMetric(
                metric_type="arr",
                metric_name="ARR",
                metric_value="$1M",
                extraction_confidence=conf,
                evidence_quote="quote",
            )
            assert metric.extraction_confidence == conf

    def test_invalid_confidence_below_zero(self):
        """Test confidence below 0.0 is rejected."""
        with pytest.raises(ValueError):
            ExtractedMetric(
                metric_type="arr",
                metric_name="ARR",
                metric_value="$1M",
                extraction_confidence=-0.1,
                evidence_quote="quote",
            )

    def test_invalid_confidence_above_one(self):
        """Test confidence above 1.0 is rejected."""
        with pytest.raises(ValueError):
            ExtractedMetric(
                metric_type="arr",
                metric_name="ARR",
                metric_value="$1M",
                extraction_confidence=1.5,
                evidence_quote="quote",
            )
