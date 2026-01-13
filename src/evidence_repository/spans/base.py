"""Base span generator interface and locator types."""

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, TypedDict


class TextLocator(TypedDict, total=False):
    """Locator for text/PDF documents.

    Example:
        {
            "type": "text",
            "offset_start": 0,
            "offset_end": 500,
            "page_hint": 1
        }
    """

    type: str  # "text"
    offset_start: int
    offset_end: int
    page_hint: int | None


class CsvLocator(TypedDict, total=False):
    """Locator for CSV files.

    Example:
        {
            "type": "csv",
            "row_start": 0,
            "row_end": 10,
            "col_start": 0,
            "col_end": 3
        }
    """

    type: str  # "csv"
    row_start: int
    row_end: int
    col_start: int
    col_end: int


class ExcelLocator(TypedDict, total=False):
    """Locator for Excel files.

    Example:
        {
            "type": "excel",
            "sheet": "Summary",
            "cell_range": "A1:D10"
        }
    """

    type: str  # "excel"
    sheet: str
    cell_range: str


class ImageLocator(TypedDict, total=False):
    """Locator for image files.

    Example:
        {
            "type": "image",
            "filename": "document.png",
            "width": 800,
            "height": 600,
            "image_index": 0
        }
    """

    type: str  # "image"
    filename: str
    width: int | None
    height: int | None
    image_index: int


@dataclass
class SpanData:
    """Data structure for a generated span.

    Contains all information needed to create a Span database record.
    """

    # Content
    text_content: str

    # Locator (JSON-serializable dict)
    locator: dict[str, Any]

    # Span type
    span_type: str = "text"

    # Stable hash for idempotency
    span_hash: str = ""

    # Additional metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Compute span_hash if not provided."""
        if not self.span_hash:
            self.span_hash = self.compute_hash()

    def compute_hash(self) -> str:
        """Compute a stable hash for this span.

        The hash is computed from:
        - locator (serialized)
        - text_content (first 1000 chars for efficiency)

        Returns:
            SHA-256 hash string (64 chars).
        """
        import json

        # Serialize locator deterministically
        locator_str = json.dumps(self.locator, sort_keys=True)

        # Use first 1000 chars of text for hash (full text can be very long)
        text_sample = self.text_content[:1000] if self.text_content else ""

        # Combine and hash
        hash_input = f"{locator_str}|{text_sample}"
        return hashlib.sha256(hash_input.encode("utf-8")).hexdigest()


class BaseSpanGenerator(ABC):
    """Abstract base class for span generators.

    Each generator handles a specific document type and produces
    SpanData objects that can be persisted as Span records.

    Subclasses must implement:
    - generate_spans(): Main span generation method
    - supported_content_types: List of MIME types handled
    - name: Human-readable generator name
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of this generator."""
        pass

    @property
    @abstractmethod
    def supported_content_types(self) -> list[str]:
        """List of MIME types this generator can handle."""
        pass

    def can_handle(self, content_type: str) -> bool:
        """Check if this generator can handle the given content type.

        Args:
            content_type: MIME type to check.

        Returns:
            True if this generator supports the content type.
        """
        return content_type.lower() in [ct.lower() for ct in self.supported_content_types]

    @abstractmethod
    def generate_spans(
        self,
        text: str | None,
        tables: list[dict[str, Any]] | None,
        images: list[dict[str, Any]] | None,
        metadata: dict[str, Any],
    ) -> list[SpanData]:
        """Generate spans from extracted content.

        Args:
            text: Extracted text content (for text/PDF).
            tables: List of table data dicts (for CSV/Excel).
            images: List of image data dicts (for images).
            metadata: Extraction metadata including filename, content_type, etc.

        Returns:
            List of SpanData objects ready for persistence.
        """
        pass
