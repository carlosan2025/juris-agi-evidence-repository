"""Safe document deletion with tracked cascading.

This module implements a multi-step deletion process that:
1. Creates deletion tasks for each resource
2. Processes tasks in dependency order
3. Tracks progress and handles failures
4. Maintains full audit trail
"""

import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from evidence_repository.models import (
    DeletionStatus,
    DeletionTask,
    DeletionTaskStatus,
    DeletionTaskType,
    Document,
    DocumentVersion,
    EmbeddingChunk,
    FactClaim,
    FactConstraint,
    FactMetric,
    FactRisk,
    QualityConflict,
    QualityOpenQuestion,
    Span,
    TASK_TYPE_ORDER,
)
from evidence_repository.models.extraction import ExtractionRun
from evidence_repository.models.project import ProjectDocument
from evidence_repository.storage.base import StorageBackend

logger = logging.getLogger(__name__)


async def create_deletion_tasks(
    db: AsyncSession,
    document: Document,
    user_id: str,
) -> list[DeletionTask]:
    """Create deletion tasks for all resources associated with a document.

    Args:
        db: Database session
        document: Document to delete
        user_id: User requesting deletion

    Returns:
        List of created DeletionTask records
    """
    tasks: list[DeletionTask] = []
    order = 0

    # Mark document as being prepared for deletion
    document.deletion_status = DeletionStatus.MARKED_FOR_DELETION
    document.deletion_requested_at = datetime.utcnow()
    document.deletion_requested_by = user_id
    document.deletion_error = None

    # Process each version
    for version in document.versions:
        version_id = version.id

        # Task 1: Storage file
        if version.storage_path:
            order += 1
            tasks.append(
                DeletionTask(
                    id=uuid.uuid4(),
                    document_id=document.id,
                    version_id=version_id,
                    task_type=DeletionTaskType.STORAGE_FILE,
                    resource_id=version.storage_path,
                    resource_count=1,
                    processing_order=order,
                    status=DeletionTaskStatus.PENDING,
                )
            )

        # Task 2: Embedding chunks (count them for batch delete)
        embedding_count = await db.scalar(
            select(func.count()).where(EmbeddingChunk.document_version_id == version_id)
        )
        if embedding_count and embedding_count > 0:
            order += 1
            tasks.append(
                DeletionTask(
                    id=uuid.uuid4(),
                    document_id=document.id,
                    version_id=version_id,
                    task_type=DeletionTaskType.EMBEDDING_CHUNKS,
                    resource_id=str(version_id),
                    resource_count=embedding_count,
                    processing_order=order,
                    status=DeletionTaskStatus.PENDING,
                )
            )

        # Task 3: Spans (count them)
        span_count = await db.scalar(
            select(func.count()).where(Span.document_version_id == version_id)
        )
        if span_count and span_count > 0:
            order += 1
            tasks.append(
                DeletionTask(
                    id=uuid.uuid4(),
                    document_id=document.id,
                    version_id=version_id,
                    task_type=DeletionTaskType.SPANS,
                    resource_id=str(version_id),
                    resource_count=span_count,
                    processing_order=order,
                    status=DeletionTaskStatus.PENDING,
                )
            )

        # Task 4: Extraction runs
        extraction_count = await db.scalar(
            select(func.count()).where(ExtractionRun.document_version_id == version_id)
        )
        if extraction_count and extraction_count > 0:
            order += 1
            tasks.append(
                DeletionTask(
                    id=uuid.uuid4(),
                    document_id=document.id,
                    version_id=version_id,
                    task_type=DeletionTaskType.EXTRACTION_RUNS,
                    resource_id=str(version_id),
                    resource_count=extraction_count,
                    processing_order=order,
                    status=DeletionTaskStatus.PENDING,
                )
            )

    # Document-level tasks (not version-specific)

    # Facts tables
    for task_type, model in [
        (DeletionTaskType.FACTS_CLAIMS, FactClaim),
        (DeletionTaskType.FACTS_METRICS, FactMetric),
        (DeletionTaskType.FACTS_CONSTRAINTS, FactConstraint),
        (DeletionTaskType.FACTS_RISKS, FactRisk),
    ]:
        count = await db.scalar(
            select(func.count()).where(model.document_id == document.id)
        )
        if count and count > 0:
            order += 1
            tasks.append(
                DeletionTask(
                    id=uuid.uuid4(),
                    document_id=document.id,
                    version_id=None,
                    task_type=task_type,
                    resource_id=str(document.id),
                    resource_count=count,
                    processing_order=order,
                    status=DeletionTaskStatus.PENDING,
                )
            )

    # Quality tables
    for task_type, model in [
        (DeletionTaskType.QUALITY_CONFLICTS, QualityConflict),
        (DeletionTaskType.QUALITY_QUESTIONS, QualityOpenQuestion),
    ]:
        count = await db.scalar(
            select(func.count()).where(model.document_id == document.id)
        )
        if count and count > 0:
            order += 1
            tasks.append(
                DeletionTask(
                    id=uuid.uuid4(),
                    document_id=document.id,
                    version_id=None,
                    task_type=task_type,
                    resource_id=str(document.id),
                    resource_count=count,
                    processing_order=order,
                    status=DeletionTaskStatus.PENDING,
                )
            )

    # Project associations
    project_count = await db.scalar(
        select(func.count()).where(ProjectDocument.document_id == document.id)
    )
    if project_count and project_count > 0:
        order += 1
        tasks.append(
            DeletionTask(
                id=uuid.uuid4(),
                document_id=document.id,
                version_id=None,
                task_type=DeletionTaskType.PROJECT_DOCUMENTS,
                resource_id=str(document.id),
                resource_count=project_count,
                processing_order=order,
                status=DeletionTaskStatus.PENDING,
            )
        )

    # Document versions (final version-level cleanup)
    version_count = len(document.versions)
    if version_count > 0:
        order += 1
        tasks.append(
            DeletionTask(
                id=uuid.uuid4(),
                document_id=document.id,
                version_id=None,
                task_type=DeletionTaskType.DOCUMENT_VERSIONS,
                resource_id=str(document.id),
                resource_count=version_count,
                processing_order=order,
                status=DeletionTaskStatus.PENDING,
            )
        )

    # Final task: Document record itself
    order += 1
    tasks.append(
        DeletionTask(
            id=uuid.uuid4(),
            document_id=document.id,
            version_id=None,
            task_type=DeletionTaskType.DOCUMENT_RECORD,
            resource_id=str(document.id),
            resource_count=1,
            processing_order=order,
            status=DeletionTaskStatus.PENDING,
        )
    )

    # Add all tasks to session
    for task in tasks:
        db.add(task)

    await db.flush()

    logger.info(
        f"Created {len(tasks)} deletion tasks for document {document.id} "
        f"({document.original_filename})"
    )

    return tasks


