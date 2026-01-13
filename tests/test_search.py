"""Tests for search functionality."""

import uuid
from datetime import datetime

import pytest

from evidence_repository.services.search_service import (
    Citation,
    SearchMode,
    SearchResultItem,
    SearchService,
    SpanLocator,
)


class TestKeywordFiltering:
    """Tests for keyword filtering logic."""

    def _create_service(self):
        """Create a service instance for testing helper methods."""
        return SearchService.__new__(SearchService)

    def test_passes_filter_with_no_keywords(self):
        """Test that text passes when no keywords specified."""
        service = self._create_service()
        text = "This is some sample text about revenue and metrics."

        result = service._passes_keyword_filter(text, None, None)

        assert result is True

    def test_passes_filter_with_matching_keywords(self):
        """Test that text passes when all keywords are present."""
        service = self._create_service()
        text = "The company reported revenue of $10M and ARR growth of 50%."

        result = service._passes_keyword_filter(
            text,
            keywords=["revenue", "ARR"],
            exclude_keywords=None,
        )

        assert result is True

    def test_fails_filter_with_missing_keyword(self):
        """Test that text fails when a required keyword is missing."""
        service = self._create_service()
        text = "The company reported revenue of $10M."

        result = service._passes_keyword_filter(
            text,
            keywords=["revenue", "ARR"],  # ARR not in text
            exclude_keywords=None,
        )

        assert result is False

    def test_fails_filter_with_excluded_keyword(self):
        """Test that text fails when an excluded keyword is present."""
        service = self._create_service()
        text = "The company is confidential and reported revenue of $10M."

        result = service._passes_keyword_filter(
            text,
            keywords=["revenue"],
            exclude_keywords=["confidential"],
        )

        assert result is False

    def test_passes_filter_without_excluded_keyword(self):
        """Test that text passes when excluded keywords are absent."""
        service = self._create_service()
        text = "The company reported revenue of $10M."

        result = service._passes_keyword_filter(
            text,
            keywords=["revenue"],
            exclude_keywords=["confidential", "secret"],
        )

        assert result is True

    def test_keyword_matching_is_case_insensitive(self):
        """Test that keyword matching is case-insensitive."""
        service = self._create_service()
        text = "The company reported REVENUE of $10M."

        result = service._passes_keyword_filter(
            text,
            keywords=["revenue"],  # lowercase
            exclude_keywords=None,
        )

        assert result is True

    def test_exclude_keyword_matching_is_case_insensitive(self):
        """Test that exclude keyword matching is case-insensitive."""
        service = self._create_service()
        text = "This is CONFIDENTIAL information."

        result = service._passes_keyword_filter(
            text,
            keywords=None,
            exclude_keywords=["confidential"],  # lowercase
        )

        assert result is False


class TestKeywordRelevance:
    """Tests for keyword relevance scoring."""

    def _create_service(self):
        """Create a service instance for testing helper methods."""
        return SearchService.__new__(SearchService)

    def test_relevance_with_no_keywords(self):
        """Test default relevance when no keywords."""
        service = self._create_service()

        relevance = service._calculate_keyword_relevance("Some text", [])

        assert relevance == 0.5

    def test_relevance_increases_with_matches(self):
        """Test relevance increases with keyword matches."""
        service = self._create_service()
        text = "Revenue revenue REVENUE growth"

        relevance = service._calculate_keyword_relevance(text, ["revenue"])

        # 3 matches (capped), normalized
        assert relevance > 0.5

    def test_relevance_with_multiple_keywords(self):
        """Test relevance with multiple keywords."""
        service = self._create_service()
        text = "Revenue growth and ARR metrics"

        relevance = service._calculate_keyword_relevance(text, ["revenue", "arr"])

        assert relevance > 0

    def test_relevance_zero_with_no_matches(self):
        """Test relevance is zero with no matches."""
        service = self._create_service()
        text = "Some unrelated text about nothing"

        relevance = service._calculate_keyword_relevance(text, ["revenue", "arr"])

        assert relevance == 0


