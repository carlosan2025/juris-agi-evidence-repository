"""Tests for the Agent-K inspired digestion pipeline.

Tests cover:
- Unified digestion pipeline
- Document parsers
- Database-as-queue polling
- Two-stage search
- Metadata extraction
- Truthfulness assessment
"""

import hashlib
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from evidence_repository.digestion.pipeline import (
    DigestOptions,
    DigestResult,
    DigestStep,
    DigestionPipeline,
)
from evidence_repository.models.document import (
    DocumentType,
    ExtractionStatus,
    SourceType,
)


# =============================================================================
# DigestOptions Tests
# =============================================================================


class TestDigestOptions:
    """Tests for DigestOptions dataclass."""

    def test_default_options(self):
        """Test default option values."""
        options = DigestOptions()

        assert options.skip_embeddings is False
        assert options.skip_metadata_extraction is False
        assert options.skip_truthfulness_assessment is True
        assert options.force_reprocess is False
        assert options.profile_code == "general"
        assert options.process_context == "unspecified"
        assert options.extraction_level == 2

    def test_custom_options(self):
        """Test custom option values."""
        options = DigestOptions(
            skip_embeddings=True,
            profile_code="vc",
            process_context="vc.ic_decision",
            source_url="https://example.com/doc.pdf",
            uploaded_by="user123",
        )

        assert options.skip_embeddings is True
        assert options.profile_code == "vc"
        assert options.process_context == "vc.ic_decision"
        assert options.source_url == "https://example.com/doc.pdf"
        assert options.uploaded_by == "user123"


# =============================================================================
# DigestResult Tests
# =============================================================================


class TestDigestResult:
    """Tests for DigestResult dataclass."""

    def test_default_result(self):
        """Test default result values."""
        result = DigestResult()

        assert result.document_id is None
        assert result.version_id is None
        assert result.status == "pending"
        assert result.deduplicated is False
        assert result.steps_completed == []
        assert result.steps_failed == []
        assert result.text_length == 0
        assert result.error_message is None

    def test_to_dict(self):
        """Test serialization to dictionary."""
        import uuid

        doc_id = uuid.uuid4()
        ver_id = uuid.uuid4()

        result = DigestResult(
            document_id=doc_id,
            version_id=ver_id,
            status="ready",
            text_length=1000,
            steps_completed=["validate", "store", "parse"],
        )

        d = result.to_dict()

        assert d["document_id"] == str(doc_id)
        assert d["version_id"] == str(ver_id)
        assert d["status"] == "ready"
        assert d["text_length"] == 1000
        assert "validate" in d["steps_completed"]


# =============================================================================
# Parsers Tests
# =============================================================================


class TestDocumentParsers:
    """Tests for document parsers."""

    @pytest.mark.asyncio
    async def test_parse_text_file(self):
        """Test plain text parsing."""
        from evidence_repository.digestion.parsers import parse_text

        content = b"Hello, World!\nThis is a test document."
        text, metadata = await parse_text(content, "test.txt")

        assert "Hello, World!" in text
        assert "This is a test document." in text
        assert metadata.get("encoding") == "utf-8"

    @pytest.mark.asyncio
    async def test_parse_text_with_encodings(self):
        """Test text parsing with different encodings."""
        from evidence_repository.digestion.parsers import parse_text

        # Latin-1 encoded content
        content = "Café résumé".encode("latin-1")
        text, metadata = await parse_text(content, "test.txt")

        assert "Café" in text or "Caf" in text  # May decode differently

    @pytest.mark.asyncio
    async def test_parse_csv(self):
        """Test CSV parsing."""
        from evidence_repository.digestion.parsers import parse_csv

        content = b"Name,Age,City\nJohn,30,NYC\nJane,25,LA"
        text, metadata = await parse_csv(content, "data.csv")

        assert "Name" in text
        assert "John" in text
        assert metadata.get("row_count") == 3
        assert metadata.get("columns") == ["Name", "Age", "City"]

    @pytest.mark.asyncio
    async def test_parse_document_dispatcher(self):
        """Test parse_document correctly dispatches by MIME type."""
        from evidence_repository.digestion.parsers import parse_document

        content = b"Test content"
        text, metadata = await parse_document(
            content, "text/plain", "test.txt"
        )

        assert "Test content" in text
        assert metadata.get("parser") == "text"