async def process_deletion_tasks(
    db: AsyncSession,
    document_id: uuid.UUID,
    storage: StorageBackend,
) -> dict[str, Any]:
    """Process all pending deletion tasks for a document.

    Args:
        db: Database session
        document_id: Document ID to process
        storage: Storage backend for file deletion

    Returns:
        Status dict with completion info
    """
    # Load document
    document = await db.get(Document, document_id)
    if not document:
        return {"error": "Document not found", "document_id": str(document_id)}

    # Check if already fully deleted
    if document.deletion_status == DeletionStatus.DELETED:
        return {"status": "already_deleted", "document_id": str(document_id)}

    # Mark as actively deleting
    document.deletion_status = DeletionStatus.DELETING_RESOURCES
    await db.commit()

    # Get pending tasks in order
    result = await db.execute(
        select(DeletionTask)
        .where(DeletionTask.document_id == document_id)
        .where(DeletionTask.status.in_([DeletionTaskStatus.PENDING, DeletionTaskStatus.FAILED]))
        .order_by(DeletionTask.processing_order)
    )
    tasks = result.scalars().all()

    completed = 0
    failed = 0

    for task in tasks:
        try:
            # Mark as in progress
            task.status = DeletionTaskStatus.IN_PROGRESS
            task.started_at = datetime.utcnow()
            await db.commit()

            # Execute the deletion
            await _execute_deletion_task(db, task, storage)

            # Mark as completed
            task.status = DeletionTaskStatus.COMPLETED
            task.completed_at = datetime.utcnow()
            task.error_message = None
            await db.commit()

            completed += 1
            logger.info(f"Completed deletion task {task.task_type.value} for document {document_id}")

        except Exception as e:
            # Mark as failed
            task.status = DeletionTaskStatus.FAILED
            task.error_message = str(e)
            task.retry_count += 1
            await db.commit()

            failed += 1
            logger.error(f"Deletion task {task.task_type.value} failed: {e}")

            # Stop on first failure
            document.deletion_status = DeletionStatus.DELETION_FAILED
            document.deletion_error = f"Task {task.task_type.value} failed: {e}"
            await db.commit()

            return {
                "status": "failed",
                "document_id": str(document_id),
                "failed_task": task.task_type.value,
                "error": str(e),
                "completed": completed,
                "failed": failed,
            }

    # All tasks completed - mark document as deleted
    document.deletion_status = DeletionStatus.DELETED
    document.deletion_completed_at = datetime.utcnow()
    document.deleted_at = datetime.utcnow()  # Also set soft-delete timestamp
    document.deletion_error = None
    await db.commit()

    logger.info(f"Document {document_id} fully deleted ({completed} tasks completed)")

    return {
        "status": "deleted",
        "document_id": str(document_id),
        "completed": completed,
        "failed": failed,
    }