class TestHighlightCalculation:
    """Tests for keyword highlight range calculation."""

    def _create_service(self):
        """Create a service instance for testing helper methods."""
        return SearchService.__new__(SearchService)

    def test_no_highlights_with_no_keywords(self):
        """Test no highlights when no keywords."""
        service = self._create_service()

        highlights = service._calculate_highlights("Some text", None)

        assert highlights is None

    def test_no_highlights_with_empty_keywords(self):
        """Test no highlights when empty keywords list."""
        service = self._create_service()

        highlights = service._calculate_highlights("Some text", [])

        assert highlights is None

    def test_highlights_single_keyword(self):
        """Test highlight for single keyword occurrence."""
        service = self._create_service()
        text = "The revenue is $10M"

        highlights = service._calculate_highlights(text, ["revenue"])

        assert highlights is not None
        assert len(highlights) == 1
        assert highlights[0]["start"] == 4  # "The " = 4 chars
        assert highlights[0]["end"] == 11  # "revenue" = 7 chars

    def test_highlights_multiple_occurrences(self):
        """Test highlights for multiple keyword occurrences."""
        service = self._create_service()
        text = "Revenue is up. Revenue growth is strong."

        highlights = service._calculate_highlights(text, ["revenue"])

        assert highlights is not None
        assert len(highlights) == 2

    def test_highlights_multiple_keywords(self):
        """Test highlights for multiple different keywords."""
        service = self._create_service()
        text = "Revenue and ARR are key metrics"

        highlights = service._calculate_highlights(text, ["revenue", "arr"])

        assert highlights is not None
        assert len(highlights) == 2

    def test_highlights_merge_overlapping(self):
        """Test that overlapping highlights are merged."""
        service = self._create_service()
        text = "The annual revenue rate is good"

        # "annual" and "revenue" are adjacent, should merge
        highlights = service._calculate_highlights(text, ["annual revenue"])

        assert highlights is not None


class TestSearchModes:
    """Tests for search mode enum."""

    def test_semantic_mode_value(self):
        """Test semantic mode enum value."""
        assert SearchMode.SEMANTIC.value == "semantic"

    def test_keyword_mode_value(self):
        """Test keyword mode enum value."""
        assert SearchMode.KEYWORD.value == "keyword"

    def test_hybrid_mode_value(self):
        """Test hybrid mode enum value."""
        assert SearchMode.HYBRID.value == "hybrid"


class TestCitationDataclass:
    """Tests for Citation dataclass."""

    def test_citation_creation(self):
        """Test creating a Citation instance."""
        locator = SpanLocator(
            type="pdf",
            page=5,
            bbox={"x1": 100, "y1": 200, "x2": 500, "y2": 250},
        )
        citation = Citation(
            span_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            document_version_id=uuid.uuid4(),
            document_filename="test.pdf",
            span_type="text",
            locator=locator,
            text_excerpt="Sample text excerpt",
        )

        assert citation.document_filename == "test.pdf"
        assert citation.span_type == "text"
        assert citation.locator.page == 5

    def test_span_locator_pdf_type(self):
        """Test SpanLocator for PDF documents."""
        locator = SpanLocator(
            type="pdf",
            page=10,
            bbox={"x1": 50, "y1": 100, "x2": 400, "y2": 150},
        )

        assert locator.type == "pdf"
        assert locator.page == 10
        assert locator.bbox is not None
        assert locator.sheet is None

    def test_span_locator_spreadsheet_type(self):
        """Test SpanLocator for spreadsheet documents."""
        locator = SpanLocator(
            type="spreadsheet",
            sheet="Summary",
            cell_range="A1:D10",
        )

        assert locator.type == "spreadsheet"
        assert locator.sheet == "Summary"
        assert locator.cell_range == "A1:D10"
        assert locator.page is None

    def test_span_locator_text_type(self):
        """Test SpanLocator for plain text documents."""
        locator = SpanLocator(
            type="text",
            char_offset_start=100,
            char_offset_end=500,
        )

        assert locator.type == "text"
        assert locator.char_offset_start == 100
        assert locator.char_offset_end == 500


