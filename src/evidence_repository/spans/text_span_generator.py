"""Text span generator for PDF and plain text documents."""

import re
from typing import Any

from evidence_repository.spans.base import BaseSpanGenerator, SpanData


class TextSpanGenerator(BaseSpanGenerator):
    """Span generator for text-based documents (PDF, TXT, MD).

    Generates spans of 500-1000 characters with configurable overlap.
    Attempts to break at sentence/paragraph boundaries when possible.

    Rules:
    - Target span size: 500-1000 characters
    - Overlap: Configurable (default 100 chars)
    - Breaks at sentence boundaries when possible
    - Preserves paragraph structure
    """

    # Sentence-ending patterns
    SENTENCE_END_PATTERN = re.compile(r"[.!?]\s+")

    # Paragraph break pattern
    PARAGRAPH_PATTERN = re.compile(r"\n\s*\n")

    def __init__(
        self,
        min_span_size: int = 500,
        max_span_size: int = 1000,
        overlap_size: int = 100,
    ):
        """Initialize text span generator.

        Args:
            min_span_size: Minimum characters per span.
            max_span_size: Maximum characters per span.
            overlap_size: Characters to overlap between spans.
        """
        self.min_span_size = min_span_size
        self.max_span_size = max_span_size
        self.overlap_size = overlap_size

    @property
    def name(self) -> str:
        return "text"

    @property
    def supported_content_types(self) -> list[str]:
        return [
            "application/pdf",
            "text/plain",
            "text/markdown",
            "text/x-markdown",
        ]

    def generate_spans(
        self,
        text: str | None,
        tables: list[dict[str, Any]] | None,
        images: list[dict[str, Any]] | None,
        metadata: dict[str, Any],
    ) -> list[SpanData]:
        """Generate text spans with overlap.

        Args:
            text: Extracted text content.
            tables: Not used for text spans.
            images: Not used for text spans.
            metadata: Extraction metadata.

        Returns:
            List of SpanData objects.
        """
        if not text or not text.strip():
            return []

        spans: list[SpanData] = []
        text_length = len(text)

        # Detect page boundaries if available in metadata
        page_breaks = metadata.get("page_breaks", [])

        position = 0
        while position < text_length:
            # Calculate end position
            end_pos = min(position + self.max_span_size, text_length)

            # Try to find a good break point
            if end_pos < text_length:
                end_pos = self._find_break_point(text, position, end_pos)

            # Extract span text
            span_text = text[position:end_pos].strip()

            if span_text and len(span_text) >= self.min_span_size // 2:
                # Determine page hint
                page_hint = self._get_page_hint(position, page_breaks)

                # Create locator
                locator: dict[str, Any] = {
                    "type": "text",
                    "offset_start": position,
                    "offset_end": end_pos,
                }
                if page_hint is not None:
                    locator["page_hint"] = page_hint

                # Create span data
                span = SpanData(
                    text_content=span_text,
                    locator=locator,
                    span_type="text",
                    metadata={
                        "char_count": len(span_text),
                        "word_count": len(span_text.split()),
                    },
                )
                spans.append(span)

            # Move position with overlap
            if end_pos >= text_length:
                break

            position = end_pos - self.overlap_size
            if position <= spans[-1].locator.get("offset_start", 0) if spans else 0:
                position = end_pos  # Prevent infinite loop

        return spans

    def _find_break_point(self, text: str, start: int, max_end: int) -> int:
        """Find a good break point for the span.

        Tries to break at:
        1. Paragraph boundaries
        2. Sentence boundaries
        3. Word boundaries

        Args:
            text: Full text.
            start: Start position of current span.
            max_end: Maximum end position.

        Returns:
            Best break point position.
        """
        search_start = start + self.min_span_size
        search_text = text[search_start:max_end]

        # Try paragraph break first
        para_match = self.PARAGRAPH_PATTERN.search(search_text)
        if para_match:
            return search_start + para_match.end()

        # Try sentence break
        sentence_matches = list(self.SENTENCE_END_PATTERN.finditer(search_text))
        if sentence_matches:
            # Use the last sentence break within range
            return search_start + sentence_matches[-1].end()

        # Fall back to word boundary
        # Find last space before max_end
        last_space = text.rfind(" ", search_start, max_end)
        if last_space > search_start:
            return last_space + 1

        return max_end

    def _get_page_hint(
        self,
        position: int,
        page_breaks: list[int],
    ) -> int | None:
        """Get page number hint for a position.

        Args:
            position: Character position.
            page_breaks: List of character positions where pages start.

        Returns:
            Page number (1-indexed) or None.
        """
        if not page_breaks:
            return None

        # Find which page this position is on
        page = 1
        for break_pos in page_breaks:
            if position >= break_pos:
                page += 1
            else:
                break

        return page
