"""Text extraction orchestration service."""

import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from evidence_repository.config import get_settings
from evidence_repository.extraction.lovepdf import LovePDFClient, LovePDFError
from evidence_repository.models.document import DocumentVersion, ExtractionStatus
from evidence_repository.storage.base import StorageBackend

logger = logging.getLogger(__name__)


class ExtractionService:
    """Service for orchestrating text extraction from documents.

    Supports multiple document types:
    - PDF: Uses LovePDF API (canonical) or pypdf fallback
    - Plain text: Direct read
    - Other formats: Extensible for future support
    """

    SUPPORTED_CONTENT_TYPES = {
        "application/pdf": "pdf",
        "text/plain": "text",
        "text/markdown": "text",
        "text/csv": "text",
    }

    def __init__(
        self,
        storage: StorageBackend,
        db: AsyncSession,
        lovepdf_client: LovePDFClient | None = None,
    ):
        """Initialize extraction service.

        Args:
            storage: Storage backend for file access.
            db: Database session.
            lovepdf_client: Optional LovePDF client (created from settings if not provided).
        """
        self.storage = storage
        self.db = db

        if lovepdf_client:
            self.lovepdf = lovepdf_client
        else:
            settings = get_settings()
            self.lovepdf = LovePDFClient(
                public_key=settings.lovepdf_public_key,
                secret_key=settings.lovepdf_secret_key,
            )

    async def extract_text(self, version: DocumentVersion) -> str:
        """Extract text from a document version.

        Updates the version's extraction status and stores the result.

        Args:
            version: Document version to extract text from.

        Returns:
            Extracted text.

        Raises:
            ValueError: If content type is not supported.
        """
        # Mark as processing
        version.extraction_status = ExtractionStatus.PROCESSING
        await self.db.flush()

        try:
            # Get content type from parent document
            content_type = version.document.content_type
            doc_type = self.SUPPORTED_CONTENT_TYPES.get(content_type)

            if not doc_type:
                raise ValueError(f"Unsupported content type: {content_type}")

            # Download file content
            data = await self.storage.download(version.storage_path)

            # Extract based on type
            if doc_type == "pdf":
                text, page_count = await self._extract_pdf(data)
                version.page_count = page_count
            elif doc_type == "text":
                text = await self._extract_text(data)
            else:
                raise ValueError(f"Unknown document type: {doc_type}")

            # Update version with results
            version.extracted_text = text
            version.extraction_status = ExtractionStatus.COMPLETED
            version.extracted_at = datetime.utcnow()
            version.extraction_error = None
            await self.db.flush()

            logger.info(
                f"Extracted text from version {version.id}: "
                f"{len(text)} chars, {version.page_count or 0} pages"
            )

            return text

        except Exception as e:
            # Mark as failed
            version.extraction_status = ExtractionStatus.FAILED
            version.extraction_error = str(e)
            await self.db.flush()

            logger.error(f"Extraction failed for version {version.id}: {e}")
            raise

    async def _extract_pdf(self, data: bytes) -> tuple[str, int]:
        """Extract text from PDF using LovePDF or fallback.

        Args:
            data: PDF file content.

        Returns:
            Tuple of (extracted text, page count).
        """
        settings = get_settings()

        # Try LovePDF if configured
        if settings.lovepdf_public_key and settings.lovepdf_secret_key:
            try:
                result = await self.lovepdf.extract_text(data)
                return result.text, result.page_count
            except LovePDFError as e:
                logger.warning(f"LovePDF extraction failed, trying fallback: {e}")

        # Fallback to pypdf
        result = await self.lovepdf.extract_text_fallback(data)
        return result.text, result.page_count

    async def _extract_text(self, data: bytes) -> str:
        """Extract text from plain text files.

        Args:
            data: File content.

        Returns:
            Decoded text content.
        """
        # Try common encodings
        for encoding in ["utf-8", "latin-1", "cp1252"]:
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue

        # Last resort: decode with replacement
        return data.decode("utf-8", errors="replace")

    async def reprocess_version(self, version: DocumentVersion) -> str:
        """Re-run extraction on a document version.

        Useful when extraction settings change or to retry failed extractions.

        Args:
            version: Document version to reprocess.

        Returns:
            Newly extracted text.
        """
        # Reset status
        version.extracted_text = None
        version.extraction_status = ExtractionStatus.PENDING
        version.extraction_error = None
        version.extracted_at = None
        await self.db.flush()

        return await self.extract_text(version)
