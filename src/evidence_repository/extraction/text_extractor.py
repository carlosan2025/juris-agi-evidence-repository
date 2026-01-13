"""Plain text and markdown extractor."""

import logging
import time
from pathlib import Path

from evidence_repository.extraction.base import BaseExtractor, ExtractionArtifact

logger = logging.getLogger(__name__)


class TextExtractor(BaseExtractor):
    """Extractor for plain text and markdown files.

    Supports:
    - Plain text (.txt)
    - Markdown (.md)
    - Other text-based formats

    Handles multiple encodings with graceful fallback.
    """

    # Common encodings to try in order
    ENCODINGS = ["utf-8", "utf-8-sig", "latin-1", "cp1252", "iso-8859-1"]

    @property
    def name(self) -> str:
        return "text"

    @property
    def supported_content_types(self) -> list[str]:
        return [
            "text/plain",
            "text/markdown",
            "text/x-markdown",
        ]

    @property
    def version(self) -> str:
        return "1.0.0"

    async def extract(
        self,
        data: bytes,
        filename: str,
        content_type: str,
        output_dir: Path | None = None,
    ) -> ExtractionArtifact:
        """Extract content from a text file.

        Args:
            data: Raw file bytes.
            filename: Original filename.
            content_type: MIME type.
            output_dir: Not used for text extraction.

        Returns:
            ExtractionArtifact with text content.
        """
        start_time = time.time()
        artifact = self._create_artifact()

        # Detect and decode text
        text, encoding_used = self._decode_text(data)

        # Calculate line count
        lines = text.split("\n")
        line_count = len(lines)

        # Detect format from filename or content type
        file_format = self._detect_format(filename, content_type)

        # Calculate processing time
        processing_time_ms = int((time.time() - start_time) * 1000)

        # Build artifact
        artifact.text = text
        artifact.metadata = {
            "filename": filename,
            "encoding": encoding_used,
            "line_count": line_count,
            "format": file_format,
        }
        artifact.processing_time_ms = processing_time_ms

        return artifact

    def _decode_text(self, data: bytes) -> tuple[str, str]:
        """Decode bytes to string, trying multiple encodings.

        Args:
            data: Raw bytes to decode.

        Returns:
            Tuple of (decoded text, encoding used).
        """
        # Check for BOM (Byte Order Mark)
        if data.startswith(b"\xef\xbb\xbf"):
            return data[3:].decode("utf-8"), "utf-8-sig"
        if data.startswith(b"\xff\xfe"):
            return data[2:].decode("utf-16-le"), "utf-16-le"
        if data.startswith(b"\xfe\xff"):
            return data[2:].decode("utf-16-be"), "utf-16-be"

        # Try each encoding
        for encoding in self.ENCODINGS:
            try:
                return data.decode(encoding), encoding
            except (UnicodeDecodeError, LookupError):
                continue

        # Last resort: decode with replacement characters
        logger.warning("Could not detect encoding, using utf-8 with replacement")
        return data.decode("utf-8", errors="replace"), "utf-8-fallback"

    def _detect_format(self, filename: str, content_type: str) -> str:
        """Detect the text format from filename or content type.

        Args:
            filename: Original filename.
            content_type: MIME type.

        Returns:
            Format identifier string.
        """
        # Check content type
        if content_type in ("text/markdown", "text/x-markdown"):
            return "markdown"

        # Check file extension
        lower_filename = filename.lower()
        if lower_filename.endswith(".md") or lower_filename.endswith(".markdown"):
            return "markdown"
        if lower_filename.endswith(".rst"):
            return "restructuredtext"
        if lower_filename.endswith(".txt"):
            return "plain"

        return "plain"
