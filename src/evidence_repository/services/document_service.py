"""Document business service layer."""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from evidence_repository.embeddings.service import EmbeddingService
from evidence_repository.extraction.service import ExtractionService
from evidence_repository.ingestion.service import IngestionService
from evidence_repository.models.document import Document, DocumentVersion, ExtractionStatus
from evidence_repository.storage.base import StorageBackend


class DocumentService:
    """High-level document operations combining ingestion, extraction, and embedding."""

    def __init__(self, db: AsyncSession, storage: StorageBackend):
        """Initialize document service.

        Args:
            db: Database session.
            storage: Storage backend.
        """
        self.db = db
        self.storage = storage
        self.ingestion = IngestionService(storage=storage, db=db)
        self.extraction = ExtractionService(storage=storage, db=db)
        self.embedding = EmbeddingService(db=db)

    async def upload_and_process(
        self,
        filename: str,
        content_type: str,
        data: bytes,
        metadata: dict | None = None,
        auto_extract: bool = True,
        auto_embed: bool = True,
    ) -> tuple[Document, DocumentVersion]:
        """Upload a document and optionally process it.

        This is the main entry point for document ingestion that handles
        the full pipeline: upload -> extraction -> embedding.

        Args:
            filename: Original filename.
            content_type: MIME type.
            data: File content.
            metadata: Optional metadata.
            auto_extract: Whether to automatically extract text.
            auto_embed: Whether to automatically generate embeddings.

        Returns:
            Tuple of (Document, DocumentVersion).
        """
        # Ingest document
        document, version = await self.ingestion.ingest_document(
            filename=filename,
            content_type=content_type,
            data=data,
            metadata=metadata,
        )

        # Auto-extract if requested and applicable
        if auto_extract:
            try:
                await self.extraction.extract_text(version)
            except Exception:
                pass  # Extraction failure is non-fatal

        # Auto-embed if extraction succeeded
        if auto_embed and version.extraction_status == ExtractionStatus.COMPLETED:
            try:
                await self.embedding.embed_document_version(version)
            except Exception:
                pass  # Embedding failure is non-fatal

        return document, version

    async def get_document_with_versions(
        self, document_id: uuid.UUID
    ) -> Document | None:
        """Get a document with all its versions loaded.

        Args:
            document_id: Document ID.

        Returns:
            Document with versions or None.
        """
        result = await self.db.execute(
            select(Document)
            .options(selectinload(Document.versions))
            .where(Document.id == document_id)
        )
        return result.scalar_one_or_none()

    async def reprocess_version(
        self,
        version: DocumentVersion,
        reextract: bool = True,
        reembed: bool = True,
    ) -> DocumentVersion:
        """Reprocess a document version.

        Useful when extraction or embedding settings change.

        Args:
            version: Document version to reprocess.
            reextract: Whether to re-run extraction.
            reembed: Whether to re-generate embeddings.

        Returns:
            Updated document version.
        """
        if reextract:
            await self.extraction.reprocess_version(version)

        if reembed and version.extraction_status == ExtractionStatus.COMPLETED:
            await self.embedding.embed_document_version(version, reprocess=True)

        return version

    async def search_by_content_hash(self, file_hash: str) -> Document | None:
        """Find a document by its content hash.

        Useful for deduplication.

        Args:
            file_hash: SHA-256 hash of file content.

        Returns:
            Document if found.
        """
        return await self.ingestion.find_by_hash(file_hash)

    async def get_version_text(self, version: DocumentVersion) -> str | None:
        """Get the extracted text for a version.

        Extracts on-demand if not yet extracted.

        Args:
            version: Document version.

        Returns:
            Extracted text or None if extraction fails.
        """
        if version.extracted_text:
            return version.extracted_text

        if version.extraction_status == ExtractionStatus.PENDING:
            try:
                await self.extraction.extract_text(version)
                return version.extracted_text
            except Exception:
                return None

        return None

    async def delete_document(
        self,
        document: Document,
        hard_delete: bool = False,
    ) -> None:
        """Delete a document.

        Args:
            document: Document to delete.
            hard_delete: If True, permanently delete. If False, soft delete.
        """
        if hard_delete:
            # Delete files from storage
            for version in document.versions:
                try:
                    await self.storage.delete(version.storage_path)
                except Exception:
                    pass

            # Delete from database
            await self.db.delete(document)
        else:
            await self.ingestion.soft_delete_document(document)

    async def restore_document(self, document: Document) -> None:
        """Restore a soft-deleted document.

        Args:
            document: Document to restore.
        """
        await self.ingestion.restore_document(document)
