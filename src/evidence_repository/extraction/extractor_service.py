"""Extraction service orchestrator using BaseExtractor interface."""

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from evidence_repository.config import get_settings
from evidence_repository.extraction.base import BaseExtractor, ExtractionArtifact
from evidence_repository.extraction.csv_extractor import CsvExtractor
from evidence_repository.extraction.excel_extractor import ExcelExtractor
from evidence_repository.extraction.image_extractor import ImageExtractor
from evidence_repository.extraction.pdf_extractor import PdfExtractor
from evidence_repository.extraction.text_extractor import TextExtractor
from evidence_repository.models.document import DocumentVersion, ExtractionStatus
from evidence_repository.models.extraction import ExtractionRun, ExtractionRunStatus
from evidence_repository.storage.base import StorageBackend

logger = logging.getLogger(__name__)


class ExtractorService:
    """Service for orchestrating document extraction.

    Manages:
    - Extractor registration and selection
    - Extraction run lifecycle
    - Artifact storage and retrieval
    - Progress tracking

    Artifacts are stored under: /data/extracted/{document_id}/{version_id}/
    """

    def __init__(
        self,
        storage: StorageBackend,
        db: AsyncSession,
        extractors: list[BaseExtractor] | None = None,
    ):
        """Initialize extractor service.

        Args:
            storage: Storage backend for file access.
            db: Database session.
            extractors: List of extractors to use. Defaults to all built-in extractors.
        """
        self.storage = storage
        self.db = db
        self._extractors: dict[str, BaseExtractor] = {}

        # Register extractors
        default_extractors = extractors or [
            PdfExtractor(),
            TextExtractor(),
            CsvExtractor(),
            ExcelExtractor(),
            ImageExtractor(),
        ]

        for extractor in default_extractors:
            self.register_extractor(extractor)

    def register_extractor(self, extractor: BaseExtractor) -> None:
        """Register an extractor for its supported content types.

        Args:
            extractor: Extractor instance to register.
        """
        for content_type in extractor.supported_content_types:
            self._extractors[content_type.lower()] = extractor
            logger.debug(f"Registered {extractor.name} for {content_type}")

    def get_extractor(self, content_type: str) -> BaseExtractor | None:
        """Get extractor for a content type.

        Args:
            content_type: MIME type to look up.

        Returns:
            Matching extractor or None if not found.
        """
        return self._extractors.get(content_type.lower())

    def can_extract(self, content_type: str) -> bool:
        """Check if content type is supported for extraction.

        Args:
            content_type: MIME type to check.

        Returns:
            True if an extractor exists for this type.
        """
        return content_type.lower() in self._extractors

    async def extract_document(
        self,
        version: DocumentVersion,
        force: bool = False,
    ) -> ExtractionRun:
        """Extract content from a document version.

        Creates an extraction run, executes the appropriate extractor,
        and stores the artifacts.

        Args:
            version: Document version to extract.
            force: If True, extract even if already extracted.

        Returns:
            ExtractionRun record with results.
        """
        content_type = version.document.content_type

        # Check if already extracted
        if not force and version.extraction_status == ExtractionStatus.COMPLETED:
            existing_run = await self._get_latest_run(version.id)
            if existing_run and existing_run.status == ExtractionRunStatus.COMPLETED:
                logger.info(f"Version {version.id} already extracted, skipping")
                return existing_run

        # Get extractor
        extractor = self.get_extractor(content_type)
        if not extractor:
            run = await self._create_failed_run(
                version_id=version.id,
                extractor_name="unknown",
                error=f"No extractor for content type: {content_type}",
            )
            version.extraction_status = ExtractionStatus.FAILED
            version.extraction_error = f"No extractor for content type: {content_type}"
            await self.db.flush()
            return run

        # Create extraction run record
        run = ExtractionRun(
            document_version_id=version.id,
            status=ExtractionRunStatus.RUNNING,
            extractor_name=extractor.name,
            extractor_version=extractor.version,
            started_at=datetime.now(timezone.utc),
        )
        self.db.add(run)
        await self.db.flush()

        # Update version status
        version.extraction_status = ExtractionStatus.PROCESSING
        await self.db.flush()

        try:
            # Download document content
            data = await self.storage.download(version.storage_path)

            # Prepare output directory for artifacts
            settings = get_settings()
            output_dir = Path(settings.data_dir) / "extracted" / str(version.document_id) / str(version.id)
            output_dir.mkdir(parents=True, exist_ok=True)

            # Run extraction
            artifact = await extractor.extract(
                data=data,
                filename=version.document.filename,
                content_type=content_type,
                output_dir=output_dir,
            )

            # Store artifact JSON
            artifact_path = output_dir / "artifact.json"
            with open(artifact_path, "w") as f:
                json.dump(artifact.to_dict(), f, indent=2, default=str)

            # Update run with results
            run.status = ExtractionRunStatus.COMPLETED
            run.completed_at = datetime.now(timezone.utc)
            run.artifact_path = str(output_dir)
            run.has_text = bool(artifact.text)
            run.has_tables = bool(artifact.tables)
            run.has_images = bool(artifact.images)
            run.char_count = artifact.char_count
            run.word_count = artifact.word_count
            run.page_count = artifact.page_count
            run.table_count = len(artifact.tables)
            run.image_count = len(artifact.images)
            run.processing_time_ms = artifact.processing_time_ms
            run.warnings = artifact.warnings
            run.metadata_ = artifact.metadata

            # Update version with extracted content
            version.extracted_text = artifact.text
            version.extraction_status = ExtractionStatus.COMPLETED
            version.extraction_error = None
            version.extracted_at = datetime.now(timezone.utc)
            version.page_count = artifact.page_count

            await self.db.flush()

            logger.info(
                f"Extracted version {version.id}: "
                f"text={run.has_text}, tables={run.table_count}, images={run.image_count}"
            )

            return run

        except Exception as e:
            logger.error(f"Extraction failed for version {version.id}: {e}")

            # Update run with failure
            run.status = ExtractionRunStatus.FAILED
            run.completed_at = datetime.now(timezone.utc)
            run.error_message = str(e)
            if run.started_at:
                run.processing_time_ms = int(
                    (datetime.now(timezone.utc) - run.started_at).total_seconds() * 1000
                )

            # Update version status
            version.extraction_status = ExtractionStatus.FAILED
            version.extraction_error = str(e)

            await self.db.flush()
            raise

    async def get_extraction_run(self, run_id: UUID) -> ExtractionRun | None:
        """Get an extraction run by ID.

        Args:
            run_id: UUID of the extraction run.

        Returns:
            ExtractionRun or None if not found.
        """
        result = await self.db.execute(
            select(ExtractionRun).where(ExtractionRun.id == run_id)
        )
        return result.scalar_one_or_none()

    async def get_extraction_artifact(self, run: ExtractionRun) -> ExtractionArtifact | None:
        """Load the extraction artifact for a run.

        Args:
            run: Extraction run to load artifact for.

        Returns:
            ExtractionArtifact or None if not found.
        """
        if not run.artifact_path:
            return None

        artifact_file = Path(run.artifact_path) / "artifact.json"
        if not artifact_file.exists():
            return None

        try:
            with open(artifact_file) as f:
                data = json.load(f)

            # Reconstruct artifact from JSON
            from evidence_repository.extraction.base import TableData, ExtractedImage

            artifact = ExtractionArtifact(
                text=data.get("text"),
                tables=[
                    TableData(
                        headers=t["headers"],
                        rows=t["rows"],
                        sheet_name=t.get("sheet_name"),
                        table_index=t.get("table_index", 0),
                        metadata=t.get("metadata", {}),
                    )
                    for t in data.get("tables", [])
                ],
                images=[
                    ExtractedImage(
                        image_index=i["image_index"],
                        content_type=i["content_type"],
                        width=i.get("width"),
                        height=i.get("height"),
                        page_number=i.get("page_number"),
                        storage_path=i.get("storage_path"),
                        ocr_text=i.get("ocr_text"),
                        metadata=i.get("metadata", {}),
                    )
                    for i in data.get("images", [])
                ],
                metadata=data.get("metadata", {}),
                extractor_name=data.get("extractor_name", ""),
                extractor_version=data.get("extractor_version", "1.0.0"),
                page_count=data.get("page_count"),
                char_count=data.get("char_count"),
                word_count=data.get("word_count"),
                processing_time_ms=data.get("processing_time_ms"),
                warnings=data.get("warnings", []),
                errors=data.get("errors", []),
            )

            return artifact

        except Exception as e:
            logger.error(f"Failed to load artifact: {e}")
            return None

    async def _get_latest_run(self, version_id: UUID) -> ExtractionRun | None:
        """Get the latest extraction run for a version.

        Args:
            version_id: Document version ID.

        Returns:
            Latest ExtractionRun or None.
        """
        result = await self.db.execute(
            select(ExtractionRun)
            .where(ExtractionRun.document_version_id == version_id)
            .order_by(ExtractionRun.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _create_failed_run(
        self,
        version_id: UUID,
        extractor_name: str,
        error: str,
    ) -> ExtractionRun:
        """Create a failed extraction run record.

        Args:
            version_id: Document version ID.
            extractor_name: Name of the extractor (or "unknown").
            error: Error message.

        Returns:
            Failed ExtractionRun record.
        """
        now = datetime.now(timezone.utc)
        run = ExtractionRun(
            document_version_id=version_id,
            status=ExtractionRunStatus.FAILED,
            extractor_name=extractor_name,
            extractor_version="1.0.0",
            started_at=now,
            completed_at=now,
            error_message=error,
        )
        self.db.add(run)
        await self.db.flush()
        return run

    @property
    def supported_content_types(self) -> list[str]:
        """Get all supported content types.

        Returns:
            List of supported MIME types.
        """
        return list(self._extractors.keys())
