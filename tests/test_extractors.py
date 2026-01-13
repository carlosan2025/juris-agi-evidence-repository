"""Tests for document extractors."""

import pytest
from pathlib import Path

from evidence_repository.extraction.base import (
    BaseExtractor,
    ExtractionArtifact,
    NoOpOCRProvider,
    TableData,
)
from evidence_repository.extraction.text_extractor import TextExtractor
from evidence_repository.extraction.csv_extractor import CsvExtractor
from evidence_repository.extraction.image_extractor import ImageExtractor


class TestExtractionArtifact:
    """Tests for ExtractionArtifact dataclass."""

    def test_artifact_creation(self):
        """Test basic artifact creation."""
        artifact = ExtractionArtifact(
            text="Hello world",
            extractor_name="test",
        )
        assert artifact.text == "Hello world"
        assert artifact.char_count == 11
        assert artifact.word_count == 2

    def test_artifact_with_tables(self):
        """Test artifact with table data."""
        table = TableData(
            headers=["Name", "Value"],
            rows=[["foo", 1], ["bar", 2]],
        )
        artifact = ExtractionArtifact(tables=[table])
        assert len(artifact.tables) == 1
        assert artifact.tables[0].headers == ["Name", "Value"]

    def test_artifact_to_dict(self):
        """Test serialization to dict."""
        table = TableData(
            headers=["A", "B"],
            rows=[[1, 2]],
            sheet_name="Sheet1",
        )
        artifact = ExtractionArtifact(
            text="Test",
            tables=[table],
            metadata={"key": "value"},
        )
        data = artifact.to_dict()
        assert data["text"] == "Test"
        assert len(data["tables"]) == 1
        assert data["tables"][0]["sheet_name"] == "Sheet1"
        assert data["metadata"]["key"] == "value"

    def test_artifact_has_content(self):
        """Test has_content check."""
        empty = ExtractionArtifact()
        assert not empty.has_content()

        with_text = ExtractionArtifact(text="Hello")
        assert with_text.has_content()

        with_tables = ExtractionArtifact(tables=[TableData(headers=["A"], rows=[[1]])])
        assert with_tables.has_content()

    def test_artifact_get_all_text(self):
        """Test get_all_text with OCR content."""
        from evidence_repository.extraction.base import ExtractedImage

        artifact = ExtractionArtifact(
            text="Main text",
            images=[
                ExtractedImage(
                    image_index=0,
                    content_type="image/png",
                    ocr_text="OCR from image",
                ),
            ],
        )
        all_text = artifact.get_all_text()
        assert "Main text" in all_text
        assert "OCR from image" in all_text


class TestTextExtractor:
    """Tests for TextExtractor."""

    @pytest.fixture
    def extractor(self):
        return TextExtractor()

    @pytest.mark.asyncio
    async def test_extract_utf8(self, extractor):
        """Test extraction of UTF-8 text."""
        data = "Hello, World!\nLine 2".encode("utf-8")
        artifact = await extractor.extract(data, "test.txt", "text/plain")

        assert artifact.text == "Hello, World!\nLine 2"
        assert artifact.metadata["encoding"] == "utf-8"
        assert artifact.metadata["line_count"] == 2

    @pytest.mark.asyncio
    async def test_extract_utf8_bom(self, extractor):
        """Test extraction of UTF-8 with BOM."""
        data = b"\xef\xbb\xbfHello with BOM"
        artifact = await extractor.extract(data, "test.txt", "text/plain")

        assert artifact.text == "Hello with BOM"
        assert artifact.metadata["encoding"] == "utf-8-sig"

    @pytest.mark.asyncio
    async def test_extract_latin1(self, extractor):
        """Test extraction of Latin-1 text."""
        data = "Café résumé".encode("latin-1")
        artifact = await extractor.extract(data, "test.txt", "text/plain")

        assert "Caf" in artifact.text
        assert artifact.metadata["encoding"] in ["latin-1", "utf-8"]

    @pytest.mark.asyncio
    async def test_detect_markdown_format(self, extractor):
        """Test markdown format detection."""
        data = b"# Heading\n\nParagraph"

        # By content type
        artifact = await extractor.extract(data, "test.md", "text/markdown")
        assert artifact.metadata["format"] == "markdown"

        # By extension
        artifact = await extractor.extract(data, "test.md", "text/plain")
        assert artifact.metadata["format"] == "markdown"

    def test_supported_content_types(self, extractor):
        """Test supported content types."""
        assert "text/plain" in extractor.supported_content_types
        assert "text/markdown" in extractor.supported_content_types

    def test_can_handle(self, extractor):
        """Test can_handle method."""
        assert extractor.can_handle("text/plain")
        assert extractor.can_handle("TEXT/PLAIN")  # Case insensitive
        assert not extractor.can_handle("application/pdf")


