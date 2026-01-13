"""Tests for Juris-AGI evidence pack endpoints."""

import uuid
from datetime import datetime

import pytest

from evidence_repository.schemas.evidence import (
    JurisClaimSummary,
    JurisConflictSummary,
    JurisDocumentSummary,
    JurisEvidencePackCreate,
    JurisEvidencePackResponse,
    JurisMetricSummary,
    JurisOpenQuestionSummary,
    JurisQualitySummary,
    JurisSpanSummary,
)


class TestJurisEvidencePackSchemas:
    """Tests for Juris-AGI evidence pack Pydantic schemas."""

    def test_juris_document_summary_creation(self):
        """Test creating a JurisDocumentSummary."""
        doc = JurisDocumentSummary(
            id=uuid.uuid4(),
            filename="financial_report.pdf",
            content_type="application/pdf",
            version_id=uuid.uuid4(),
            version_number=1,
            extraction_status="completed",
        )

        assert doc.filename == "financial_report.pdf"
        assert doc.content_type == "application/pdf"
        assert doc.version_number == 1

    def test_juris_span_summary_creation(self):
        """Test creating a JurisSpanSummary."""
        span = JurisSpanSummary(
            id=uuid.uuid4(),
            document_version_id=uuid.uuid4(),
            document_filename="report.pdf",
            span_type="text",
            text_content="The company reported ARR of $10M.",
            locator={"type": "pdf", "page": 5, "bbox": {"x1": 100, "y1": 200, "x2": 500, "y2": 250}},
        )

        assert span.span_type == "text"
        assert "ARR" in span.text_content
        assert span.locator["type"] == "pdf"

    def test_juris_claim_summary_creation(self):
        """Test creating a JurisClaimSummary."""
        claim = JurisClaimSummary(
            id=uuid.uuid4(),
            span_id=uuid.uuid4(),
            claim_text="Company has SOC2 Type II certification.",
            claim_type="soc2",
            certainty="definite",
            reliability="verified",
            time_scope="2024",
            extraction_confidence=0.95,
        )

        assert claim.claim_type == "soc2"
        assert claim.certainty == "definite"
        assert claim.extraction_confidence == 0.95

    def test_juris_metric_summary_creation(self):
        """Test creating a JurisMetricSummary."""
        metric = JurisMetricSummary(
            id=uuid.uuid4(),
            span_id=uuid.uuid4(),
            metric_name="ARR",
            metric_type="arr",
            metric_value="$10M",
            numeric_value=10000000.0,
            unit="USD",
            time_scope="FY2024",
            certainty="definite",
            reliability="official",
        )

        assert metric.metric_name == "ARR"
        assert metric.numeric_value == 10000000.0
        assert metric.unit == "USD"

    def test_juris_conflict_summary_creation(self):
        """Test creating a JurisConflictSummary."""
        conflict = JurisConflictSummary(
            conflict_type="metric",
            severity="high",
            reason="Conflicting ARR values: $10M vs $8M for same period",
            affected_ids=[str(uuid.uuid4()), str(uuid.uuid4())],
            details={
                "metric_name": "ARR",
                "values": [10000000, 8000000],
            },
        )

        assert conflict.conflict_type == "metric"
        assert conflict.severity == "high"
        assert len(conflict.affected_ids) == 2

    def test_juris_open_question_creation(self):
        """Test creating a JurisOpenQuestionSummary."""
        question = JurisOpenQuestionSummary(
            category="missing_data",
            question="What is the currency for 'Revenue'?",
            context="Revenue metric has value 5000000 but no currency specified.",
            related_ids=[str(uuid.uuid4())],
        )

        assert question.category == "missing_data"
        assert "currency" in question.question.lower()

    def test_juris_quality_summary_creation(self):
        """Test creating a JurisQualitySummary."""
        summary = JurisQualitySummary(
            total_conflicts=5,
            critical_conflicts=1,
            high_conflicts=2,
            total_open_questions=3,
        )

        assert summary.total_conflicts == 5
        assert summary.critical_conflicts == 1

    def test_juris_evidence_pack_create_schema(self):
        """Test JurisEvidencePackCreate schema."""
        pack_create = JurisEvidencePackCreate(
            name="Due Diligence Evidence Pack",
            description="Evidence for Series B due diligence",
            span_ids=[uuid.uuid4(), uuid.uuid4()],
            claim_ids=[uuid.uuid4()],
            metric_ids=[uuid.uuid4(), uuid.uuid4(), uuid.uuid4()],
            include_quality_analysis=True,
            metadata={"deal_id": "series-b-2024"},
        )

        assert pack_create.name == "Due Diligence Evidence Pack"
        assert len(pack_create.span_ids) == 2
        assert len(pack_create.claim_ids) == 1
        assert len(pack_create.metric_ids) == 3
        assert pack_create.include_quality_analysis is True

    def test_juris_evidence_pack_create_defaults(self):
        """Test JurisEvidencePackCreate default values."""
        pack_create = JurisEvidencePackCreate(name="Minimal Pack")

        assert pack_create.description is None
        assert pack_create.span_ids == []
        assert pack_create.claim_ids == []
        assert pack_create.metric_ids == []
        assert pack_create.include_quality_analysis is True
        assert pack_create.metadata == {}

    def test_juris_evidence_pack_response_full(self):
        """Test JurisEvidencePackResponse with all fields populated."""
        now = datetime.utcnow()
        pack_id = uuid.uuid4()
        project_id = uuid.uuid4()

        # Create document summary
        doc = JurisDocumentSummary(
            id=uuid.uuid4(),
            filename="report.pdf",
            content_type="application/pdf",
            version_id=uuid.uuid4(),
            version_number=1,
            extraction_status="completed",
        )

        # Create span summary
        span = JurisSpanSummary(
            id=uuid.uuid4(),
            document_version_id=doc.version_id,
            document_filename=doc.filename,
            span_type="text",
            text_content="Sample evidence text",
            locator={"type": "text", "offset_start": 0, "offset_end": 100},
        )

        # Create claim summary
        claim = JurisClaimSummary(
            id=uuid.uuid4(),
            span_id=span.id,
            claim_text="Test claim",
            claim_type="compliance",
            certainty="probable",
            reliability="official",
        )

        # Create metric summary
        metric = JurisMetricSummary(
            id=uuid.uuid4(),
            span_id=span.id,
            metric_name="Revenue",
            metric_type="revenue",
            metric_value="$5M",
            numeric_value=5000000.0,
            unit="USD",
            certainty="definite",
            reliability="official",
        )

        # Create conflict
        conflict = JurisConflictSummary(
            conflict_type="metric",
            severity="medium",
            reason="Test conflict",
            affected_ids=[str(metric.id)],
        )

        # Create open question
        question = JurisOpenQuestionSummary(
            category="temporal",
            question="Is the data current?",
            context="Data is 14 months old",
            related_ids=[str(metric.id)],
        )

        # Create quality summary
        quality = JurisQualitySummary(
            total_conflicts=1,
            critical_conflicts=0,
            high_conflicts=0,
            total_open_questions=1,
        )

        # Create full response
        response = JurisEvidencePackResponse(
            id=pack_id,
            project_id=project_id,
            name="Full Test Pack",
            description="A comprehensive test pack",
            created_by="test-user",
            created_at=now,
            updated_at=now,
            documents=[doc],
            spans=[span],
            claims=[claim],
            metrics=[metric],
            conflicts=[conflict],
            open_questions=[question],
            quality_summary=quality,
            document_count=1,
            span_count=1,
            claim_count=1,
            metric_count=1,
            metadata={"test": True},
        )

        assert response.id == pack_id
        assert response.project_id == project_id
        assert response.name == "Full Test Pack"
        assert len(response.documents) == 1
        assert len(response.spans) == 1
        assert len(response.claims) == 1
        assert len(response.metrics) == 1
        assert len(response.conflicts) == 1
        assert len(response.open_questions) == 1
        assert response.quality_summary is not None
        assert response.document_count == 1
        assert response.metadata == {"test": True}

    def test_juris_evidence_pack_response_empty(self):
        """Test JurisEvidencePackResponse with minimal/empty fields."""
        now = datetime.utcnow()

        response = JurisEvidencePackResponse(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            name="Empty Pack",
            created_at=now,
            updated_at=now,
        )

        assert response.description is None
        assert response.created_by is None
        assert response.documents == []
        assert response.spans == []
        assert response.claims == []
        assert response.metrics == []
        assert response.conflicts == []
        assert response.open_questions == []
        assert response.quality_summary is None
        assert response.document_count == 0


