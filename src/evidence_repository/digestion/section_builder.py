"""Section builder for creating spans from extracted text.

Creates structured sections (spans) from raw text using intelligent
paragraph detection and content classification.
"""

import hashlib
import logging
import re
import uuid
from datetime import datetime

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from evidence_repository.models.document import DocumentVersion
from evidence_repository.models.evidence import Span, SpanType

logger = logging.getLogger(__name__)


async def build_sections(
    db: AsyncSession,
    version: DocumentVersion,
    force_rebuild: bool = False,
) -> int:
    """Build sections (spans) from extracted text.

    Args:
        db: Async database session.
        version: DocumentVersion with extracted text.
        force_rebuild: Delete existing spans before building.

    Returns:
        Number of sections created.
    """
    if not version.extracted_text:
        return 0

    # Check for existing spans
    existing = await db.execute(
        select(Span).where(Span.document_version_id == version.id).limit(1)
    )
    if existing.scalar_one_or_none() and not force_rebuild:
        # Count existing
        count_result = await db.execute(
            select(Span.id).where(Span.document_version_id == version.id)
        )
        return len(count_result.fetchall())

    # Delete existing if rebuilding
    if force_rebuild:
        await db.execute(
            delete(Span).where(Span.document_version_id == version.id)
        )
        await db.flush()

    # Build new sections
    sections = _split_into_sections(version.extracted_text)

    created = 0
    for i, section in enumerate(sections):
        text = section["text"]
        if not text or len(text.strip()) < 10:
            continue

        # Compute hash for idempotency
        span_hash = hashlib.sha256(
            f"{version.id}:{i}:{text[:100]}".encode()
        ).hexdigest()[:64]

        # Determine span type
        span_type = _classify_section(text, section.get("hints", {}))

        span = Span(
            document_version_id=version.id,
            span_hash=span_hash,
            start_locator={
                "type": "text",
                "char_offset_start": section["start"],
                "char_offset_end": section["end"],
                "section_index": i,
                "page": section.get("page"),
            },
            end_locator=None,
            text_content=text,
            span_type=span_type,
            metadata_={
                "section_index": i,
                "section_type": section.get("type", "paragraph"),
            },
        )
        db.add(span)
        created += 1

    await db.flush()
    logger.info(f"Created {created} sections for version {version.id}")
    return created


def _split_into_sections(text: str) -> list[dict]:
    """Split text into logical sections.

    Args:
        text: Raw extracted text.

    Returns:
        List of section dicts with text, start, end, hints.
    """
    sections = []
    current_pos = 0

    # Split by page markers first
    page_pattern = r'---\s*Page\s*(\d+)\s*---'
    pages = re.split(page_pattern, text)

    page_num = None
    for i, part in enumerate(pages):
        if i % 2 == 1:  # Page number
            page_num = int(part)
            continue

        # Split into paragraphs
        paragraphs = _split_paragraphs(part, current_pos, page_num)
        sections.extend(paragraphs)
        current_pos += len(part)

    # If no page markers, just split by paragraphs
    if not sections:
        sections = _split_paragraphs(text, 0, None)

    return sections


def _split_paragraphs(
    text: str,
    offset: int,
    page: int | None,
) -> list[dict]:
    """Split text into paragraphs.

    Args:
        text: Text to split.
        offset: Character offset in full document.
        page: Page number if known.

    Returns:
        List of paragraph dicts.
    """
    paragraphs = []

    # Split by double newlines or form feeds
    parts = re.split(r'\n\n+|\f', text)

    current_pos = offset
    for i, part in enumerate(parts):
        part = part.strip()
        if not part:
            continue

        # Detect section type hints
        hints = {}
        if re.match(r'^#{1,6}\s', part):
            hints["markdown_heading"] = True
        elif re.match(r'^[A-Z][A-Z\s]{2,}$', part):
            hints["uppercase_heading"] = True
        elif '|' in part and part.count('|') > 2:
            hints["table"] = True
        elif re.match(r'^[-*•]\s', part):
            hints["list"] = True
        elif re.match(r'^\d+\.\s', part):
            hints["numbered_list"] = True

        paragraphs.append({
            "text": part,
            "start": current_pos,
            "end": current_pos + len(part),
            "page": page,
            "hints": hints,
            "type": "paragraph",
        })

        current_pos += len(part) + 2  # Account for separators

    return paragraphs


def _classify_section(text: str, hints: dict) -> SpanType:
    """Classify section type based on content.

    Args:
        text: Section text.
        hints: Hints from splitting.

    Returns:
        SpanType classification.
    """
    # Check hints first
    if hints.get("markdown_heading") or hints.get("uppercase_heading"):
        return SpanType.HEADING
    if hints.get("table"):
        return SpanType.TABLE
    if hints.get("list") or hints.get("numbered_list"):
        return SpanType.TEXT

    # Content-based classification
    text_lower = text.lower()

    # Check for citation patterns
    citation_patterns = [
        r'\[\d+\]',  # [1], [2]
        r'\(\d{4}\)',  # (2024)
        r'et al\.',
        r'ibid\.',
        r'op\.?\s*cit\.',
    ]
    for pattern in citation_patterns:
        if re.search(pattern, text_lower):
            return SpanType.CITATION

    # Check for footnote patterns
    if re.match(r'^\d+[.)]?\s', text) and len(text) < 500:
        return SpanType.FOOTNOTE

    # Check for table patterns
    if '|' in text and text.count('|') > 4:
        return SpanType.TABLE

    # Check for figure/image references
    if re.match(r'^(figure|fig\.|image|chart|graph|table)\s*\d+', text_lower):
        return SpanType.IMAGE

    return SpanType.TEXT
