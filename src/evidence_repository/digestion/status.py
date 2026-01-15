"""Processing status and monitoring utilities.

Provides status queries and monitoring endpoints for the digestion pipeline.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from evidence_repository.models.document import Document, DocumentVersion, ExtractionStatus

logger = logging.getLogger(__name__)


@dataclass
class ProcessingStatus:
    """Current processing status summary."""

    pending_count: int = 0
    processing_count: int = 0
    completed_count: int = 0
    failed_count: int = 0
    total_count: int = 0

    # Recent activity
    processed_last_hour: int = 0
    processed_last_24h: int = 0
    failed_last_hour: int = 0

    # Oldest pending
    oldest_pending_at: datetime | None = None
    oldest_pending_id: str | None = None

    # Timing estimates
    avg_processing_time_ms: float | None = None
    estimated_queue_clear_time: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "queue": {
                "pending": self.pending_count,
                "processing": self.processing_count,
                "completed": self.completed_count,
                "failed": self.failed_count,
                "total": self.total_count,
            },
            "recent_activity": {
                "processed_last_hour": self.processed_last_hour,
                "processed_last_24h": self.processed_last_24h,
                "failed_last_hour": self.failed_last_hour,
            },
            "oldest_pending": {
                "created_at": self.oldest_pending_at.isoformat() if self.oldest_pending_at else None,
                "version_id": self.oldest_pending_id,
            },
            "performance": {
                "avg_processing_time_ms": self.avg_processing_time_ms,
                "estimated_queue_clear_time": self.estimated_queue_clear_time,
            },
        }


async def get_processing_stats(db: AsyncSession) -> ProcessingStatus:
    """Get comprehensive processing statistics.

    Args:
        db: Async database session.

    Returns:
        ProcessingStatus with current queue and activity stats.
    """
    status = ProcessingStatus()
    now = datetime.utcnow()
    hour_ago = now - timedelta(hours=1)
    day_ago = now - timedelta(hours=24)

    # Get counts by status
    counts_result = await db.execute(
        select(
            DocumentVersion.extraction_status,
            func.count(DocumentVersion.id).label("count"),
        )
        .group_by(DocumentVersion.extraction_status)
    )

    for row in counts_result.fetchall():
        extraction_status, count = row
        if extraction_status == ExtractionStatus.PENDING:
            status.pending_count = count
        elif extraction_status == ExtractionStatus.PROCESSING:
            status.processing_count = count
        elif extraction_status == ExtractionStatus.COMPLETED:
            status.completed_count = count
        elif extraction_status == ExtractionStatus.FAILED:
            status.failed_count = count

    status.total_count = (
        status.pending_count +
        status.processing_count +
        status.completed_count +
        status.failed_count
    )

    # Get processed in last hour
    hour_result = await db.execute(
        select(func.count(DocumentVersion.id))
        .where(
            DocumentVersion.extraction_status == ExtractionStatus.COMPLETED,
            DocumentVersion.extracted_at >= hour_ago,
        )
    )
    status.processed_last_hour = hour_result.scalar() or 0

    # Get processed in last 24h
    day_result = await db.execute(
        select(func.count(DocumentVersion.id))
        .where(
            DocumentVersion.extraction_status == ExtractionStatus.COMPLETED,
            DocumentVersion.extracted_at >= day_ago,
        )
    )
    status.processed_last_24h = day_result.scalar() or 0

    # Get failed in last hour (using created_at since DocumentVersion has no updated_at)
    failed_result = await db.execute(
        select(func.count(DocumentVersion.id))
        .where(
            DocumentVersion.extraction_status == ExtractionStatus.FAILED,
            DocumentVersion.created_at >= hour_ago,
        )
    )
    status.failed_last_hour = failed_result.scalar() or 0

    # Get oldest pending
    oldest_result = await db.execute(
        select(DocumentVersion.id, DocumentVersion.created_at)
        .where(DocumentVersion.extraction_status == ExtractionStatus.PENDING)
        .order_by(DocumentVersion.created_at)
        .limit(1)
    )
    oldest = oldest_result.fetchone()
    if oldest:
        status.oldest_pending_id = str(oldest[0])
        status.oldest_pending_at = oldest[1]

    # Estimate queue clear time based on recent throughput
    if status.pending_count > 0 and status.processed_last_hour > 0:
        hours_to_clear = status.pending_count / status.processed_last_hour
        if hours_to_clear < 1:
            status.estimated_queue_clear_time = f"{int(hours_to_clear * 60)} minutes"
        elif hours_to_clear < 24:
            status.estimated_queue_clear_time = f"{hours_to_clear:.1f} hours"
        else:
            status.estimated_queue_clear_time = f"{hours_to_clear / 24:.1f} days"

    return status


async def get_queue_status(db: AsyncSession) -> dict[str, Any]:
    """Get simple queue status for health checks.

    This is a lightweight endpoint that just returns counts.

    Args:
        db: Async database session.

    Returns:
        Dictionary with queue counts.
    """
    counts_result = await db.execute(
        select(
            DocumentVersion.extraction_status,
            func.count(DocumentVersion.id).label("count"),
        )
        .group_by(DocumentVersion.extraction_status)
    )

    counts = {str(status.value): 0 for status in ExtractionStatus}
    for row in counts_result.fetchall():
        counts[str(row[0].value)] = row[1]

    return {
        "queue": counts,
        "timestamp": datetime.utcnow().isoformat(),
    }


async def get_version_status(
    db: AsyncSession,
    version_id: str,
) -> dict[str, Any] | None:
    """Get processing status for a specific version.

    Args:
        db: Async database session.
        version_id: Document version ID.

    Returns:
        Status dict or None if not found.
    """
    import uuid
    from sqlalchemy.orm import selectinload

    result = await db.execute(
        select(DocumentVersion)
        .options(selectinload(DocumentVersion.document))
        .where(DocumentVersion.id == uuid.UUID(version_id))
    )
    version = result.scalar_one_or_none()

    if not version:
        return None

    # Map processing_status to human-readable step names
    STEP_LABELS = {
        "pending": "Waiting to start",
        "uploaded": "File uploaded",
        "extracted": "Extracting text",
        "spans_built": "Building sections",
        "embedded": "Generating embeddings",
        "facts_extracted": "Extracting metadata",
        "quality_checked": "Complete",
        "failed": "Failed",
    }

    processing_step = version.processing_status.value if version.processing_status else "pending"
    step_label = STEP_LABELS.get(processing_step, processing_step)

    return {
        "version_id": str(version.id),
        "document_id": str(version.document_id),
        "filename": version.document.original_filename if version.document else None,
        "status": version.extraction_status.value,
        "processing_step": processing_step,
        "processing_step_label": step_label,
        "upload_status": version.upload_status.value if version.upload_status else None,
        "created_at": version.created_at.isoformat(),
        "extracted_at": version.extracted_at.isoformat() if version.extracted_at else None,
        "text_length": len(version.extracted_text) if version.extracted_text else 0,
        "page_count": version.page_count,
        "error": version.extraction_error,
    }


async def retry_failed_documents(
    db: AsyncSession,
    limit: int = 10,
    older_than_hours: int = 1,
) -> int:
    """Reset failed documents to pending for retry.

    Args:
        db: Async database session.
        limit: Maximum documents to retry.
        older_than_hours: Only retry documents older than this.

    Returns:
        Number of documents reset.
    """
    from sqlalchemy import update

    cutoff = datetime.utcnow() - timedelta(hours=older_than_hours)

    # Find failed documents (using created_at since DocumentVersion has no updated_at)
    result = await db.execute(
        select(DocumentVersion.id)
        .where(
            DocumentVersion.extraction_status == ExtractionStatus.FAILED,
            DocumentVersion.created_at < cutoff,
        )
        .limit(limit)
    )
    version_ids = [row[0] for row in result.fetchall()]

    if not version_ids:
        return 0

    # Reset to pending
    await db.execute(
        update(DocumentVersion)
        .where(DocumentVersion.id.in_(version_ids))
        .values(
            extraction_status=ExtractionStatus.PENDING,
            extraction_error=None,
        )
    )
    await db.commit()

    logger.info(f"Reset {len(version_ids)} failed documents to pending")
    return len(version_ids)


async def retry_single_document(
    db: AsyncSession,
    document_id: str,
) -> dict[str, Any]:
    """Reset a single document for reprocessing.

    Works for documents that are failed, stuck in processing, or pending.

    Args:
        db: Async database session.
        document_id: Document ID to retry.

    Returns:
        Status dict with result.
    """
    import uuid
    from sqlalchemy import update
    from sqlalchemy.orm import selectinload
    from evidence_repository.models.document import ProcessingStatus as DocProcessingStatus

    # Get document with versions
    result = await db.execute(
        select(Document)
        .options(selectinload(Document.versions))
        .where(Document.id == uuid.UUID(document_id))
    )
    document = result.scalar_one_or_none()

    if not document:
        return {"success": False, "error": "Document not found"}

    if not document.versions:
        return {"success": False, "error": "Document has no versions"}

    version = document.versions[0]  # Latest version

    # Check if already completed
    if version.extraction_status == ExtractionStatus.COMPLETED:
        return {
            "success": False,
            "error": "Document already completed. Use force=true to reprocess.",
            "status": version.extraction_status.value,
        }

    # Reset to pending for reprocessing
    version.extraction_status = ExtractionStatus.PENDING
    version.processing_status = DocProcessingStatus.UPLOADED
    version.extraction_error = None
    await db.commit()

    logger.info(f"Reset document {document_id} to pending for reprocessing")

    return {
        "success": True,
        "document_id": str(document.id),
        "version_id": str(version.id),
        "filename": document.original_filename,
        "message": "Document queued for reprocessing",
    }
