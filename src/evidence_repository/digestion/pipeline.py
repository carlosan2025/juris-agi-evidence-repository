"""Unified document digestion pipeline.

This module provides a single entry point for processing documents from any
trigger (API upload, worker, batch import, etc.).

Key patterns:
1. Shared pipeline logic - same code path for all processing modes
2. Database status transitions - PENDING → PROCESSING → READY/FAILED
3. Content hash deduplication at upload time
4. Graceful fallbacks for parsing failures
5. LLM-based metadata extraction
"""

import hashlib
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from evidence_repository.config import get_settings
from evidence_repository.models.document import Document, DocumentVersion, ExtractionStatus

logger = logging.getLogger(__name__)


class DigestStep(str, Enum):
    """Steps in the digestion pipeline."""

    VALIDATE = "validate"
    DEDUPLICATE = "deduplicate"
    STORE = "store"
    PARSE = "parse"
    EXTRACT_METADATA = "extract_metadata"
    BUILD_SECTIONS = "build_sections"
    GENERATE_EMBEDDINGS = "generate_embeddings"
    ASSESS_TRUTHFULNESS = "assess_truthfulness"


@dataclass
class DigestOptions:
    """Options for document digestion."""

    # Processing options
    skip_embeddings: bool = False
    skip_metadata_extraction: bool = False
    skip_truthfulness_assessment: bool = True  # Off by default (costly)
    force_reprocess: bool = False

    # Profile options
    profile_code: str = "general"
    process_context: str = "unspecified"
    extraction_level: int = 2

    # Source tracking
    source_url: str | None = None
    source_path: str | None = None
    uploaded_by: str | None = None

    # Processing hints
    expected_document_type: str | None = None
    language_hint: str | None = None


@dataclass
class DigestResult:
    """Result of document digestion."""

    document_id: uuid.UUID | None = None
    version_id: uuid.UUID | None = None
    status: str = "pending"
    deduplicated: bool = False

    # Step results
    steps_completed: list[str] = field(default_factory=list)
    steps_failed: list[str] = field(default_factory=list)
    step_results: dict[str, Any] = field(default_factory=dict)

    # Content summary
    text_length: int = 0
    page_count: int | None = None
    section_count: int = 0
    embedding_count: int = 0

    # Extracted metadata (from LLM)
    extracted_metadata: dict[str, Any] = field(default_factory=dict)

    # Timing
    started_at: datetime | None = None
    completed_at: datetime | None = None
    processing_time_ms: float = 0

    # Errors
    error_message: str | None = None
    error_step: str | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "document_id": str(self.document_id) if self.document_id else None,
            "version_id": str(self.version_id) if self.version_id else None,
            "status": self.status,
            "deduplicated": self.deduplicated,
            "steps_completed": self.steps_completed,
            "steps_failed": self.steps_failed,
            "text_length": self.text_length,
            "page_count": self.page_count,
            "section_count": self.section_count,
            "embedding_count": self.embedding_count,
            "extracted_metadata": self.extracted_metadata,
            "processing_time_ms": self.processing_time_ms,
            "error_message": self.error_message,
            "error_step": self.error_step,
        }


