"""Document ingestion service."""

import hashlib
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from evidence_repository.models.document import Document, DocumentVersion, ExtractionStatus
from evidence_repository.storage.base import StorageBackend


class IngestionService:
    """Service for ingesting documents into the repository.

    Handles:
    - File upload and storage
    - Document metadata creation
    - Version management
    - Deduplication via content hashing
    """

    def __init__(self, storage: StorageBackend, db: AsyncSession):
        """Initialize ingestion service.

        Args:
            storage: Storage backend for file storage.
            db: Database session.
        """
        self.storage = storage
        self.db = db

    @staticmethod
    def compute_file_hash(data: bytes) -> str:
        """Compute SHA-256 hash of file content.

        Args:
            data: File content.

        Returns:
            Hex-encoded SHA-256 hash.
        """
        return hashlib.sha256(data).hexdigest()

    def generate_storage_path(
        self,
        document_id: uuid.UUID,
        version_number: int,
        filename: str,
    ) -> str:
        """Generate a storage path for a document version.

        Path format: documents/{document_id}/v{version_number}/{filename}

        Args:
            document_id: Document UUID.
            version_number: Version number.
            filename: Original filename.

        Returns:
            Storage path string.
        """
        # Sanitize filename
        safe_filename = "".join(
            c for c in filename if c.isalnum() or c in "._-"
        ).strip()
        if not safe_filename:
            safe_filename = "document"

        return f"documents/{document_id}/v{version_number}/{safe_filename}"

    async def find_by_hash(self, file_hash: str) -> Document | None:
        """Find an existing document by its content hash.

        Args:
            file_hash: SHA-256 hash of file content.

        Returns:
            Document if found, None otherwise.
        """
        from sqlalchemy.orm import selectinload
        result = await self.db.execute(
            select(Document)
            .options(selectinload(Document.versions))
            .where(
                Document.file_hash == file_hash,
                Document.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def ingest_document(
        self,
        filename: str,
        content_type: str,
        data: bytes,
        metadata: dict | None = None,
        profile_code: str = "general",
    ) -> tuple[Document, DocumentVersion]:
        """Ingest a new document into the repository.

        Args:
            filename: Original filename.
            content_type: MIME type.
            data: File content.
            metadata: Optional document metadata.
            profile_code: Industry profile for extraction (vc, pharma, insurance, general).

        Returns:
            Tuple of (Document, DocumentVersion).
        """
        file_hash = self.compute_file_hash(data)

        # Check for existing document with same hash
        existing = await self.find_by_hash(file_hash)
        if existing:
            # Update profile if different
            if existing.profile_code != profile_code:
                existing.profile_code = profile_code
                await self.db.flush()
            # Return existing document with its latest version
            return existing, existing.latest_version  # type: ignore

        # Create new document
        document = Document(
            filename=filename,
            original_filename=filename,
            content_type=content_type,
            file_hash=file_hash,
            profile_code=profile_code,
            metadata_=metadata or {},
        )
        self.db.add(document)
        await self.db.flush()  # Get document ID

        # Create first version
        version = await self.create_version(
            document=document,
            data=data,
            content_type=content_type,
        )

        return document, version

    async def create_version(
        self,
        document: Document,
        data: bytes,
        content_type: str,
        metadata: dict | None = None,
    ) -> DocumentVersion:
        """Create a new version of an existing document.

        Args:
            document: Parent document.
            data: File content.
            content_type: MIME type.
            metadata: Optional version metadata.

        Returns:
            New DocumentVersion.
        """
        # Determine next version number by querying the database
        # (async SQLAlchemy doesn't support lazy loading of relationships)
        from sqlalchemy import select, func
        from evidence_repository.models.document import DocumentVersion

        version_number = 1
        result = await self.db.execute(
            select(func.max(DocumentVersion.version_number))
            .where(DocumentVersion.document_id == document.id)
        )
        max_version = result.scalar()
        if max_version:
            version_number = max_version + 1

        # Generate storage path
        storage_path = self.generate_storage_path(
            document_id=document.id,
            version_number=version_number,
            filename=document.filename,
        )

        # Upload to storage
        await self.storage.upload(
            key=storage_path,
            data=data,
            content_type=content_type,
            metadata={"document_id": str(document.id), "version": str(version_number)},
        )

        # Create version record
        version = DocumentVersion(
            document_id=document.id,
            version_number=version_number,
            storage_path=storage_path,
            file_size=len(data),
            file_hash=self.compute_file_hash(data),
            extraction_status=ExtractionStatus.PENDING,
            metadata_=metadata or {},
        )
        self.db.add(version)
        await self.db.flush()

        return version

    async def soft_delete_document(self, document: Document) -> None:
        """Soft delete a document.

        Args:
            document: Document to delete.
        """
        document.deleted_at = datetime.utcnow()
        await self.db.flush()

    async def restore_document(self, document: Document) -> None:
        """Restore a soft-deleted document.

        Args:
            document: Document to restore.
        """
        document.deleted_at = None
        await self.db.flush()

    async def get_version_content(self, version: DocumentVersion) -> bytes:
        """Get the file content for a document version.

        Args:
            version: Document version.

        Returns:
            File content as bytes.
        """
        return await self.storage.download(version.storage_path)