class TestCsvExtractor:
    """Tests for CsvExtractor."""

    @pytest.fixture
    def extractor(self):
        return CsvExtractor()

    @pytest.mark.asyncio
    async def test_extract_simple_csv(self, extractor):
        """Test extraction of simple CSV."""
        data = b"Name,Age,City\nAlice,30,NYC\nBob,25,LA"
        artifact = await extractor.extract(data, "test.csv", "text/csv")

        assert len(artifact.tables) == 1
        table = artifact.tables[0]
        assert table.headers == ["Name", "Age", "City"]
        assert len(table.rows) == 2
        assert table.rows[0] == ["Alice", 30, "NYC"]

    @pytest.mark.asyncio
    async def test_extract_semicolon_csv(self, extractor):
        """Test extraction of semicolon-delimited CSV."""
        data = b"A;B;C\n1;2;3\n4;5;6"
        artifact = await extractor.extract(data, "test.csv", "text/csv")

        assert artifact.metadata["delimiter"] == ";"
        table = artifact.tables[0]
        assert table.headers == ["A", "B", "C"]

    @pytest.mark.asyncio
    async def test_extract_tab_csv(self, extractor):
        """Test extraction of tab-delimited CSV."""
        data = b"Col1\tCol2\nVal1\tVal2"
        artifact = await extractor.extract(data, "test.tsv", "text/csv")

        assert artifact.metadata["delimiter"] == "\t"

    @pytest.mark.asyncio
    async def test_numeric_parsing(self, extractor):
        """Test numeric value parsing."""
        data = b"Int,Float,String\n42,3.14,text"
        artifact = await extractor.extract(data, "test.csv", "text/csv")

        table = artifact.tables[0]
        assert table.rows[0][0] == 42
        assert table.rows[0][1] == 3.14
        assert table.rows[0][2] == "text"

    @pytest.mark.asyncio
    async def test_text_representation(self, extractor):
        """Test text representation generation."""
        data = b"A,B\n1,2"
        artifact = await extractor.extract(data, "test.csv", "text/csv")

        assert "A | B" in artifact.text
        assert "1 | 2" in artifact.text

    def test_supported_content_types(self, extractor):
        """Test supported content types."""
        assert "text/csv" in extractor.supported_content_types


class TestImageExtractor:
    """Tests for ImageExtractor."""

    @pytest.fixture
    def extractor(self):
        return ImageExtractor()

    @pytest.fixture
    def extractor_with_noop_ocr(self):
        return ImageExtractor(ocr_provider=NoOpOCRProvider())

    def test_supported_content_types(self, extractor):
        """Test supported content types."""
        assert "image/png" in extractor.supported_content_types
        assert "image/jpeg" in extractor.supported_content_types
        assert "image/gif" in extractor.supported_content_types

    @pytest.mark.asyncio
    async def test_extract_stores_image(self, extractor, tmp_path):
        """Test that extraction stores image to output dir."""
        # Create a minimal PNG (1x1 pixel)
        png_data = (
            b"\x89PNG\r\n\x1a\n"  # PNG signature
            b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"  # IHDR chunk
            b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N"  # IDAT chunk
            b"\x00\x00\x00\x00IEND\xaeB`\x82"  # IEND chunk
        )

        artifact = await extractor.extract(
            data=png_data,
            filename="test.png",
            content_type="image/png",
            output_dir=tmp_path,
        )

        assert len(artifact.images) == 1
        assert artifact.images[0].content_type == "image/png"
        assert artifact.images[0].storage_path is not None
        assert Path(artifact.images[0].storage_path).exists()

    @pytest.mark.asyncio
    async def test_extract_metadata(self, extractor):
        """Test extraction includes metadata."""
        # Minimal PNG
        png_data = (
            b"\x89PNG\r\n\x1a\n"
            b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
            b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N"
            b"\x00\x00\x00\x00IEND\xaeB`\x82"
        )

        artifact = await extractor.extract(
            data=png_data,
            filename="test.png",
            content_type="image/png",
        )

        assert artifact.metadata["filename"] == "test.png"
        assert artifact.metadata["content_type"] == "image/png"
        assert artifact.metadata["ocr_provider"] == "noop"


class TestNoOpOCRProvider:
    """Tests for NoOpOCRProvider."""

    @pytest.mark.asyncio
    async def test_returns_empty_string(self):
        """Test that NoOp provider returns empty string."""
        provider = NoOpOCRProvider()
        result = await provider.extract_text(b"image data", "image/png")
        assert result == ""

    def test_name(self):
        """Test provider name."""
        provider = NoOpOCRProvider()
        assert provider.name == "noop"


class TestTableData:
    """Tests for TableData dataclass."""

    def test_table_creation(self):
        """Test basic table creation."""
        table = TableData(
            headers=["A", "B", "C"],
            rows=[[1, 2, 3], [4, 5, 6]],
        )
        assert len(table.headers) == 3
        assert len(table.rows) == 2

    def test_table_with_sheet_name(self):
        """Test table with sheet metadata."""
        table = TableData(
            headers=["X"],
            rows=[[1]],
            sheet_name="Sales",
            table_index=2,
        )
        assert table.sheet_name == "Sales"
        assert table.table_index == 2

    def test_table_to_dict(self):
        """Test table serialization."""
        table = TableData(
            headers=["A"],
            rows=[[1]],
            sheet_name="Test",
            metadata={"source": "excel"},
        )
        data = table.to_dict()
        assert data["headers"] == ["A"]
        assert data["rows"] == [[1]]
        assert data["sheet_name"] == "Test"
        assert data["metadata"]["source"] == "excel"