async def _execute_deletion_task(
    db: AsyncSession,
    task: DeletionTask,
    storage: StorageBackend,
) -> None:
    """Execute a single deletion task.

    Args:
        db: Database session
        task: Task to execute
        storage: Storage backend for file deletion
    """
    task_type = task.task_type

    if task_type == DeletionTaskType.STORAGE_FILE:
        # Delete file from storage (R2/S3)
        try:
            file_uri = storage._key_to_uri(task.resource_id)
            await storage.delete(file_uri)
        except Exception as e:
            # File might not exist - log but don't fail
            if "not found" in str(e).lower() or "404" in str(e):
                logger.warning(f"File not found (already deleted?): {task.resource_id}")
            else:
                raise

    elif task_type == DeletionTaskType.EMBEDDING_CHUNKS:
        # Delete embedding chunks for version
        await db.execute(
            delete(EmbeddingChunk).where(
                EmbeddingChunk.document_version_id == uuid.UUID(task.resource_id)
            )
        )

    elif task_type == DeletionTaskType.SPANS:
        # Delete spans for version (cascades to claims/metrics via SQLAlchemy)
        await db.execute(
            delete(Span).where(Span.document_version_id == uuid.UUID(task.resource_id))
        )

    elif task_type == DeletionTaskType.EXTRACTION_RUNS:
        # Delete extraction runs for version
        await db.execute(
            delete(ExtractionRun).where(
                ExtractionRun.document_version_id == uuid.UUID(task.resource_id)
            )
        )

    elif task_type == DeletionTaskType.FACTS_CLAIMS:
        await db.execute(
            delete(FactClaim).where(FactClaim.document_id == uuid.UUID(task.resource_id))
        )

    elif task_type == DeletionTaskType.FACTS_METRICS:
        await db.execute(
            delete(FactMetric).where(FactMetric.document_id == uuid.UUID(task.resource_id))
        )

    elif task_type == DeletionTaskType.FACTS_CONSTRAINTS:
        await db.execute(
            delete(FactConstraint).where(
                FactConstraint.document_id == uuid.UUID(task.resource_id)
            )
        )

    elif task_type == DeletionTaskType.FACTS_RISKS:
        await db.execute(
            delete(FactRisk).where(FactRisk.document_id == uuid.UUID(task.resource_id))
        )

    elif task_type == DeletionTaskType.QUALITY_CONFLICTS:
        await db.execute(
            delete(QualityConflict).where(
                QualityConflict.document_id == uuid.UUID(task.resource_id)
            )
        )

    elif task_type == DeletionTaskType.QUALITY_QUESTIONS:
        await db.execute(
            delete(QualityOpenQuestion).where(
                QualityOpenQuestion.document_id == uuid.UUID(task.resource_id)
            )
        )

    elif task_type == DeletionTaskType.PROJECT_DOCUMENTS:
        await db.execute(
            delete(ProjectDocument).where(
                ProjectDocument.document_id == uuid.UUID(task.resource_id)
            )
        )

    elif task_type == DeletionTaskType.DOCUMENT_VERSIONS:
        await db.execute(
            delete(DocumentVersion).where(
                DocumentVersion.document_id == uuid.UUID(task.resource_id)
            )
        )

    elif task_type == DeletionTaskType.DOCUMENT_RECORD:
        # Final deletion - remove the document record
        # Note: We keep the record but mark it as DELETED for audit trail
        # The actual DB record deletion happens via a separate cleanup job
        # For now, we just ensure deletion_status = DELETED which was set by caller
        pass

    # Flush changes
    await db.flush()


