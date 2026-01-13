"""Tests for span generators."""

import pytest

from evidence_repository.spans.base import BaseSpanGenerator, SpanData
from evidence_repository.spans.text_span_generator import TextSpanGenerator
from evidence_repository.spans.csv_span_generator import CsvSpanGenerator
from evidence_repository.spans.excel_span_generator import ExcelSpanGenerator
from evidence_repository.spans.image_span_generator import ImageSpanGenerator


class TestSpanData:
    """Tests for SpanData dataclass."""

    def test_span_data_creation(self):
        """Test basic SpanData creation."""
        span = SpanData(
            text_content="Hello world",
            locator={"type": "text", "offset_start": 0, "offset_end": 11},
        )
        assert span.text_content == "Hello world"
        assert span.span_type == "text"
        assert len(span.span_hash) == 64  # SHA-256 hex

    def test_span_hash_stability(self):
        """Test that span hash is deterministic."""
        span1 = SpanData(
            text_content="Same content",
            locator={"type": "text", "offset_start": 0, "offset_end": 12},
        )
        span2 = SpanData(
            text_content="Same content",
            locator={"type": "text", "offset_start": 0, "offset_end": 12},
        )
        assert span1.span_hash == span2.span_hash

    def test_span_hash_different_for_different_content(self):
        """Test that different content produces different hashes."""
        span1 = SpanData(
            text_content="Content A",
            locator={"type": "text", "offset_start": 0, "offset_end": 9},
        )
        span2 = SpanData(
            text_content="Content B",
            locator={"type": "text", "offset_start": 0, "offset_end": 9},
        )
        assert span1.span_hash != span2.span_hash

    def test_span_hash_different_for_different_locators(self):
        """Test that different locators produce different hashes."""
        span1 = SpanData(
            text_content="Same content",
            locator={"type": "text", "offset_start": 0, "offset_end": 12},
        )
        span2 = SpanData(
            text_content="Same content",
            locator={"type": "text", "offset_start": 100, "offset_end": 112},
        )
        assert span1.span_hash != span2.span_hash


class TestTextSpanGenerator:
    """Tests for TextSpanGenerator."""

    @pytest.fixture
    def generator(self):
        return TextSpanGenerator(
            min_span_size=100,
            max_span_size=200,
            overlap_size=20,
        )

    def test_supported_content_types(self, generator):
        """Test supported content types."""
        assert "text/plain" in generator.supported_content_types
        assert "application/pdf" in generator.supported_content_types
        assert generator.can_handle("text/plain")

    def test_generate_spans_empty_text(self, generator):
        """Test with empty text."""
        spans = generator.generate_spans(
            text="",
            tables=None,
            images=None,
            metadata={},
        )
        assert spans == []

    def test_generate_spans_short_text(self, generator):
        """Test with text shorter than min_span_size."""
        short_text = "Hello world"
        spans = generator.generate_spans(
            text=short_text,
            tables=None,
            images=None,
            metadata={},
        )
        # Should still create a span for short text
        assert len(spans) >= 0

    def test_generate_spans_with_overlap(self):
        """Test that spans have proper overlap."""
        generator = TextSpanGenerator(
            min_span_size=50,
            max_span_size=100,
            overlap_size=20,
        )

        # Create text that should produce multiple spans
        text = "A" * 250

        spans = generator.generate_spans(
            text=text,
            tables=None,
            images=None,
            metadata={},
        )

        assert len(spans) >= 2

        # Check overlap between consecutive spans
        for i in range(len(spans) - 1):
            current_end = spans[i].locator["offset_end"]
            next_start = spans[i + 1].locator["offset_start"]
            # Next span should start before current ends (overlap)
            assert next_start < current_end

    def test_span_locator_format(self):
        """Test that locators have correct format."""
        generator = TextSpanGenerator(min_span_size=10, max_span_size=50)
        text = "A" * 100

        spans = generator.generate_spans(
            text=text,
            tables=None,
            images=None,
            metadata={},
        )

        for span in spans:
            assert "type" in span.locator
            assert span.locator["type"] == "text"
            assert "offset_start" in span.locator
            assert "offset_end" in span.locator
            assert span.locator["offset_start"] < span.locator["offset_end"]

    def test_page_hint_included(self):
        """Test that page_hint is included when page_breaks provided."""
        generator = TextSpanGenerator(min_span_size=50, max_span_size=100)
        text = "A" * 200

        spans = generator.generate_spans(
            text=text,
            tables=None,
            images=None,
            metadata={"page_breaks": [0, 100]},  # Page 2 starts at char 100
        )

        # First span should be on page 1, later spans may be on page 2
        assert spans[0].locator.get("page_hint") == 1