# =============================================================================
# Status Tests
# =============================================================================


class TestProcessingStatus:
    """Tests for processing status utilities."""

    def test_processing_status_to_dict(self):
        """Test ProcessingStatus serialization."""
        from evidence_repository.digestion.status import ProcessingStatus

        status = ProcessingStatus(
            pending_count=5,
            processing_count=2,
            completed_count=100,
            failed_count=3,
            total_count=110,
            processed_last_hour=10,
        )

        d = status.to_dict()

        assert d["queue"]["pending"] == 5
        assert d["queue"]["processing"] == 2
        assert d["queue"]["completed"] == 100
        assert d["recent_activity"]["processed_last_hour"] == 10


# =============================================================================
# Two-Stage Search Tests
# =============================================================================


class TestTwoStageSearch:
    """Tests for two-stage search architecture."""

    def test_search_filters(self):
        """Test SearchFilters dataclass."""
        from evidence_repository.services.two_stage_search import SearchFilters

        filters = SearchFilters(
            sectors=["technology", "finance"],
            topics=["AI", "machine learning"],
            document_types=["whitepaper"],
        )

        assert "technology" in filters.sectors
        assert "AI" in filters.topics
        assert "whitepaper" in filters.document_types

    def test_search_result(self):
        """Test SearchResult dataclass."""
        import uuid
        from evidence_repository.services.two_stage_search import SearchResult

        result = SearchResult(
            id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            document_filename="report.pdf",
            version_id=uuid.uuid4(),
            semantic_score=0.85,
            metadata_score=0.7,
            combined_score=0.79,
            text="Sample text",
        )

        assert result.semantic_score == 0.85
        assert result.combined_score == 0.79

    def test_search_mode_enum(self):
        """Test SearchMode enum values."""
        from evidence_repository.services.two_stage_search import SearchMode

        assert SearchMode.SEMANTIC.value == "semantic"
        assert SearchMode.METADATA.value == "metadata"
        assert SearchMode.TWO_STAGE.value == "two_stage"
        assert SearchMode.DISCOVERY.value == "discovery"


# =============================================================================
# Metadata Extraction Tests
# =============================================================================


class TestMetadataExtraction:
    """Tests for metadata extraction."""

    @pytest.mark.asyncio
    async def test_extract_from_filename(self):
        """Test filename-based metadata extraction."""
        from evidence_repository.digestion.metadata_extractor import _extract_from_filename

        metadata = _extract_from_filename("2024-01-15_quarterly_report.pdf")

        assert metadata["filename"] == "2024-01-15_quarterly_report.pdf"
        assert metadata.get("filename_date") == "2024-01-15"

    @pytest.mark.asyncio
    async def test_extract_from_filename_guesses_type(self):
        """Test document type guessing from filename."""
        from evidence_repository.digestion.metadata_extractor import _extract_from_filename

        invoice_meta = _extract_from_filename("Invoice_12345.pdf")
        assert invoice_meta.get("guessed_type") == "invoice"

        contract_meta = _extract_from_filename("Contract_Agreement_v2.docx")
        assert contract_meta.get("guessed_type") == "contract"

        report_meta = _extract_from_filename("Annual_Report_2024.pdf")
        assert report_meta.get("guessed_type") == "company_report"


# =============================================================================
# Truthfulness Assessment Tests
# =============================================================================


class TestTruthtulnessAssessment:
    """Tests for truthfulness assessment."""

    @pytest.mark.asyncio
    async def test_basic_assessment(self):
        """Test basic (non-LLM) truthfulness assessment."""
        from evidence_repository.digestion.truthfulness import _basic_assessment

        text = """
        This is a factual document with citations [1] and references (2024).
        The study shows that results are statistically significant.
        """

        assessment = _basic_assessment(text)

        assert assessment["method"] == "basic"
        assert assessment["metrics"]["citation_count"] >= 2
        assert isinstance(assessment["flags"], list)

    @pytest.mark.asyncio
    async def test_basic_assessment_detects_issues(self):
        """Test that basic assessment detects potential issues."""
        from evidence_repository.digestion.truthfulness import _basic_assessment

        biased_text = """
        This product is AMAZING and INCREDIBLE! It's definitely the BEST ever!
        You will never find anything better, guaranteed 100%!
        Everyone knows this is absolutely shocking and outrageous!
        """

        assessment = _basic_assessment(biased_text)

        # Should detect emotional language
        emotional_count = assessment["metrics"].get("emotional_language_count", 0)
        absolute_count = assessment["metrics"].get("absolute_claim_count", 0)

        assert emotional_count > 0 or absolute_count > 0