class DigestionPipeline:
    """Unified document digestion pipeline.

    This class encapsulates all document processing logic in a single place,
    ensuring consistency across all entry points (API, worker, batch import).

    Usage:
        pipeline = DigestionPipeline(db=session, storage=storage_backend)
        result = await pipeline.digest(
            file_data=content,
            filename="report.pdf",
            content_type="application/pdf",
            options=DigestOptions(profile_code="vc"),
        )
    """

    def __init__(self, db: AsyncSession, storage=None):
        """Initialize digestion pipeline.

        Args:
            db: Async database session.
            storage: Storage backend (defaults to local filesystem).
        """
        self.db = db
        self._storage = storage
        self._settings = get_settings()

    @property
    def storage(self):
        """Lazy-load storage backend."""
        if self._storage is None:
            from evidence_repository.storage import get_storage_backend
            self._storage = get_storage_backend()
        return self._storage

    async def digest(
        self,
        file_data: bytes,
        filename: str,
        content_type: str,
        options: DigestOptions | None = None,
    ) -> DigestResult:
        """Process a document through the complete digestion pipeline.

        This is the main entry point for document processing. All other methods
        (API upload, worker processing, batch import) should call this method.

        Args:
            file_data: Raw file content.
            filename: Original filename.
            content_type: MIME type.
            options: Processing options.

        Returns:
            DigestResult with processing results and any errors.
        """
        options = options or DigestOptions()
        result = DigestResult(started_at=datetime.utcnow())

        try:
            # Step 1: Validate input
            await self._step_validate(file_data, filename, content_type, result)
            if result.status == "failed":
                return result

            # Step 2: Check for duplicate
            file_hash = self._compute_hash(file_data)
            existing = await self._step_deduplicate(file_hash, options, result)
            if existing:
                return result

            # Step 3: Store file and create records
            document, version = await self._step_store(
                file_data, filename, content_type, file_hash, options, result
            )
            if result.status == "failed":
                return result

            result.document_id = document.id
            result.version_id = version.id

            # Step 4: Parse document (extract text)
            await self._step_parse(document, version, file_data, result)

            # Step 5: Extract metadata using LLM (optional)
            if not options.skip_metadata_extraction:
                await self._step_extract_metadata(document, version, result)

            # Step 6: Build sections (spans)
            await self._step_build_sections(version, result)

            # Step 7: Generate embeddings (optional)
            if not options.skip_embeddings:
                await self._step_generate_embeddings(version, result)

            # Step 8: Assess truthfulness (optional)
            if not options.skip_truthfulness_assessment:
                await self._step_assess_truthfulness(version, result)

            # Mark as complete
            version.extraction_status = ExtractionStatus.COMPLETED
            await self.db.commit()

            result.status = "ready"
            result.completed_at = datetime.utcnow()
            result.processing_time_ms = (
                result.completed_at - result.started_at
            ).total_seconds() * 1000

            logger.info(
                f"Document digestion complete: {document.id} "
                f"({result.processing_time_ms:.0f}ms)"
            )

        except Exception as e:
            logger.error(f"Digestion failed for {filename}: {e}")
            result.status = "failed"
            result.error_message = str(e)
            result.completed_at = datetime.utcnow()

            # Update version status if we have one
            if result.version_id:
                try:
                    await self.db.execute(
                        update(DocumentVersion)
                        .where(DocumentVersion.id == result.version_id)
                        .values(
                            extraction_status=ExtractionStatus.FAILED,
                            extraction_error=str(e),
                        )
                    )
                    await self.db.commit()
                except Exception:
                    pass

        return result

    def _compute_hash(self, data: bytes) -> str:
        """Compute SHA-256 hash of file content."""
        return hashlib.sha256(data).hexdigest()

    async def _step_validate(
        self,
        file_data: bytes,
        filename: str,
        content_type: str,
        result: DigestResult,
    ) -> None:
        """Validate input data."""
        step_name = DigestStep.VALIDATE.value

        # Check file size
        max_size = self._settings.max_file_size_mb * 1024 * 1024
        if len(file_data) > max_size:
            result.status = "failed"
            result.error_step = step_name
            result.error_message = f"File too large: {len(file_data)} bytes (max {max_size})"
            result.steps_failed.append(step_name)
            return

        # Check extension
        extension = Path(filename).suffix.lower()
        if extension not in self._settings.supported_extensions:
            result.status = "failed"
            result.error_step = step_name
            result.error_message = f"Unsupported file type: {extension}"
            result.steps_failed.append(step_name)
            return

        result.steps_completed.append(step_name)
        result.step_results[step_name] = {
            "file_size": len(file_data),
            "filename": filename,
            "content_type": content_type,
        }

    async def _step_deduplicate(
        self,
        file_hash: str,
        options: DigestOptions,
        result: DigestResult,
    ) -> Document | None:
        """Check for existing document with same content hash."""
        step_name = DigestStep.DEDUPLICATE.value

        existing = await self.db.execute(
            select(Document).where(
                Document.file_hash == file_hash,
                Document.deleted_at.is_(None),
            )
        )
        existing_doc = existing.scalar_one_or_none()

        if existing_doc and not options.force_reprocess:
            # Load versions relationship
            from sqlalchemy.orm import selectinload
            doc_result = await self.db.execute(
                select(Document)
                .options(selectinload(Document.versions))
                .where(Document.id == existing_doc.id)
            )
            existing_doc = doc_result.scalar_one()

            result.document_id = existing_doc.id
            result.version_id = existing_doc.versions[0].id if existing_doc.versions else None
            result.deduplicated = True
            result.status = "ready"
            result.steps_completed.append(step_name)
            result.step_results[step_name] = {"action": "deduplicated"}

            logger.info(f"Document deduplicated: {existing_doc.id}")
            return existing_doc

        result.steps_completed.append(step_name)
        result.step_results[step_name] = {"action": "new_document"}
        return None

    async def _step_store(
        self,
        file_data: bytes,
        filename: str,
        content_type: str,
        file_hash: str,
        options: DigestOptions,
        result: DigestResult,
    ) -> tuple[Document, DocumentVersion]:
        """Store file and create database records."""
        step_name = DigestStep.STORE.value

        try:
            # Create document
            document = Document(
                filename=filename,
                original_filename=filename,
                content_type=content_type,
                file_hash=file_hash,
                profile_code=options.profile_code,
                metadata_={
                    "source_url": options.source_url,
                    "source_path": options.source_path,
                    "uploaded_by": options.uploaded_by,
                },
            )
            self.db.add(document)
            await self.db.flush()

            # Generate storage path
            version_number = 1
            storage_path = f"documents/{document.id}/v{version_number}/{filename}"

            # Upload to storage
            await self.storage.upload(
                key=storage_path,
                data=file_data,
                content_type=content_type,
                metadata={"document_id": str(document.id)},
            )

            # Create version
            version = DocumentVersion(
                document_id=document.id,
                version_number=version_number,
                storage_path=storage_path,
                file_size=len(file_data),
                file_hash=file_hash,
                extraction_status=ExtractionStatus.PROCESSING,
                metadata_={"uploaded_by": options.uploaded_by} if options.uploaded_by else {},
            )
            self.db.add(version)
            await self.db.flush()

            result.steps_completed.append(step_name)
            result.step_results[step_name] = {
                "document_id": str(document.id),
                "version_id": str(version.id),
                "storage_path": storage_path,
            }

            return document, version

        except Exception as e:
            result.status = "failed"
            result.error_step = step_name
            result.error_message = str(e)
            result.steps_failed.append(step_name)
            raise

    async def _step_parse(
        self,
        document: Document,
        version: DocumentVersion,
        file_data: bytes,
        result: DigestResult,
    ) -> None:
        """Parse document to extract text content."""
        step_name = DigestStep.PARSE.value

        try:
            from evidence_repository.digestion.parsers import parse_document

            text, metadata = await parse_document(
                file_data,
                document.content_type,
                document.filename,
            )

            version.extracted_text = text
            version.extracted_at = datetime.utcnow()
            version.page_count = metadata.get("page_count")
            await self.db.flush()

            result.text_length = len(text)
            result.page_count = metadata.get("page_count")
            result.steps_completed.append(step_name)
            result.step_results[step_name] = {
                "text_length": len(text),
                "page_count": metadata.get("page_count"),
                "parser": metadata.get("parser"),
            }

        except Exception as e:
            logger.warning(f"Parsing failed for {document.filename}: {e}")
            result.steps_failed.append(step_name)
            result.step_results[step_name] = {"error": str(e)}
            # Don't fail the whole pipeline - continue with empty text

    async def _step_extract_metadata(
        self,
        document: Document,
        version: DocumentVersion,
        result: DigestResult,
        openai_api_key: str | None = None,
    ) -> None:
        """Extract metadata using LLM."""
        step_name = DigestStep.EXTRACT_METADATA.value

        if not version.extracted_text:
            result.steps_failed.append(step_name)
            result.step_results[step_name] = {"error": "no_text_to_analyze"}
            return

        try:
            from evidence_repository.digestion.metadata_extractor import extract_metadata

            # Try to get OpenAI key from multiple sources:
            # 1. Passed parameter
            # 2. Database-stored integration key
            # 3. Environment variable via settings
            api_key = openai_api_key
            if not api_key:
                try:
                    from evidence_repository.models.integration_key import IntegrationProvider
                    from evidence_repository.services.integration_key_service import IntegrationKeyService

                    service = IntegrationKeyService(self.db)
                    api_key = await service.get_provider_key(IntegrationProvider.OPENAI, "api_key")
                    if api_key:
                        logger.info("Using OpenAI key from database")
                except Exception as e:
                    logger.debug(f"Could not get OpenAI key from database: {e}")

            # Fall back to environment variable
            if not api_key:
                api_key = self._settings.openai_api_key
                if api_key:
                    logger.info("Using OpenAI key from environment variable")

            metadata = await extract_metadata(
                text=version.extracted_text[:10000],  # Limit context
                filename=document.filename,
                openai_api_key=api_key,
            )

            # Update document with extracted metadata
            document.metadata_ = {
                **document.metadata_,
                "extracted": metadata,
            }
            await self.db.flush()

            result.extracted_metadata = metadata
            result.steps_completed.append(step_name)
            result.step_results[step_name] = metadata

        except Exception as e:
            logger.warning(f"Metadata extraction failed: {e}")
            result.steps_failed.append(step_name)
            result.step_results[step_name] = {"error": str(e)}

    async def _step_build_sections(
        self,
        version: DocumentVersion,
        result: DigestResult,
    ) -> None:
        """Build sections (spans) from extracted text."""
        step_name = DigestStep.BUILD_SECTIONS.value

        if not version.extracted_text:
            result.steps_failed.append(step_name)
            result.step_results[step_name] = {"error": "no_text"}
            return

        try:
            from evidence_repository.digestion.section_builder import build_sections

            sections = await build_sections(
                db=self.db,
                version=version,
            )

            result.section_count = sections
            result.steps_completed.append(step_name)
            result.step_results[step_name] = {"sections_created": sections}

        except Exception as e:
            logger.warning(f"Section building failed: {e}")
            result.steps_failed.append(step_name)
            result.step_results[step_name] = {"error": str(e)}

    async def _step_generate_embeddings(
        self,
        version: DocumentVersion,
        result: DigestResult,
    ) -> None:
        """Generate embeddings for sections."""
        step_name = DigestStep.GENERATE_EMBEDDINGS.value

        try:
            from evidence_repository.digestion.embedding_generator import generate_embeddings

            count = await generate_embeddings(
                db=self.db,
                version=version,
            )

            result.embedding_count = count
            result.steps_completed.append(step_name)
            result.step_results[step_name] = {"embeddings_created": count}

        except Exception as e:
            logger.warning(f"Embedding generation failed: {e}")
            result.steps_failed.append(step_name)
            result.step_results[step_name] = {"error": str(e)}

    async def _step_assess_truthfulness(
        self,
        version: DocumentVersion,
        result: DigestResult,
    ) -> None:
        """Assess document truthfulness."""
        step_name = DigestStep.ASSESS_TRUTHFULNESS.value

        if not version.extracted_text:
            result.steps_failed.append(step_name)
            result.step_results[step_name] = {"error": "no_text"}
            return

        try:
            from evidence_repository.digestion.truthfulness import assess_truthfulness

            assessment = await assess_truthfulness(
                text=version.extracted_text[:15000],
            )

            # Store in version metadata
            version.metadata_ = {
                **version.metadata_,
                "truthfulness": assessment,
            }
            await self.db.flush()

            result.steps_completed.append(step_name)
            result.step_results[step_name] = assessment

        except Exception as e:
            logger.warning(f"Truthfulness assessment failed: {e}")
            result.steps_failed.append(step_name)
            result.step_results[step_name] = {"error": str(e)}