class TestCsvSpanGenerator:
    """Tests for CsvSpanGenerator."""

    @pytest.fixture
    def generator(self):
        return CsvSpanGenerator(rows_per_span=10)

    def test_supported_content_types(self, generator):
        """Test supported content types."""
        assert "text/csv" in generator.supported_content_types

    def test_generate_spans_empty(self, generator):
        """Test with no tables."""
        spans = generator.generate_spans(
            text=None,
            tables=None,
            images=None,
            metadata={},
        )
        assert spans == []

    def test_generate_spans_single_table(self, generator):
        """Test with a single table."""
        table = {
            "headers": ["Name", "Value"],
            "rows": [["A", 1], ["B", 2], ["C", 3]],
        }

        spans = generator.generate_spans(
            text=None,
            tables=[table],
            images=None,
            metadata={},
        )

        assert len(spans) == 1
        assert spans[0].span_type == "table"
        assert spans[0].locator["type"] == "csv"
        assert spans[0].locator["row_start"] == 0
        assert spans[0].locator["row_end"] == 3

    def test_generate_spans_large_table(self):
        """Test that large tables are split into multiple spans."""
        generator = CsvSpanGenerator(rows_per_span=5)

        table = {
            "headers": ["Col1", "Col2"],
            "rows": [[i, i * 2] for i in range(20)],
        }

        spans = generator.generate_spans(
            text=None,
            tables=[table],
            images=None,
            metadata={},
        )

        assert len(spans) == 4  # 20 rows / 5 rows per span
        assert spans[0].locator["row_start"] == 0
        assert spans[0].locator["row_end"] == 5
        assert spans[1].locator["row_start"] == 5

    def test_locator_format(self, generator):
        """Test CSV locator format."""
        table = {
            "headers": ["A", "B", "C"],
            "rows": [["x", "y", "z"]],
        }

        spans = generator.generate_spans(
            text=None,
            tables=[table],
            images=None,
            metadata={},
        )

        locator = spans[0].locator
        assert locator["type"] == "csv"
        assert locator["row_start"] == 0
        assert locator["row_end"] == 1
        assert locator["col_start"] == 0
        assert locator["col_end"] == 3


class TestExcelSpanGenerator:
    """Tests for ExcelSpanGenerator."""

    @pytest.fixture
    def generator(self):
        return ExcelSpanGenerator(rows_per_span=10)

    def test_supported_content_types(self, generator):
        """Test supported content types."""
        assert any("spreadsheetml" in ct for ct in generator.supported_content_types)

    def test_generate_spans_with_sheet(self):
        """Test that sheet name is included in locator."""
        generator = ExcelSpanGenerator(rows_per_span=25)

        table = {
            "sheet_name": "Sales",
            "headers": ["Product", "Amount"],
            "rows": [["Widget", 100], ["Gadget", 200]],
        }

        spans = generator.generate_spans(
            text=None,
            tables=[table],
            images=None,
            metadata={},
        )

        assert len(spans) == 1
        assert spans[0].locator["type"] == "excel"
        assert spans[0].locator["sheet"] == "Sales"
        assert "cell_range" in spans[0].locator

    def test_cell_range_format(self):
        """Test that cell range is in Excel notation."""
        generator = ExcelSpanGenerator(rows_per_span=10)

        table = {
            "sheet_name": "Data",
            "headers": ["A", "B", "C", "D"],
            "rows": [[1, 2, 3, 4] for _ in range(5)],
        }

        spans = generator.generate_spans(
            text=None,
            tables=[table],
            images=None,
            metadata={},
        )

        # Cell range should be like "A2:D6" (row 2-6, cols A-D)
        cell_range = spans[0].locator["cell_range"]
        assert cell_range.startswith("A")  # First column
        assert ":" in cell_range

    def test_column_letter_conversion(self):
        """Test column index to letter conversion."""
        generator = ExcelSpanGenerator()

        assert generator._col_index_to_letter(0) == "A"
        assert generator._col_index_to_letter(25) == "Z"
        assert generator._col_index_to_letter(26) == "AA"
        assert generator._col_index_to_letter(27) == "AB"