class TestSearchResultItem:
    """Tests for SearchResultItem dataclass."""

    def test_result_item_creation(self):
        """Test creating a SearchResultItem."""
        locator = SpanLocator(type="text", char_offset_start=0, char_offset_end=100)
        citation = Citation(
            span_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            document_version_id=uuid.uuid4(),
            document_filename="test.txt",
            span_type="text",
            locator=locator,
            text_excerpt="Test excerpt",
        )

        result = SearchResultItem(
            result_id=uuid.uuid4(),
            similarity=0.85,
            citation=citation,
            matched_text="This is the matched text content",
            highlight_ranges=[{"start": 0, "end": 4}],
            metadata={"page": 1},
        )

        assert result.similarity == 0.85
        assert result.matched_text == "This is the matched text content"
        assert result.highlight_ranges is not None
        assert len(result.highlight_ranges) == 1

    def test_result_item_without_highlights(self):
        """Test SearchResultItem without highlights."""
        locator = SpanLocator(type="text")
        citation = Citation(
            span_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            document_version_id=uuid.uuid4(),
            document_filename="test.txt",
            span_type="text",
            locator=locator,
            text_excerpt="",
        )

        result = SearchResultItem(
            result_id=uuid.uuid4(),
            similarity=0.9,
            citation=citation,
            matched_text="Some text",
        )

        assert result.highlight_ranges is None
        assert result.metadata == {}


class TestSearchSchemas:
    """Tests for Pydantic search schemas."""

    def test_search_query_defaults(self):
        """Test SearchQuery default values."""
        from evidence_repository.schemas.search import SearchQuery, SearchMode

        query = SearchQuery(query="test query")

        assert query.limit == 10
        assert query.similarity_threshold == 0.7
        assert query.mode == SearchMode.SEMANTIC
        assert query.keywords is None
        assert query.exclude_keywords is None
        assert query.spans_only is False

    def test_search_query_with_keywords(self):
        """Test SearchQuery with keyword filters."""
        from evidence_repository.schemas.search import SearchQuery, SearchMode

        query = SearchQuery(
            query="revenue growth",
            keywords=["ARR", "MRR"],
            exclude_keywords=["draft"],
            mode=SearchMode.HYBRID,
        )

        assert query.keywords == ["ARR", "MRR"]
        assert query.exclude_keywords == ["draft"]
        assert query.mode == SearchMode.HYBRID

    def test_search_query_with_span_filters(self):
        """Test SearchQuery with span type filters."""
        from evidence_repository.schemas.search import (
            SearchQuery,
            SpanTypeFilter,
        )

        query = SearchQuery(
            query="financial data",
            span_types=[SpanTypeFilter.TABLE, SpanTypeFilter.TEXT],
            spans_only=True,
        )

        assert len(query.span_types) == 2
        assert SpanTypeFilter.TABLE in query.span_types
        assert query.spans_only is True

    def test_project_search_query_defaults(self):
        """Test ProjectSearchQuery default values."""
        from evidence_repository.schemas.search import ProjectSearchQuery

        query = ProjectSearchQuery(query="test")

        assert query.limit == 10
        assert query.similarity_threshold == 0.7
        assert query.keywords is None
        assert query.document_ids is None

    def test_citation_schema(self):
        """Test Citation Pydantic model."""
        from evidence_repository.schemas.search import Citation, SpanLocator

        locator = SpanLocator(type="pdf", page=5)
        citation = Citation(
            span_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            document_version_id=uuid.uuid4(),
            document_filename="report.pdf",
            span_type="text",
            locator=locator,
            text_excerpt="Sample excerpt",
        )

        # Test serialization
        data = citation.model_dump()
        assert data["document_filename"] == "report.pdf"
        assert data["locator"]["page"] == 5

    def test_search_result_schema(self):
        """Test SearchResult Pydantic model."""
        from evidence_repository.schemas.search import (
            Citation,
            SearchMode,
            SearchResult,
            SearchResultItem,
            SpanLocator,
        )

        locator = SpanLocator(type="text")
        citation = Citation(
            span_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            document_version_id=uuid.uuid4(),
            document_filename="test.txt",
            span_type="text",
            locator=locator,
            text_excerpt="",
        )
        result_item = SearchResultItem(
            result_id=uuid.uuid4(),
            similarity=0.9,
            citation=citation,
            matched_text="Test content",
        )

        result = SearchResult(
            query="test query",
            mode=SearchMode.SEMANTIC,
            results=[result_item],
            total=1,
            search_time_ms=15.5,
        )

        assert result.query == "test query"
        assert result.mode == SearchMode.SEMANTIC
        assert result.total == 1
        assert len(result.results) == 1
