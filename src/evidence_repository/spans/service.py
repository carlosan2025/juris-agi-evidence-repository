"""Span generation service for orchestrating span creation."""

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from evidence_repository.extraction.base import ExtractionArtifact
from evidence_repository.models.document import DocumentVersion
from evidence_repository.models.evidence import Span, SpanType
from evidence_repository.spans.base import BaseSpanGenerator, SpanData
from evidence_repository.spans.csv_span_generator import CsvSpanGenerator
from evidence_repository.spans.excel_span_generator import ExcelSpanGenerator
from evidence_repository.spans.image_span_generator import ImageSpanGenerator
from evidence_repository.spans.text_span_generator import TextSpanGenerator

logger = logging.getLogger(__name__)


class SpanGenerationService:
    """Service for generating and persisting document spans.

    Orchestrates:
    - Generator selection based on content type
    - Span generation from extraction artifacts
    - Idempotent span persistence with stable hashes
    - Duplicate detection via span_hash

    Usage:
        service = SpanGenerationService(db)
        spans = await service.generate_spans_for_version(version, artifact)
    """

    def __init__(
        self,
        db: AsyncSession,
        generators: list[BaseSpanGenerator] | None = None,
    ):
        """Initialize span generation service.

        Args:
            db: Database session.
            generators: List of span generators. Defaults to all built-in generators.
        """
        self.db = db
        self._generators: dict[str, BaseSpanGenerator] = {}

        # Register generators
        default_generators = generators or [
            TextSpanGenerator(),
            CsvSpanGenerator(),
            ExcelSpanGenerator(),
            ImageSpanGenerator(),
        ]

        for generator in default_generators:
            self.register_generator(generator)

    def register_generator(self, generator: BaseSpanGenerator) -> None:
        """Register a span generator for its supported content types.

        Args:
            generator: Generator instance to register.
        """
        for content_type in generator.supported_content_types:
            self._generators[content_type.lower()] = generator
            logger.debug(f"Registered {generator.name} span generator for {content_type}")

    def get_generator(self, content_type: str) -> BaseSpanGenerator | None:
        """Get generator for a content type.

        Args:
            content_type: MIME type to look up.

        Returns:
            Matching generator or None.
        """
        return self._generators.get(content_type.lower())

    async def generate_spans_for_version(
        self,
        version: DocumentVersion,
        artifact: ExtractionArtifact,
    ) -> list[Span]:
        """Generate and persist spans for a document version.

        This is the main entry point for span generation. It:
        1. Selects the appropriate generator based on content type
        2. Generates SpanData objects from the extraction artifact
        3. Persists spans with idempotent upsert (skip duplicates)

        Args:
            version: Document version to create spans for.
            artifact: Extraction artifact with content.

        Returns:
            List of created/existing Span records.
        """
        content_type = version.document.content_type
        generator = self.get_generator(content_type)

        if not generator:
            logger.warning(f"No span generator for content type: {content_type}")
            return []

        # Prepare data for generator
        tables_data = [t.to_dict() for t in artifact.tables] if artifact.tables else None
        images_data = [i.to_dict() for i in artifact.images] if artifact.images else None
        metadata = artifact.metadata.copy()
        metadata["filename"] = version.document.filename
        metadata["content_type"] = content_type

        # Generate span data
        span_data_list = generator.generate_spans(
            text=artifact.text,
            tables=tables_data,
            images=images_data,
            metadata=metadata,
        )

        if not span_data_list:
            logger.info(f"No spans generated for version {version.id}")
            return []

        # Persist spans
        spans = await self._persist_spans(version.id, span_data_list)

        logger.info(f"Generated {len(spans)} spans for version {version.id}")
        return spans

    async def generate_spans_from_text(
        self,
        version_id: UUID,
        text: str,
        content_type: str = "text/plain",
        metadata: dict[str, Any] | None = None,
    ) -> list[Span]:
        """Generate spans from raw text.

        Convenience method for generating spans directly from text
        without a full extraction artifact.

        Args:
            version_id: Document version ID.
            text: Text content to generate spans from.
            content_type: Content type for generator selection.
            metadata: Additional metadata.

        Returns:
            List of created Span records.
        """
        generator = self.get_generator(content_type)
        if not generator:
            generator = TextSpanGenerator()

        span_data_list = generator.generate_spans(
            text=text,
            tables=None,
            images=None,
            metadata=metadata or {},
        )

        return await self._persist_spans(version_id, span_data_list)

    async def _persist_spans(
        self,
        version_id: UUID,
        span_data_list: list[SpanData],
    ) -> list[Span]:
        """Persist spans to database with idempotent upsert.

        Uses span_hash for duplicate detection. If a span with the same
        version_id and span_hash exists, it's skipped.

        Args:
            version_id: Document version ID.
            span_data_list: List of SpanData to persist.

        Returns:
            List of Span records (created or existing).
        """
        spans: list[Span] = []

        for span_data in span_data_list:
            # Check for existing span with same hash
            existing = await self._get_span_by_hash(version_id, span_data.span_hash)

            if existing:
                spans.append(existing)
                continue

            # Create new span
            span = Span(
                document_version_id=version_id,
                span_hash=span_data.span_hash,
                start_locator=span_data.locator,
                end_locator=None,
                text_content=span_data.text_content,
                span_type=self._parse_span_type(span_data.span_type),
                metadata_=span_data.metadata,
            )
            self.db.add(span)
            spans.append(span)

        await self.db.flush()
        return spans

    async def _get_span_by_hash(
        self,
        version_id: UUID,
        span_hash: str,
    ) -> Span | None:
        """Get existing span by version and hash.

        Args:
            version_id: Document version ID.
            span_hash: Span hash.

        Returns:
            Existing Span or None.
        """
        result = await self.db.execute(
            select(Span).where(
                Span.document_version_id == version_id,
                Span.span_hash == span_hash,
            )
        )
        return result.scalar_one_or_none()

    def _parse_span_type(self, type_str: str) -> SpanType:
        """Parse span type string to enum.

        Args:
            type_str: Span type string.

        Returns:
            SpanType enum value.
        """
        try:
            return SpanType(type_str.lower())
        except ValueError:
            return SpanType.OTHER

    async def get_spans_for_version(
        self,
        version_id: UUID,
        span_type: SpanType | None = None,
    ) -> list[Span]:
        """Get all spans for a document version.

        Args:
            version_id: Document version ID.
            span_type: Optional filter by span type.

        Returns:
            List of Span records.
        """
        query = select(Span).where(Span.document_version_id == version_id)

        if span_type:
            query = query.where(Span.span_type == span_type)

        query = query.order_by(Span.created_at)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def delete_spans_for_version(self, version_id: UUID) -> int:
        """Delete all spans for a document version.

        Args:
            version_id: Document version ID.

        Returns:
            Number of deleted spans.
        """
        from sqlalchemy import delete

        result = await self.db.execute(
            delete(Span).where(Span.document_version_id == version_id)
        )
        await self.db.flush()
        return result.rowcount

    async def regenerate_spans(
        self,
        version: DocumentVersion,
        artifact: ExtractionArtifact,
    ) -> list[Span]:
        """Regenerate spans for a version, removing old ones.

        Args:
            version: Document version.
            artifact: Extraction artifact.

        Returns:
            List of newly created Span records.
        """
        # Delete existing spans
        deleted = await self.delete_spans_for_version(version.id)
        logger.info(f"Deleted {deleted} existing spans for version {version.id}")

        # Generate new spans
        return await self.generate_spans_for_version(version, artifact)

    @property
    def supported_content_types(self) -> list[str]:
        """Get all supported content types.

        Returns:
            List of MIME types.
        """
        return list(self._generators.keys())