class TestImageSpanGenerator:
    """Tests for ImageSpanGenerator."""

    @pytest.fixture
    def generator(self):
        return ImageSpanGenerator()

    def test_supported_content_types(self, generator):
        """Test supported content types."""
        assert "image/png" in generator.supported_content_types
        assert "image/jpeg" in generator.supported_content_types

    def test_generate_standalone_image_span(self, generator):
        """Test span generation for standalone image."""
        spans = generator.generate_spans(
            text="OCR extracted text",
            tables=None,
            images=None,
            metadata={
                "filename": "document.png",
                "width": 800,
                "height": 600,
                "content_type": "image/png",
            },
        )

        assert len(spans) == 1
        assert spans[0].span_type == "figure"
        assert spans[0].locator["type"] == "image"
        assert spans[0].locator["filename"] == "document.png"
        assert spans[0].locator["width"] == 800
        assert spans[0].locator["height"] == 600
        assert "OCR extracted text" in spans[0].text_content

    def test_generate_embedded_image_spans(self, generator):
        """Test span generation for embedded images."""
        images = [
            {
                "image_index": 0,
                "content_type": "image/png",
                "width": 400,
                "height": 300,
                "page_number": 1,
                "ocr_text": "Text from image 1",
            },
            {
                "image_index": 1,
                "content_type": "image/jpeg",
                "width": 800,
                "height": 600,
                "page_number": 2,
                "ocr_text": None,
            },
        ]

        spans = generator.generate_spans(
            text=None,
            tables=None,
            images=images,
            metadata={},
        )

        assert len(spans) == 2

        # First image with OCR
        assert spans[0].locator["image_index"] == 0
        assert spans[0].locator["page_number"] == 1
        assert "Text from image 1" in spans[0].text_content

        # Second image without OCR
        assert spans[1].locator["image_index"] == 1
        assert spans[1].locator["page_number"] == 2

    def test_image_span_without_ocr(self, generator):
        """Test span generation for image without OCR text."""
        spans = generator.generate_spans(
            text=None,
            tables=None,
            images=None,
            metadata={
                "filename": "image.jpg",
                "width": 100,
                "height": 100,
            },
        )

        assert len(spans) == 1
        assert spans[0].metadata["has_ocr"] is False


class TestSpanHashIdempotency:
    """Tests for span hash idempotency."""

    def test_same_content_same_hash(self):
        """Test that identical spans produce identical hashes."""
        generator = TextSpanGenerator(min_span_size=10, max_span_size=50)
        text = "Test content for hashing"

        spans1 = generator.generate_spans(text=text, tables=None, images=None, metadata={})
        spans2 = generator.generate_spans(text=text, tables=None, images=None, metadata={})

        assert len(spans1) == len(spans2)
        for s1, s2 in zip(spans1, spans2):
            assert s1.span_hash == s2.span_hash

    def test_csv_hash_stability(self):
        """Test CSV span hash stability."""
        generator = CsvSpanGenerator()
        table = {
            "headers": ["A", "B"],
            "rows": [[1, 2], [3, 4]],
        }

        spans1 = generator.generate_spans(text=None, tables=[table], images=None, metadata={})
        spans2 = generator.generate_spans(text=None, tables=[table], images=None, metadata={})

        assert spans1[0].span_hash == spans2[0].span_hash