async def get_deletion_status(
    db: AsyncSession,
    document_id: uuid.UUID,
) -> dict[str, Any]:
    """Get detailed deletion status for a document.

    Args:
        db: Database session
        document_id: Document ID

    Returns:
        Status dict with task details
    """
    document = await db.get(Document, document_id)
    if not document:
        return {"error": "Document not found", "document_id": str(document_id)}

    # Get task counts by status
    result = await db.execute(
        select(DeletionTask.status, func.count())
        .where(DeletionTask.document_id == document_id)
        .group_by(DeletionTask.status)
    )
    status_counts = {row[0].value: row[1] for row in result.all()}

    # Get task details
    result = await db.execute(
        select(DeletionTask)
        .where(DeletionTask.document_id == document_id)
        .order_by(DeletionTask.processing_order)
    )
    tasks = result.scalars().all()

    return {
        "document_id": str(document_id),
        "filename": document.original_filename,
        "deletion_status": document.deletion_status.value,
        "deletion_requested_at": (
            document.deletion_requested_at.isoformat()
            if document.deletion_requested_at
            else None
        ),
        "deletion_requested_by": document.deletion_requested_by,
        "deletion_completed_at": (
            document.deletion_completed_at.isoformat()
            if document.deletion_completed_at
            else None
        ),
        "deletion_error": document.deletion_error,
        "task_summary": {
            "total": len(tasks),
            "pending": status_counts.get("pending", 0),
            "in_progress": status_counts.get("in_progress", 0),
            "completed": status_counts.get("completed", 0),
            "failed": status_counts.get("failed", 0),
            "skipped": status_counts.get("skipped", 0),
        },
        "tasks": [
            {
                "id": str(task.id),
                "type": task.task_type.value,
                "resource_id": task.resource_id,
                "resource_count": task.resource_count,
                "status": task.status.value,
                "error_message": task.error_message,
                "retry_count": task.retry_count,
                "processing_order": task.processing_order,
            }
            for task in tasks
        ],
    }


async def retry_failed_deletion(
    db: AsyncSession,
    document_id: uuid.UUID,
    storage: StorageBackend,
) -> dict[str, Any]:
    """Retry deletion for a document with failed tasks.

    Args:
        db: Database session
        document_id: Document ID
        storage: Storage backend

    Returns:
        Status dict from process_deletion_tasks
    """
    document = await db.get(Document, document_id)
    if not document:
        return {"error": "Document not found", "document_id": str(document_id)}

    if document.deletion_status not in [
        DeletionStatus.DELETION_FAILED,
        DeletionStatus.MARKED_FOR_DELETION,
    ]:
        return {
            "error": "Document is not in a retryable state",
            "document_id": str(document_id),
            "current_status": document.deletion_status.value,
        }

    # Reset failed tasks to pending
    await db.execute(
        DeletionTask.__table__.update()
        .where(DeletionTask.document_id == document_id)
        .where(DeletionTask.status == DeletionTaskStatus.FAILED)
        .values(status=DeletionTaskStatus.PENDING, error_message=None)
    )
    await db.commit()

    # Re-run deletion
    return await process_deletion_tasks(db, document_id, storage)
