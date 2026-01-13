"""Service for bulk document ingestion operations."""

import mimetypes
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from evidence_repository.config import get_settings
from evidence_repository.ingestion.service import IngestionService
from evidence_repository.models.document import Document
from evidence_repository.models.ingestion import (
    IngestionBatch,
    IngestionBatchStatus,
    IngestionItem,
    IngestionItemStatus,
    IngestionSource,
)
from evidence_repository.models.job import JobType
from evidence_repository.models.project import Project, ProjectDocument
from evidence_repository.queue.job_queue import get_job_queue
from evidence_repository.storage.base import StorageBackend


class BulkIngestionService:
    """Service for managing bulk document ingestion.

    Handles:
    - Folder scanning and file discovery
    - Batch creation and tracking
    - Project attachment
    - Job enqueueing for async processing
    """

    def __init__(self, storage: StorageBackend, db: AsyncSession):
        """Initialize the bulk ingestion service.

        Args:
            storage: Storage backend for file operations.
            db: Database session.
        """
        self.storage = storage
        self.db = db
        self.settings = get_settings()

    async def scan_folder(
        self,
        folder_path: str,
        recursive: bool = True,
        allowed_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Scan a folder for files matching the allowed types.

        Args:
            folder_path: Path to the folder to scan.
            recursive: Whether to scan subfolders.
            allowed_types: List of allowed extensions (without dots).

        Returns:
            List of file info dictionaries with path, filename, size.
        """
        folder = Path(folder_path)
        if not folder.exists():
            raise ValueError(f"Folder not found: {folder_path}")
        if not folder.is_dir():
            raise ValueError(f"Not a directory: {folder_path}")

        # Normalize allowed types
        if allowed_types is None:
            allowed_types = [ext.lstrip(".") for ext in self.settings.supported_extensions]
        else:
            allowed_types = [ext.lower().lstrip(".") for ext in allowed_types]

        files = []
        max_size = self.settings.max_file_size_mb * 1024 * 1024

        if recursive:
            iterator = folder.rglob("*")
        else:
            iterator = folder.glob("*")

        for file_path in iterator:
            if not file_path.is_file():
                continue

            # Check extension
            ext = file_path.suffix.lower().lstrip(".")
            if ext not in allowed_types:
                continue

            # Check file size
            try:
                size = file_path.stat().st_size
            except OSError:
                continue

            if size > max_size:
                continue

            # Get content type
            content_type, _ = mimetypes.guess_type(str(file_path))

            files.append({
                "path": str(file_path),
                "filename": file_path.name,
                "size": size,
                "content_type": content_type or "application/octet-stream",
            })

        return files

    async def create_folder_batch(
        self,
        folder_path: str,
        files: list[dict[str, Any]],
        project_id: UUID | None = None,
        auto_process: bool = True,
        user_id: str | None = None,
    ) -> tuple[IngestionBatch, str]:
        """Create an ingestion batch for folder ingestion.

        Args:
            folder_path: Source folder path.
            files: List of files to ingest.
            project_id: Optional project to attach documents to.
            auto_process: Whether to auto-process documents.
            user_id: ID of the user initiating the ingestion.

        Returns:
            Tuple of (batch, job_id).
        """
        # Validate project if provided
        if project_id:
            result = await self.db.execute(
                select(Project).where(
                    Project.id == project_id,
                    Project.deleted_at.is_(None),
                )
            )
            project = result.scalar_one_or_none()
            if not project:
                raise ValueError(f"Project not found: {project_id}")

        # Create batch
        batch = IngestionBatch(
            name=f"Folder ingestion: {Path(folder_path).name}",
            source_type=IngestionSource.LOCAL_FOLDER,
            source_path=folder_path,
            status=IngestionBatchStatus.PENDING,
            total_items=len(files),
            created_by=user_id,
            metadata_={
                "project_id": str(project_id) if project_id else None,
                "auto_process": auto_process,
                "recursive": True,
            },
        )
        self.db.add(batch)
        await self.db.flush()

        # Create items for each file
        for file_info in files:
            item = IngestionItem(
                batch_id=batch.id,
                source_path=file_info["path"],
                source_filename=file_info["filename"],
                source_size=file_info["size"],
                content_type=file_info["content_type"],
                status=IngestionItemStatus.PENDING,
            )
            self.db.add(item)

        await self.db.flush()

        # Enqueue processing job
        job_queue = get_job_queue()
        job_id = job_queue.enqueue(
            job_type=JobType.BULK_FOLDER_INGEST,
            payload={
                "batch_id": str(batch.id),
                "folder_path": folder_path,
                "project_id": str(project_id) if project_id else None,
                "auto_process": auto_process,
                "user_id": user_id,
            },
            priority=-5,  # Lower priority for bulk operations
        )

        # Update batch with job ID
        batch.job_id = UUID(job_id) if job_id else None

        return batch, job_id

    async def create_url_batch(
        self,
        url: str,
        filename: str | None = None,
        project_id: UUID | None = None,
        auto_process: bool = True,
        user_id: str | None = None,
    ) -> tuple[IngestionBatch, IngestionItem, str]:
        """Create an ingestion batch for URL ingestion.

        Args:
            url: URL to download from.
            filename: Optional filename override.
            project_id: Optional project to attach documents to.
            auto_process: Whether to auto-process documents.
            user_id: ID of the user initiating the ingestion.

        Returns:
            Tuple of (batch, item, job_id).
        """
        # Validate project if provided
        if project_id:
            result = await self.db.execute(
                select(Project).where(
                    Project.id == project_id,
                    Project.deleted_at.is_(None),
                )
            )
            project = result.scalar_one_or_none()
            if not project:
                raise ValueError(f"Project not found: {project_id}")

        # Extract filename from URL if not provided
        if not filename:
            from urllib.parse import unquote, urlparse
            parsed = urlparse(url)
            filename = unquote(Path(parsed.path).name) or "downloaded_file"

        # Create batch
        batch = IngestionBatch(
            name=f"URL ingestion: {filename}",
            source_type=IngestionSource.URL,
            source_path=url,
            status=IngestionBatchStatus.PENDING,
            total_items=1,
            created_by=user_id,
            metadata_={
                "project_id": str(project_id) if project_id else None,
                "auto_process": auto_process,
                "original_url": url,
            },
        )
        self.db.add(batch)
        await self.db.flush()

        # Create item
        item = IngestionItem(
            batch_id=batch.id,
            source_path=url,
            source_filename=filename,
            status=IngestionItemStatus.PENDING,
        )
        self.db.add(item)
        await self.db.flush()

        # Enqueue processing job
        job_queue = get_job_queue()
        job_id = job_queue.enqueue(
            job_type=JobType.BULK_URL_INGEST,
            payload={
                "batch_id": str(batch.id),
                "item_id": str(item.id),
                "url": url,
                "filename": filename,
                "project_id": str(project_id) if project_id else None,
                "auto_process": auto_process,
                "user_id": user_id,
            },
            priority=0,  # Normal priority for single URL
        )

        # Update batch with job ID
        batch.job_id = UUID(job_id) if job_id else None

        return batch, item, job_id

    async def attach_to_project(
        self,
        document_id: UUID,
        project_id: UUID,
        user_id: str | None = None,
    ) -> ProjectDocument:
        """Attach a document to a project.

        Args:
            document_id: ID of the document to attach.
            project_id: ID of the project to attach to.
            user_id: ID of the user performing the attachment.

        Returns:
            The created ProjectDocument.
        """
        # Check if already attached
        result = await self.db.execute(
            select(ProjectDocument).where(
                ProjectDocument.project_id == project_id,
                ProjectDocument.document_id == document_id,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing

        # Create attachment
        project_doc = ProjectDocument(
            project_id=project_id,
            document_id=document_id,
            attached_by=user_id,
        )
        self.db.add(project_doc)
        await self.db.flush()

        return project_doc

    async def get_batch(self, batch_id: UUID) -> IngestionBatch | None:
        """Get an ingestion batch by ID.

        Args:
            batch_id: ID of the batch to retrieve.

        Returns:
            The batch if found, None otherwise.
        """
        result = await self.db.execute(
            select(IngestionBatch)
            .options(selectinload(IngestionBatch.items))
            .where(IngestionBatch.id == batch_id)
        )
        return result.scalar_one_or_none()

    async def list_batches(
        self,
        status: IngestionBatchStatus | None = None,
        source_type: IngestionSource | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[IngestionBatch]:
        """List ingestion batches with optional filtering.

        Args:
            status: Optional status filter.
            source_type: Optional source type filter.
            limit: Maximum number of batches to return.
            offset: Offset for pagination.

        Returns:
            List of matching batches.
        """
        query = select(IngestionBatch).order_by(IngestionBatch.created_at.desc())

        if status:
            query = query.where(IngestionBatch.status == status)
        if source_type:
            query = query.where(IngestionBatch.source_type == source_type)

        query = query.offset(offset).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def update_batch_progress(
        self,
        batch_id: UUID,
        processed: int | None = None,
        successful: int | None = None,
        failed: int | None = None,
        skipped: int | None = None,
    ) -> None:
        """Update batch progress counters.

        Args:
            batch_id: ID of the batch to update.
            processed: New processed count (or increment if None).
            successful: Successful count.
            failed: Failed count.
            skipped: Skipped count.
        """
        result = await self.db.execute(
            select(IngestionBatch).where(IngestionBatch.id == batch_id)
        )
        batch = result.scalar_one_or_none()
        if not batch:
            return

        if processed is not None:
            batch.processed_items = processed
        if successful is not None:
            batch.successful_items = successful
        if failed is not None:
            batch.failed_items = failed
        if skipped is not None:
            batch.skipped_items = skipped

        await self.db.flush()

    async def complete_batch(
        self,
        batch_id: UUID,
        status: IngestionBatchStatus,
    ) -> None:
        """Mark a batch as complete.

        Args:
            batch_id: ID of the batch to complete.
            status: Final status.
        """
        result = await self.db.execute(
            select(IngestionBatch).where(IngestionBatch.id == batch_id)
        )
        batch = result.scalar_one_or_none()
        if not batch:
            return

        batch.status = status
        batch.completed_at = datetime.now(timezone.utc)

        await self.db.flush()
