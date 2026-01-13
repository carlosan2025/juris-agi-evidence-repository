"""Base extractor interface and extraction artifacts."""

import enum
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID


class ExtractionStatus(str, enum.Enum):
    """Status of an extraction run."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class TableData:
    """Represents tabular data extracted from a document."""

    headers: list[str]
    rows: list[list[Any]]
    sheet_name: str | None = None
    table_index: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "headers": self.headers,
            "rows": self.rows,
            "sheet_name": self.sheet_name,
            "table_index": self.table_index,
            "metadata": self.metadata,
        }


@dataclass
class ExtractedImage:
    """Represents an image extracted from a document."""

    image_index: int
    content_type: str
    width: int | None = None
    height: int | None = None
    page_number: int | None = None
    storage_path: str | None = None
    ocr_text: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "image_index": self.image_index,
            "content_type": self.content_type,
            "width": self.width,
            "height": self.height,
            "page_number": self.page_number,
            "storage_path": self.storage_path,
            "ocr_text": self.ocr_text,
            "metadata": self.metadata,
        }


@dataclass
class ExtractionArtifact:
    """Complete extraction result from a document.

    Contains all extracted content: text, tables, images, and metadata.
    Artifacts are stored under /data/extracted/{document_id}/{version_id}/
    """

    # Primary text content
    text: str | None = None

    # Structured data (tables, spreadsheets)
    tables: list[TableData] = field(default_factory=list)

    # Embedded images with optional OCR
    images: list[ExtractedImage] = field(default_factory=list)

    # Document metadata extracted during processing
    metadata: dict[str, Any] = field(default_factory=dict)

    # Processing details
    extractor_name: str = ""
    extractor_version: str = "1.0.0"
    page_count: int | None = None
    char_count: int | None = None
    word_count: int | None = None
    processing_time_ms: int | None = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Compute derived fields after initialization."""
        if self.text and self.char_count is None:
            self.char_count = len(self.text)
        if self.text and self.word_count is None:
            self.word_count = len(self.text.split())

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "text": self.text,
            "tables": [t.to_dict() for t in self.tables],
            "images": [i.to_dict() for i in self.images],
            "metadata": self.metadata,
            "extractor_name": self.extractor_name,
            "extractor_version": self.extractor_version,
            "page_count": self.page_count,
            "char_count": self.char_count,
            "word_count": self.word_count,
            "processing_time_ms": self.processing_time_ms,
            "warnings": self.warnings,
            "errors": self.errors,
        }

    def has_content(self) -> bool:
        """Check if any content was extracted."""
        return bool(self.text or self.tables or self.images)

    def get_all_text(self) -> str:
        """Get all text including OCR from images."""
        parts = []
        if self.text:
            parts.append(self.text)
        for img in self.images:
            if img.ocr_text:
                parts.append(f"[Image {img.image_index}]: {img.ocr_text}")
        return "\n\n".join(parts)


class BaseExtractor(ABC):
    """Abstract base class for document extractors.

    Each extractor handles a specific document type (PDF, text, CSV, etc.)
    and produces an ExtractionArtifact containing the extracted content.

    Subclasses must implement:
    - extract(): Main extraction method
    - supported_content_types: List of MIME types this extractor handles
    - name: Human-readable extractor name
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of this extractor."""
        pass

    @property
    @abstractmethod
    def supported_content_types(self) -> list[str]:
        """List of MIME types this extractor can handle."""
        pass

    @property
    def version(self) -> str:
        """Version of this extractor."""
        return "1.0.0"

    def can_handle(self, content_type: str) -> bool:
        """Check if this extractor can handle the given content type.

        Args:
            content_type: MIME type to check.

        Returns:
            True if this extractor supports the content type.
        """
        return content_type.lower() in [ct.lower() for ct in self.supported_content_types]

    @abstractmethod
    async def extract(
        self,
        data: bytes,
        filename: str,
        content_type: str,
        output_dir: Path | None = None,
    ) -> ExtractionArtifact:
        """Extract content from a document.

        Args:
            data: Raw document bytes.
            filename: Original filename (for extension hints).
            content_type: MIME type of the document.
            output_dir: Directory to store extracted artifacts (images, etc.).

        Returns:
            ExtractionArtifact containing all extracted content.
        """
        pass

    def _create_artifact(self, **kwargs: Any) -> ExtractionArtifact:
        """Create an ExtractionArtifact with this extractor's info."""
        return ExtractionArtifact(
            extractor_name=self.name,
            extractor_version=self.version,
            **kwargs,
        )


class OCRProvider(ABC):
    """Abstract base class for OCR providers.

    Allows pluggable OCR backends (Tesseract, Google Vision, AWS Textract, etc.)
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of this OCR provider."""
        pass

    @abstractmethod
    async def extract_text(
        self,
        image_data: bytes,
        content_type: str,
        language: str = "eng",
    ) -> str:
        """Extract text from an image using OCR.

        Args:
            image_data: Raw image bytes.
            content_type: MIME type of the image.
            language: Language code for OCR (e.g., 'eng', 'spa').

        Returns:
            Extracted text from the image.
        """
        pass


class NoOpOCRProvider(OCRProvider):
    """No-operation OCR provider that returns empty text.

    Used as default when no OCR service is configured.
    """

    @property
    def name(self) -> str:
        return "noop"

    async def extract_text(
        self,
        image_data: bytes,
        content_type: str,
        language: str = "eng",
    ) -> str:
        """Returns empty string (no OCR performed)."""
        return ""
