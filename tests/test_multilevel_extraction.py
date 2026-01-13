"""Tests for multi-level extraction system."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from evidence_repository.extraction.vocabularies import (
    GeneralVocabulary,
    VCVocabulary,
    PharmaVocabulary,
    InsuranceVocabulary,
    get_vocabulary,
    get_vocabulary_registry,
)
from evidence_repository.extraction.vocabularies.base import (
    MetricDefinition,
    ClaimPredicate,
    RiskCategory,
)
from evidence_repository.extraction.multilevel.schemas import (
    ExtractedFactClaim,
    ExtractedFactMetric,
    ExtractedFactConstraint,
    ExtractedFactRisk,
    ExtractedQualityConflict,
    ExtractedQualityQuestion,
    MultiLevelExtractionResult,
)
from evidence_repository.extraction.multilevel.prompts import (
    build_system_prompt,
    build_user_prompt,
)


class TestVocabularies:
    """Tests for vocabulary implementations."""

    def test_general_vocabulary_properties(self):
        """Test GeneralVocabulary properties."""
        vocab = GeneralVocabulary()
        assert vocab.profile_code == "general"
        assert vocab.profile_name == "General"

    def test_vc_vocabulary_properties(self):
        """Test VCVocabulary properties."""
        vocab = VCVocabulary()
        assert vocab.profile_code == "vc"
        assert vocab.profile_name == "Venture Capital"

    def test_pharma_vocabulary_properties(self):
        """Test PharmaVocabulary properties."""
        vocab = PharmaVocabulary()
        assert vocab.profile_code == "pharma"
        assert vocab.profile_name == "Pharmaceutical/Life Sciences"

    def test_insurance_vocabulary_properties(self):
        """Test InsuranceVocabulary properties."""
        vocab = InsuranceVocabulary()
        assert vocab.profile_code == "insurance"
        assert vocab.profile_name == "Insurance"

    def test_vc_vocabulary_metrics_by_level(self):
        """Test VCVocabulary returns correct metrics per level."""
        vocab = VCVocabulary()

        # L1 metrics
        l1_metrics = vocab.get_metrics(level=1)
        l1_names = [m.name for m in l1_metrics]
        assert "arr" in l1_names
        assert "mrr" in l1_names
        assert "burn" in l1_names
        assert "runway" in l1_names
        assert "cash" in l1_names
        assert "headcount" in l1_names
        # L2+ metrics should not be in L1
        assert "cac" not in l1_names  # L3 metric

        # L2 metrics include L1 + L2
        l2_metrics = vocab.get_metrics(level=2)
        l2_names = [m.name for m in l2_metrics]
        assert "arr" in l2_names  # L1
        assert "nrr" in l2_names  # L2
        assert "churn" in l2_names  # L2
        assert "cac" not in l2_names  # L3

        # L3 metrics include L1 + L2 + L3
        l3_metrics = vocab.get_metrics(level=3)
        l3_names = [m.name for m in l3_metrics]
        assert "cac" in l3_names  # L3
        assert "ltv" in l3_names  # L3
        assert "burn_multiple" not in l3_names  # L4

        # L4 metrics include all
        l4_metrics = vocab.get_metrics(level=4)
        l4_names = [m.name for m in l4_metrics]
        assert "burn_multiple" in l4_names  # L4
        assert "rule_of_40" in l4_names  # L4

    def test_vc_vocabulary_claims_by_level(self):
        """Test VCVocabulary returns correct claims per level."""
        vocab = VCVocabulary()

        l1_claims = vocab.get_claim_predicates(level=1)
        l1_names = [c.name for c in l1_claims]
        assert "has_soc2" in l1_names
        assert "is_iso27001" in l1_names
        assert "is_gdpr_compliant" in l1_names

        l2_claims = vocab.get_claim_predicates(level=2)
        l2_names = [c.name for c in l2_claims]
        assert "owns_ip" in l2_names  # L2
        assert "raised_funding" in l2_names  # L2

    def test_vc_vocabulary_risks_by_level(self):
        """Test VCVocabulary returns correct risks per level."""
        vocab = VCVocabulary()

        # L1 should have no risks
        l1_risks = vocab.get_risk_categories(level=1)
        assert len(l1_risks) == 0

        # L2 should have risks
        l2_risks = vocab.get_risk_categories(level=2)
        l2_names = [r.name for r in l2_risks]
        assert "runway_risk" in l2_names
        assert "customer_concentration" in l2_names
        assert "key_person_risk" in l2_names

    def test_vocabulary_get_metric_by_name(self):
        """Test vocabulary metric lookup by name or alias."""
        vocab = VCVocabulary()

        # By canonical name
        metric = vocab.get_metric_by_name("arr")
        assert metric is not None
        assert metric.name == "arr"

        # By alias
        metric = vocab.get_metric_by_name("annual_recurring_revenue")
        assert metric is not None
        assert metric.name == "arr"

        # Unknown metric
        metric = vocab.get_metric_by_name("nonexistent")
        assert metric is None

    def test_vocabulary_registry(self):
        """Test vocabulary registry singleton."""
        registry = get_vocabulary_registry()
        assert registry is not None

        # Should have all profiles
        profiles = registry.list_profiles()
        assert "general" in profiles
        assert "vc" in profiles
        assert "pharma" in profiles
        assert "insurance" in profiles

    def test_get_vocabulary_function(self):
        """Test get_vocabulary convenience function."""
        vocab = get_vocabulary("vc")
        assert vocab.profile_code == "vc"

        # Unknown profile falls back to general
        vocab = get_vocabulary("unknown")
        assert vocab.profile_code == "general"

    def test_extraction_prompt_context(self):
        """Test vocabulary generates prompt context."""
        vocab = VCVocabulary()
        context = vocab.get_extraction_prompt_context(level=2)

        assert context["profile"] == "vc"
        assert context["profile_name"] == "Venture Capital"
        assert context["level"] == 2
        assert len(context["metrics"]) > 0
        assert len(context["claim_predicates"]) > 0
        assert len(context["risk_categories"]) > 0  # L2 has risks


class TestPrompts:
    """Tests for prompt generation."""

    def test_build_system_prompt(self):
        """Test system prompt generation."""
        vocab = VCVocabulary()
        context = vocab.get_extraction_prompt_context(level=2)
        prompt = build_system_prompt(context, level=2)

        # Should contain profile info
        assert "Venture Capital" in prompt

        # Should contain metrics
        assert "arr" in prompt.lower()
        assert "mrr" in prompt.lower()

        # Should contain claims
        assert "soc2" in prompt.lower()

        # Should contain level instructions
        assert "Level 2" in prompt

    def test_build_user_prompt(self):
        """Test user prompt generation."""
        prompt = build_user_prompt(
            document_text="Sample document content with ARR of $10M.",
            spans=None,
            previous_extraction=None,
        )

        assert "Sample document content" in prompt
        assert "Document Content" in prompt

    def test_build_user_prompt_with_spans(self):
        """Test user prompt with span references."""
        spans = [
            {"id": "span-1", "page": 1, "type": "text"},
            {"id": "span-2", "page": 2, "type": "table"},
        ]
        prompt = build_user_prompt(
            document_text="Sample content",
            spans=spans,
        )

        assert "span-1" in prompt
        assert "span-2" in prompt
        assert "Span References" in prompt

    def test_build_user_prompt_with_previous_extraction(self):
        """Test user prompt with previous extraction context."""
        previous = {
            "claims": [{"subject": {"type": "company"}, "predicate": "has_soc2"}],
            "metrics": [{"metric_name": "arr", "value_numeric": 10000000}],
        }
        prompt = build_user_prompt(
            document_text="Sample content",
            previous_extraction=previous,
        )

        assert "Previous Extraction" in prompt
        assert "has_soc2" in prompt
        assert "arr" in prompt


class TestExtractionSchemas:
    """Tests for extraction result schemas."""

    def test_extracted_fact_claim_schema(self):
        """Test ExtractedFactClaim schema."""
        claim = ExtractedFactClaim(
            subject={"type": "company", "name": "Acme Corp"},
            predicate="has_soc2",
            object={"type": "certification", "name": "SOC2 Type II"},
            claim_type="compliance",
            time_scope={"period": "2024"},
            certainty="definite",
            source_reliability="audited",
            span_refs=["span-1"],
            evidence_quote="Acme Corp has SOC2 Type II certification.",
            extraction_confidence=0.95,
        )

        assert claim.subject["name"] == "Acme Corp"
        assert claim.predicate == "has_soc2"
        assert claim.certainty == "definite"

    def test_extracted_fact_metric_schema(self):
        """Test ExtractedFactMetric schema."""
        from datetime import date

        metric = ExtractedFactMetric(
            entity_id="acme-corp",
            entity_type="company",
            metric_name="arr",
            metric_category="revenue",
            value_numeric=10000000.0,
            value_raw="$10M",
            unit="USD",
            currency="USD",
            period_start=date(2024, 1, 1),
            period_end=date(2024, 12, 31),
            period_type="annual",
            certainty="definite",
            source_reliability="official",
            span_refs=["span-2"],
            extraction_confidence=0.98,
        )

        assert metric.metric_name == "arr"
        assert metric.value_numeric == 10000000.0
        assert metric.currency == "USD"

    def test_extracted_fact_constraint_schema(self):
        """Test ExtractedFactConstraint schema."""
        constraint = ExtractedFactConstraint(
            constraint_type="definition",
            applies_to={"metric_ids": ["arr"]},
            statement="ARR is calculated as MRR × 12",
            certainty="definite",
            span_refs=["span-3"],
        )

        assert constraint.constraint_type == "definition"
        assert "arr" in str(constraint.applies_to)

    def test_extracted_fact_risk_schema(self):
        """Test ExtractedFactRisk schema."""
        risk = ExtractedFactRisk(
            risk_type="customer_concentration",
            risk_category="financial",
            severity="medium",
            statement="Top customer represents 40% of revenue",
            rationale="Concentration above 20% threshold",
            related_claims=[],
            related_metrics=["revenue"],
            span_refs=["span-4"],
            extraction_confidence=0.85,
        )

        assert risk.risk_type == "customer_concentration"
        assert risk.severity == "medium"

    def test_multi_level_extraction_result_schema(self):
        """Test MultiLevelExtractionResult schema."""
        result = MultiLevelExtractionResult(
            profile_code="vc",
            level=2,
            claims=[
                ExtractedFactClaim(
                    subject={"type": "company"},
                    predicate="has_soc2",
                    object={"type": "certification"},
                    claim_type="compliance",
                )
            ],
            metrics=[
                ExtractedFactMetric(
                    metric_name="arr",
                    value_numeric=10000000.0,
                )
            ],
            constraints=[],
            risks=[],
            conflicts=[],
            open_questions=[],
        )

        assert result.profile_code == "vc"
        assert result.level == 2
        assert len(result.claims) == 1
        assert len(result.metrics) == 1


class TestVocabularyCompleteness:
    """Tests to verify vocabulary completeness for each profile."""

    def test_vc_vocabulary_has_critical_metrics(self):
        """Test VC vocabulary has all Juris-critical metrics."""
        vocab = VCVocabulary()
        all_metrics = vocab.get_metrics(level=4)
        metric_names = [m.name for m in all_metrics]

        critical_metrics = [
            "arr", "mrr", "revenue", "burn", "runway", "cash",
            "headcount", "churn", "nrr", "gross_margin",
            "cac", "ltv", "growth_rate",
        ]

        for metric in critical_metrics:
            assert metric in metric_names, f"Missing critical metric: {metric}"

    def test_vc_vocabulary_has_critical_claims(self):
        """Test VC vocabulary has all Juris-critical claims."""
        vocab = VCVocabulary()
        all_claims = vocab.get_claim_predicates(level=4)
        claim_names = [c.name for c in all_claims]

        critical_claims = [
            "has_soc2", "is_iso27001", "is_gdpr_compliant",
            "owns_ip", "has_security_incident",
        ]

        for claim in critical_claims:
            assert claim in claim_names, f"Missing critical claim: {claim}"

    def test_pharma_vocabulary_has_critical_metrics(self):
        """Test Pharma vocabulary has critical metrics."""
        vocab = PharmaVocabulary()
        all_metrics = vocab.get_metrics(level=4)
        metric_names = [m.name for m in all_metrics]

        critical_metrics = [
            "revenue", "rd_spend", "pipeline_count", "cash", "burn",
            "clinical_trial_count", "phase1_count", "phase2_count", "phase3_count",
        ]

        for metric in critical_metrics:
            assert metric in metric_names, f"Missing critical metric: {metric}"

    def test_insurance_vocabulary_has_critical_metrics(self):
        """Test Insurance vocabulary has critical metrics."""
        vocab = InsuranceVocabulary()
        all_metrics = vocab.get_metrics(level=4)
        metric_names = [m.name for m in all_metrics]

        critical_metrics = [
            "revenue", "net_income", "assets", "policyholder_surplus",
            "combined_ratio", "loss_ratio", "expense_ratio", "rbc_ratio",
        ]

        for metric in critical_metrics:
            assert metric in metric_names, f"Missing critical metric: {metric}"


class TestMetricDefinitions:
    """Tests for metric definition completeness."""

    def test_metric_definitions_have_required_fields(self):
        """Test all metric definitions have required fields."""
        for vocab_cls in [GeneralVocabulary, VCVocabulary, PharmaVocabulary, InsuranceVocabulary]:
            vocab = vocab_cls()
            for metric in vocab.get_metrics(level=4):
                assert metric.name, f"Metric missing name in {vocab.profile_code}"
                assert metric.display_name, f"Metric {metric.name} missing display_name"
                assert metric.description, f"Metric {metric.name} missing description"
                assert metric.unit_type, f"Metric {metric.name} missing unit_type"
                assert metric.required_level >= 1, f"Metric {metric.name} has invalid level"

    def test_claim_predicates_have_required_fields(self):
        """Test all claim predicates have required fields."""
        for vocab_cls in [GeneralVocabulary, VCVocabulary, PharmaVocabulary, InsuranceVocabulary]:
            vocab = vocab_cls()
            for predicate in vocab.get_claim_predicates(level=4):
                assert predicate.name, f"Predicate missing name in {vocab.profile_code}"
                assert predicate.display_name, f"Predicate {predicate.name} missing display_name"
                assert predicate.description, f"Predicate {predicate.name} missing description"
                assert len(predicate.subject_types) > 0, f"Predicate {predicate.name} has no subject types"
                assert len(predicate.object_types) > 0, f"Predicate {predicate.name} has no object types"

    def test_risk_categories_have_required_fields(self):
        """Test all risk categories have required fields."""
        for vocab_cls in [GeneralVocabulary, VCVocabulary, PharmaVocabulary, InsuranceVocabulary]:
            vocab = vocab_cls()
            for risk in vocab.get_risk_categories(level=4):
                assert risk.name, f"Risk missing name in {vocab.profile_code}"
                assert risk.display_name, f"Risk {risk.name} missing display_name"
                assert risk.description, f"Risk {risk.name} missing description"
                assert len(risk.indicators) > 0, f"Risk {risk.name} has no indicators"