# =============================================================================
# Module-level convenience functions
# =============================================================================


async def digest_document(
    db: AsyncSession,
    file_data: bytes,
    filename: str,
    content_type: str,
    options: DigestOptions | None = None,
    storage=None,
) -> DigestResult:
    """Convenience function for single document digestion.

    Args:
        db: Async database session.
        file_data: Raw file content.
        filename: Original filename.
        content_type: MIME type.
        options: Processing options.
        storage: Storage backend (optional).

    Returns:
        DigestResult with processing results.
    """
    pipeline = DigestionPipeline(db=db, storage=storage)
    return await pipeline.digest(
        file_data=file_data,
        filename=filename,
        content_type=content_type,
        options=options,
    )


async def digest_pending_documents(
    db: AsyncSession,
    batch_size: int = 10,
    storage=None,
) -> list[DigestResult]:
    """Process pending documents from database queue.

    This function implements the database-as-queue pattern.
    It queries for documents with PENDING status and processes them.

    Args:
        db: Async database session.
        batch_size: Maximum documents to process.
        storage: Storage backend (optional).

    Returns:
        List of DigestResults for processed documents.
    """
    results = []

    # Find pending documents
    pending = await db.execute(
        select(DocumentVersion)
        .where(DocumentVersion.extraction_status == ExtractionStatus.PENDING)
        .order_by(DocumentVersion.created_at)
        .limit(batch_size)
    )
    versions = pending.scalars().all()

    if not versions:
        return results

    pipeline = DigestionPipeline(db=db, storage=storage)

    for version in versions:
        try:
            # Mark as processing
            version.extraction_status = ExtractionStatus.PROCESSING
            await db.flush()

            # Download file content
            file_data = await pipeline.storage.download(version.storage_path)

            # Get document
            doc_result = await db.execute(
                select(Document).where(Document.id == version.document_id)
            )
            document = doc_result.scalar_one()

            # Run parsing and subsequent steps
            result = DigestResult(
                document_id=document.id,
                version_id=version.id,
                started_at=datetime.utcnow(),
            )

            await pipeline._step_parse(document, version, file_data, result)
            await pipeline._step_build_sections(version, result)
            await pipeline._step_generate_embeddings(version, result)

            version.extraction_status = ExtractionStatus.COMPLETED
            await db.commit()

            result.status = "ready"
            result.completed_at = datetime.utcnow()
            results.append(result)

        except Exception as e:
            logger.error(f"Failed to process version {version.id}: {e}")
            version.extraction_status = ExtractionStatus.FAILED
            version.extraction_error = str(e)
            await db.commit()

            results.append(DigestResult(
                document_id=version.document_id,
                version_id=version.id,
                status="failed",
                error_message=str(e),
            ))

    return results