class TestJurisEvidencePackIntegration:
    """Integration tests for Juris-AGI evidence pack functionality."""

    def test_pack_contains_all_required_juris_fields(self):
        """Test that response schema has all fields required by Juris-AGI."""
        # These are the fields explicitly requested:
        # - documents
        # - spans
        # - claims
        # - metrics
        # - conflicts
        # - open_questions
        required_fields = {
            "documents",
            "spans",
            "claims",
            "metrics",
            "conflicts",
            "open_questions",
        }

        response_fields = set(JurisEvidencePackResponse.model_fields.keys())

        assert required_fields.issubset(response_fields), (
            f"Missing required fields: {required_fields - response_fields}"
        )

    def test_conflict_types_cover_requirements(self):
        """Test that conflict types cover both metric and claim conflicts."""
        # Requirements:
        # - Same metric + overlapping period + different values
        # - Same boolean claim with different values

        metric_conflict = JurisConflictSummary(
            conflict_type="metric",
            severity="critical",
            reason="Same metric, overlapping period, different values",
            affected_ids=["metric-1", "metric-2"],
            details={"metric_name": "ARR", "values": [10000000, 8000000]},
        )

        claim_conflict = JurisConflictSummary(
            conflict_type="claim",
            severity="high",
            reason="Same boolean claim with contradictory values",
            affected_ids=["claim-1", "claim-2"],
            details={"predicate": "has_soc2", "values": [True, False]},
        )

        assert metric_conflict.conflict_type == "metric"
        assert claim_conflict.conflict_type == "claim"

    def test_open_question_categories_cover_requirements(self):
        """Test that open question categories cover requirements."""
        # Requirements:
        # - Missing units, currency, periods
        # - Financials older than 12 months

        missing_unit = JurisOpenQuestionSummary(
            category="missing_data",
            question="What is the unit for 'Headcount'?",
            context="Headcount metric has value 150 but no unit specified.",
        )

        missing_currency = JurisOpenQuestionSummary(
            category="missing_data",
            question="What is the currency for 'Revenue'?",
            context="Revenue appears monetary but no currency specified.",
        )

        stale_data = JurisOpenQuestionSummary(
            category="temporal",
            question="Is the 'ARR' value still current?",
            context="Financial metric 'ARR' is 14 months old.",
        )

        assert missing_unit.category == "missing_data"
        assert missing_currency.category == "missing_data"
        assert stale_data.category == "temporal"

    def test_response_serialization(self):
        """Test that the response can be serialized to JSON."""
        now = datetime.utcnow()

        response = JurisEvidencePackResponse(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            name="Serialization Test",
            created_at=now,
            updated_at=now,
            documents=[
                JurisDocumentSummary(
                    id=uuid.uuid4(),
                    filename="test.pdf",
                    version_id=uuid.uuid4(),
                    version_number=1,
                )
            ],
        )

        # This should not raise an exception
        json_data = response.model_dump()

        assert json_data["name"] == "Serialization Test"
        assert len(json_data["documents"]) == 1
        assert json_data["documents"][0]["filename"] == "test.pdf"

    def test_response_json_mode(self):
        """Test that the response can be converted to JSON string."""
        now = datetime.utcnow()

        response = JurisEvidencePackResponse(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            name="JSON Mode Test",
            created_at=now,
            updated_at=now,
        )

        # This should not raise an exception
        json_str = response.model_dump_json()

        assert "JSON Mode Test" in json_str
        assert "documents" in json_str
        assert "conflicts" in json_str
        assert "open_questions" in json_str