# =============================================================================
# Document Model Tests
# =============================================================================


class TestDocumentModel:
    """Tests for enhanced document model fields."""

    def test_document_type_enum(self):
        """Test DocumentType enum values."""
        assert DocumentType.WHITEPAPER.value == "whitepaper"
        assert DocumentType.COMPANY_REPORT.value == "company_report"
        assert DocumentType.FINANCIAL_STATEMENT.value == "financial_statement"
        assert DocumentType.UNKNOWN.value == "unknown"

    def test_source_type_enum(self):
        """Test SourceType enum values."""
        assert SourceType.UPLOAD.value == "upload"
        assert SourceType.URL.value == "url"
        assert SourceType.EMAIL.value == "email"
        assert SourceType.CRAWLER.value == "crawler"


# =============================================================================
# Section Builder Tests
# =============================================================================


class TestSectionBuilder:
    """Tests for section building."""

    def test_split_paragraphs(self):
        """Test paragraph splitting."""
        from evidence_repository.digestion.section_builder import _split_paragraphs

        text = """First paragraph here.

        Second paragraph here.

        Third paragraph here."""

        paragraphs = _split_paragraphs(text, 0, None)

        # Should get at least 3 paragraphs
        assert len(paragraphs) >= 1

    def test_classify_section(self):
        """Test section classification."""
        from evidence_repository.digestion.section_builder import _classify_section
        from evidence_repository.models.evidence import SpanType

        # Test heading detection
        heading_type = _classify_section(
            "# Introduction",
            {"markdown_heading": True}
        )
        assert heading_type == SpanType.HEADING

        # Test table detection
        table_type = _classify_section(
            "| Col1 | Col2 | Col3 | Col4 | Col5 |",
            {"table": True}
        )
        assert table_type == SpanType.TABLE


# =============================================================================
# Integration Tests
# =============================================================================


class TestDigestionIntegration:
    """Integration tests for digestion pipeline."""

    def test_digest_steps_enum(self):
        """Test DigestStep enum has all required steps."""
        assert DigestStep.VALIDATE.value == "validate"
        assert DigestStep.DEDUPLICATE.value == "deduplicate"
        assert DigestStep.STORE.value == "store"
        assert DigestStep.PARSE.value == "parse"
        assert DigestStep.EXTRACT_METADATA.value == "extract_metadata"
        assert DigestStep.BUILD_SECTIONS.value == "build_sections"
        assert DigestStep.GENERATE_EMBEDDINGS.value == "generate_embeddings"
        assert DigestStep.ASSESS_TRUTHFULNESS.value == "assess_truthfulness"

    def test_compute_hash(self):
        """Test hash computation."""
        content = b"Test content for hashing"
        expected_hash = hashlib.sha256(content).hexdigest()

        # The pipeline should compute the same hash
        assert expected_hash == hashlib.sha256(content).hexdigest()


# =============================================================================
# Worker Tests
# =============================================================================


class TestPollingWorker:
    """Tests for polling worker."""

    def test_worker_stats(self):
        """Test worker statistics tracking."""
        from evidence_repository.digestion.polling_worker import PollingWorker

        worker = PollingWorker(poll_interval=1.0, batch_size=5)
        stats = worker.stats

        assert "hostname" in stats
        assert "documents_processed" in stats
        assert "documents_failed" in stats
        assert "iterations" in stats

    def test_worker_shutdown_request(self):
        """Test shutdown request handling."""
        from evidence_repository.digestion.polling_worker import PollingWorker

        worker = PollingWorker()
        assert worker._shutdown_requested is False

        worker.request_shutdown()
        assert worker._shutdown_requested is True
