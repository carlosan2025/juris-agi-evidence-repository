"""Document management endpoints."""

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from evidence_repository.api.dependencies import User, get_current_user, get_storage
from evidence_repository.config import get_settings
from evidence_repository.db.session import get_db_session
from evidence_repository.extraction.service import ExtractionService
from evidence_repository.ingestion.service import IngestionService
from evidence_repository.models.audit import AuditAction, AuditLog
from evidence_repository.models.document import Document, DocumentVersion, ExtractionStatus, ProcessingStatus, UploadStatus
from evidence_repository.models.job import JobType
from evidence_repository.queue.job_queue import get_job_queue
from evidence_repository.schemas.common import PaginatedResponse
from evidence_repository.schemas.document import (
    ConfirmUploadRequest,
    ConfirmUploadResponse,
    DocumentResponse,
    DocumentUploadResponse,
    DocumentVersionResponse,
    ExtractionTriggerResponse,
    PresignedUploadRequest,
    PresignedUploadResponse,
    VersionUploadResponse,
)
from evidence_repository.schemas.quality import QualityAnalysisResponse
from evidence_repository.services.quality_analysis import QualityAnalysisService
from evidence_repository.storage.base import StorageBackend

router = APIRouter()


async def _write_audit_log(
    db: AsyncSession,
    action: AuditAction,
    entity_type: str,
    entity_id: uuid.UUID | None,
    actor_id: str | None,
    details: dict | None = None,
    request: Request | None = None,
) -> None:
    """Write an audit log entry."""
    ip_address = None
    user_agent = None
    if request:
        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")

    audit_log = AuditLog(
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_id=actor_id,
        details=details or {},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(audit_log)
    await db.flush()


@router.post(
    "",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload Document",
    description="""
Upload a new document to the repository.

The file is stored and a processing job is enqueued. Returns immediately
with document_id, version_id, and job_id for tracking.

No processing happens synchronously - use GET /jobs/{job_id} to track progress.
    """,
)
async def upload_document(
    request: Request,
    file: UploadFile = File(..., description="Document file to upload"),
    profile_code: str = Form(
        default="general",
        description="Industry profile for extraction: vc, pharma, insurance, or general",
    ),
    db: AsyncSession = Depends(get_db_session),
    storage: StorageBackend = Depends(get_storage),
    user: User = Depends(get_current_user),
) -> DocumentUploadResponse:
    """Upload a document for async processing."""
    settings = get_settings()

    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required",
        )

    # Check file extension
    from pathlib import Path
    extension = Path(file.filename).suffix.lower()
    if extension not in settings.supported_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: {extension}. Supported: {settings.supported_extensions}",
        )

    # Read file content
    content = await file.read()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty file",
        )

    # Check file size
    max_size = settings.max_file_size_mb * 1024 * 1024
    if len(content) > max_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large ({len(content)} bytes). Maximum: {max_size} bytes",
        )

    # Validate profile_code
    valid_profiles = {"general", "vc", "pharma", "insurance"}
    if profile_code not in valid_profiles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid profile_code: {profile_code}. Valid options: {', '.join(sorted(valid_profiles))}",
        )

    # Store file and create document/version records
    ingestion = IngestionService(storage=storage, db=db)
    document, version = await ingestion.ingest_document(
        filename=file.filename,
        content_type=file.content_type or "application/octet-stream",
        data=content,
        metadata={"uploaded_by": user.id},
        profile_code=profile_code,
    )

    # Write audit log for upload
    await _write_audit_log(
        db=db,
        action=AuditAction.DOCUMENT_UPLOAD,
        entity_type="document",
        entity_id=document.id,
        actor_id=user.id,
        details={
            "filename": file.filename,
            "content_type": file.content_type,
            "file_size": len(content),
            "version_id": str(version.id),
            "version_number": version.version_number,
        },
        request=request,
    )

    await db.commit()

    # Enqueue processing job (use PROCESS_DOCUMENT_VERSION for the idempotent 5-step pipeline)
    job_queue = get_job_queue()
    job_id = job_queue.enqueue(
        job_type=JobType.PROCESS_DOCUMENT_VERSION,
        payload={
            "version_id": str(version.id),
            "profile_code": profile_code,
            "extraction_level": 2,  # Standard level by default
        },
        priority=0,
    )

    return DocumentUploadResponse(
        document_id=document.id,
        version_id=version.id,
        job_id=job_id,
        message=f"Document '{file.filename}' stored and queued for processing (profile: {profile_code})",
    )


@router.get(
    "",
    response_model=PaginatedResponse[DocumentResponse],
    summary="List Documents",
    description="List all documents with pagination.",
)
async def list_documents(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    include_deleted: bool = Query(default=False, description="Include soft-deleted documents"),
    include_deleting: bool = Query(default=False, description="Include documents being deleted"),
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> PaginatedResponse[DocumentResponse]:
    """List documents with pagination."""
    from evidence_repository.models.document import DeletionStatus

    # Build query
    query = select(Document).options(selectinload(Document.versions))

    if not include_deleted:
        query = query.where(Document.deleted_at.is_(None))
        # Also filter out fully deleted documents
        query = query.where(Document.deletion_status != DeletionStatus.DELETED)

    if not include_deleting:
        # Filter out documents being deleted (marked, deleting, or failed)
        query = query.where(
            Document.deletion_status.in_([DeletionStatus.ACTIVE, DeletionStatus.DELETION_FAILED])
            if include_deleted
            else Document.deletion_status == DeletionStatus.ACTIVE
        )

    # Count total
    count_query = select(func.count()).select_from(Document)
    if not include_deleted:
        count_query = count_query.where(Document.deleted_at.is_(None))
        count_query = count_query.where(Document.deletion_status != DeletionStatus.DELETED)
    if not include_deleting:
        count_query = count_query.where(
            Document.deletion_status.in_([DeletionStatus.ACTIVE, DeletionStatus.DELETION_FAILED])
            if include_deleted
            else Document.deletion_status == DeletionStatus.ACTIVE
        )
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Paginate
    query = query.order_by(Document.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    documents = result.scalars().all()

    return PaginatedResponse.create(
        items=[DocumentResponse.model_validate(d) for d in documents],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    summary="Get Document",
    description="Get document details by ID.",
)
async def get_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> DocumentResponse:
    """Get a document by ID."""
    result = await db.execute(
        select(Document)
        .options(selectinload(Document.versions))
        .where(Document.id == document_id)
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found",
        )

    return DocumentResponse.model_validate(document)


@router.post(
    "/{document_id}/versions",
    response_model=VersionUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload New Version",
    description="""
Upload a new version of an existing document.

The file is stored and a processing job is enqueued. Returns immediately
with document_id, version_id, version_number, and job_id for tracking.

No processing happens synchronously - use GET /jobs/{job_id} to track progress.
    """,
)
async def upload_document_version(
    document_id: uuid.UUID,
    request: Request,
    file: UploadFile = File(..., description="New version file"),
    db: AsyncSession = Depends(get_db_session),
    storage: StorageBackend = Depends(get_storage),
    user: User = Depends(get_current_user),
) -> VersionUploadResponse:
    """Upload a new version of an existing document."""
    settings = get_settings()

    # Get existing document
    result = await db.execute(
        select(Document)
        .options(selectinload(Document.versions))
        .where(Document.id == document_id, Document.deleted_at.is_(None))
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found",
        )

    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required",
        )

    # Check file extension
    from pathlib import Path
    extension = Path(file.filename).suffix.lower()
    if extension not in settings.supported_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: {extension}. Supported: {settings.supported_extensions}",
        )

    # Read file content
    content = await file.read()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty file",
        )

    # Check file size
    max_size = settings.max_file_size_mb * 1024 * 1024
    if len(content) > max_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large ({len(content)} bytes). Maximum: {max_size} bytes",
        )

    # Create new version
    ingestion = IngestionService(storage=storage, db=db)
    version = await ingestion.create_version(
        document=document,
        data=content,
        content_type=file.content_type or document.content_type,
        metadata={"uploaded_by": user.id},
    )

    # Write audit log for version creation
    await _write_audit_log(
        db=db,
        action=AuditAction.VERSION_CREATE,
        entity_type="document_version",
        entity_id=version.id,
        actor_id=user.id,
        details={
            "document_id": str(document_id),
            "filename": file.filename,
            "content_type": file.content_type,
            "file_size": len(content),
            "version_number": version.version_number,
        },
        request=request,
    )

    await db.commit()

    # Enqueue processing job (use PROCESS_DOCUMENT_VERSION for the idempotent 5-step pipeline)
    job_queue = get_job_queue()
    job_id = job_queue.enqueue(
        job_type=JobType.PROCESS_DOCUMENT_VERSION,
        payload={
            "version_id": str(version.id),
            "profile_code": document.profile_code,  # Use document's profile
            "extraction_level": 2,
        },
        priority=0,
    )

    return VersionUploadResponse(
        document_id=document.id,
        version_id=version.id,
        version_number=version.version_number,
        job_id=job_id,
        message=f"Version {version.version_number} stored and queued for processing (profile: {document.profile_code})",
    )


@router.get(
    "/{document_id}/versions",
    response_model=list[DocumentVersionResponse],
    summary="List Document Versions",
    description="List all versions of a document.",
)
async def list_document_versions(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> list[DocumentVersionResponse]:
    """List all versions of a document."""
    result = await db.execute(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == document_id)
        .order_by(DocumentVersion.version_number.desc())
    )
    versions = result.scalars().all()

    if not versions:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found or has no versions",
        )

    return [DocumentVersionResponse.model_validate(v) for v in versions]


@router.get(
    "/{document_id}/download",
    summary="Download Document",
    description="Download the latest version of a document.",
)
async def download_document(
    document_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
    storage: StorageBackend = Depends(get_storage),
    user: User = Depends(get_current_user),
) -> Response:
    """Download the latest version of a document."""
    # Get document with versions
    result = await db.execute(
        select(Document)
        .options(selectinload(Document.versions))
        .where(Document.id == document_id, Document.deleted_at.is_(None))
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found",
        )

    version = document.latest_version
    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} has no versions",
        )

    # Download from storage
    try:
        content = await storage.download(version.storage_path)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found in storage",
        )

    # Write audit log for download
    await _write_audit_log(
        db=db,
        action=AuditAction.DOCUMENT_DOWNLOAD,
        entity_type="document",
        entity_id=document_id,
        actor_id=user.id,
        details={
            "version_id": str(version.id),
            "version_number": version.version_number,
            "file_size": len(content),
        },
        request=request,
    )
    await db.commit()

    return Response(
        content=content,
        media_type=document.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{document.filename}"',
            "Content-Length": str(len(content)),
        },
    )


@router.get(
    "/{document_id}/versions/{version_id}/download",
    summary="Download Document Version",
    description="Download a specific version of a document.",
)
async def download_document_version(
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
    storage: StorageBackend = Depends(get_storage),
    user: User = Depends(get_current_user),
) -> Response:
    """Download a specific document version."""
    # Get version with document
    result = await db.execute(
        select(DocumentVersion)
        .options(selectinload(DocumentVersion.document))
        .where(
            DocumentVersion.id == version_id,
            DocumentVersion.document_id == document_id,
        )
    )
    version = result.scalar_one_or_none()

    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Version {version_id} not found for document {document_id}",
        )

    # Download from storage
    try:
        content = await storage.download(version.storage_path)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found in storage",
        )

    # Write audit log for download
    await _write_audit_log(
        db=db,
        action=AuditAction.DOCUMENT_DOWNLOAD,
        entity_type="document_version",
        entity_id=version_id,
        actor_id=user.id,
        details={
            "document_id": str(document_id),
            "version_number": version.version_number,
            "file_size": len(content),
        },
        request=request,
    )
    await db.commit()

    return Response(
        content=content,
        media_type=version.document.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{version.document.filename}"',
            "Content-Length": str(len(content)),
        },
    )


@router.post(
    "/{document_id}/extract",
    response_model=ExtractionTriggerResponse,
    summary="Trigger Extraction",
    description="Trigger text extraction for the latest version of a document.",
)
async def trigger_extraction(
    document_id: uuid.UUID,
    version_id: uuid.UUID | None = Query(default=None, description="Specific version to extract"),
    db: AsyncSession = Depends(get_db_session),
    storage: StorageBackend = Depends(get_storage),
    user: User = Depends(get_current_user),
) -> ExtractionTriggerResponse:
    """Trigger text extraction for a document."""
    # Get document with versions
    result = await db.execute(
        select(Document)
        .options(selectinload(Document.versions))
        .where(Document.id == document_id)
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found",
        )

    # Get target version
    if version_id:
        version = next((v for v in document.versions if v.id == version_id), None)
        if not version:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Version {version_id} not found",
            )
    else:
        version = document.latest_version
        if not version:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No versions found for document",
            )

    # Check if already extracted
    if version.extraction_status == ExtractionStatus.COMPLETED:
        return ExtractionTriggerResponse(
            document_id=document_id,
            version_id=version.id,
            status="completed",
            message="Extraction already completed",
        )

    if version.extraction_status == ExtractionStatus.PROCESSING:
        return ExtractionTriggerResponse(
            document_id=document_id,
            version_id=version.id,
            status="processing",
            message="Extraction already in progress",
        )

    # Start extraction
    extraction = ExtractionService(storage=storage, db=db)
    try:
        await extraction.extract_text(version)
        await db.commit()

        return ExtractionTriggerResponse(
            document_id=document_id,
            version_id=version.id,
            status="completed",
            message="Extraction completed successfully",
        )
    except Exception as e:
        await db.commit()  # Save the failed status
        return ExtractionTriggerResponse(
            document_id=document_id,
            version_id=version.id,
            status="failed",
            message=str(e),
        )


@router.post(
    "/{document_id}/retry",
    summary="Retry Document Processing",
    description="""
Reset a document for reprocessing.

This endpoint resets a failed or stuck document back to pending status
and triggers processing. Works for documents that are:
- Failed
- Stuck in processing state
- Pending but not progressing

Use `force=true` to reprocess an already completed document.
    """,
)
async def retry_document(
    document_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
    force: bool = Query(False, description="Force reprocessing even if completed"),
) -> dict:
    """Retry processing a document."""
    from evidence_repository.digestion.status import retry_single_document
    from evidence_repository.models.document import ProcessingStatus as DocProcessingStatus
    import httpx
    import os
    import logging

    logger = logging.getLogger(__name__)

    # Get document with versions
    result = await db.execute(
        select(Document)
        .options(selectinload(Document.versions))
        .where(Document.id == document_id)
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found",
        )

    if not document.versions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Document has no versions",
        )

    version = document.versions[0]  # Latest version

    # Check if already completed and force not set
    if version.extraction_status == ExtractionStatus.COMPLETED and not force:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Document already completed. Use force=true to reprocess.",
        )

    # Reset to pending for reprocessing
    version.extraction_status = ExtractionStatus.PENDING
    version.processing_status = DocProcessingStatus.UPLOADED
    version.extraction_error = None
    await db.commit()

    # Trigger processing via fire-and-forget HTTP call
    try:
        base_url = os.environ.get("VERCEL_URL")
        if base_url:
            base_url = f"https://{base_url}"
        else:
            base_url = f"{request.url.scheme}://{request.url.netloc}"

        api_key = request.headers.get("x-api-key", "")

        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                await client.post(
                    f"{base_url}/api/v1/worker/process-version-sync/{version.id}",
                    headers={"x-api-key": api_key},
                )
            except httpx.TimeoutException:
                pass  # Expected - we don't wait for completion
            except Exception as e:
                logger.warning(f"Fire-and-forget trigger failed: {e}")
    except Exception as e:
        logger.warning(f"Could not trigger immediate processing: {e}")

    return {
        "success": True,
        "document_id": str(document.id),
        "version_id": str(version.id),
        "filename": document.original_filename,
        "message": "Document queued for reprocessing",
    }


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Delete Document",
    description="""
Mark a document for deletion and queue the cascading delete process.

**Safe Deletion Flow:**
1. Document is marked as "marked_for_deletion"
2. Deletion tasks are created for each resource (storage, embeddings, spans, etc.)
3. Worker processes each task in dependency order
4. Only after ALL resources are deleted, the document is marked as "deleted"
5. If any task fails, document is marked as "failed" and can be retried

This prevents orphaned data from network failures or partial deletions.

**Returns:**
- `status`: "deletion_queued" or error status
- `task_count`: Number of deletion tasks created
- `document_id`: The document being deleted
    """,
)
async def delete_document(
    document_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
    storage: StorageBackend = Depends(get_storage),
    user: User = Depends(get_current_user),
) -> dict:
    """Mark a document for deletion and queue the cascading delete process."""
    import logging
    import httpx
    import os
    from evidence_repository.models.document import DeletionStatus
    from evidence_repository.digestion.deletion import create_deletion_tasks

    logger = logging.getLogger(__name__)

    result = await db.execute(
        select(Document)
        .options(selectinload(Document.versions))
        .where(Document.id == document_id)
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found",
        )

    # Check if already being deleted or deleted
    if document.deletion_status == DeletionStatus.DELETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Document has already been deleted",
        )

    if document.deletion_status in [DeletionStatus.MARKED_FOR_DELETION, DeletionStatus.DELETING_RESOURCES]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Document is already being deleted (status: {document.deletion_status.value})",
        )

    # Cancel any pending/running jobs for this document's versions
    version_ids = [str(v.id) for v in document.versions]
    canceled_jobs = 0

    try:
        from evidence_repository.models.job import Job, JobStatus

        if version_ids:
            jobs_result = await db.execute(
                select(Job).where(
                    Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.RETRYING])
                )
            )
            jobs = jobs_result.scalars().all()

            for job in jobs:
                payload_version_id = job.payload.get("version_id") if job.payload else None
                payload_document_id = job.payload.get("document_id") if job.payload else None
                if payload_version_id in version_ids or payload_document_id == str(document_id):
                    job.status = JobStatus.CANCELED
                    job.error = f"Document {document_id} was deleted"
                    canceled_jobs += 1
                    logger.info(f"Canceled job {job.id} for deleted document {document_id}")
    except Exception as e:
        logger.warning(f"Could not cancel jobs for document {document_id}: {e}")

    # Create deletion tasks for all resources
    tasks = await create_deletion_tasks(db, document, user.id)

    # Write audit log for deletion request
    try:
        await _write_audit_log(
            db=db,
            action=AuditAction.DOCUMENT_DELETE,
            entity_type="document",
            entity_id=document_id,
            actor_id=user.id,
            details={
                "filename": document.filename,
                "version_count": len(document.versions),
                "canceled_jobs": canceled_jobs,
                "deletion_tasks": len(tasks),
                "status": "deletion_queued",
            },
            request=request,
        )
    except Exception as e:
        logger.warning(f"Failed to write audit log for document {document_id} deletion: {e}")

    await db.commit()

    # Trigger deletion worker via fire-and-forget HTTP call
    try:
        base_url = os.environ.get("VERCEL_URL")
        if base_url:
            base_url = f"https://{base_url}"
        else:
            base_url = f"{request.url.scheme}://{request.url.netloc}"

        api_key = request.headers.get("x-api-key", "")

        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                await client.post(
                    f"{base_url}/api/v1/worker/process-deletion/{document_id}",
                    headers={"x-api-key": api_key},
                )
            except httpx.TimeoutException:
                pass  # Expected - we don't wait for completion
            except Exception as e:
                logger.warning(f"Fire-and-forget deletion trigger failed: {e}")
    except Exception as e:
        logger.warning(f"Could not trigger immediate deletion processing: {e}")

    return {
        "status": "deletion_queued",
        "document_id": str(document_id),
        "filename": document.original_filename,
        "task_count": len(tasks),
        "message": f"Document '{document.original_filename}' marked for deletion. {len(tasks)} tasks queued.",
    }


@router.get(
    "/{document_id}/deletion-status",
    summary="Get Deletion Status",
    description="""
Get detailed status of a document's deletion process.

Returns:
- Current deletion status
- Task summary (total, completed, pending, failed)
- Individual task details with status, error messages, retry counts
    """,
)
async def get_deletion_status(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> dict:
    """Get detailed deletion status for a document."""
    from evidence_repository.digestion.deletion import get_deletion_status as _get_deletion_status

    result = await _get_deletion_status(db, document_id)

    if "error" in result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=result["error"],
        )

    return result


@router.post(
    "/{document_id}/retry-deletion",
    summary="Retry Failed Deletion",
    description="""
Retry deletion for a document with failed tasks.

This will:
1. Reset all failed deletion tasks to pending
2. Re-trigger the deletion worker
3. Continue processing from where it failed

Only works for documents in "failed" or "marked" status.
    """,
)
async def retry_document_deletion(
    document_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
    storage: StorageBackend = Depends(get_storage),
    user: User = Depends(get_current_user),
) -> dict:
    """Retry deletion for a document with failed tasks."""
    import logging
    import httpx
    import os
    from evidence_repository.digestion.deletion import retry_failed_deletion

    logger = logging.getLogger(__name__)

    result = await retry_failed_deletion(db, document_id, storage)

    if "error" in result:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["error"],
        )

    return result


@router.get(
    "/{document_id}/quality",
    response_model=QualityAnalysisResponse,
    summary="Analyze Document Quality",
    description="""
Analyze the quality of extracted facts for a document.

Detects:
- **Metric Conflicts**: Same metric with overlapping time period but different values
- **Claim Conflicts**: Same boolean claim (e.g., has_soc2) with contradicting values
- **Open Questions**: Missing units, currency, periods, or stale financial data (>12 months old)

Returns a summary with counts and detailed lists of each issue.
    """,
)
async def analyze_document_quality(
    document_id: uuid.UUID,
    version_id: uuid.UUID | None = Query(
        default=None, description="Specific version to analyze (defaults to latest)"
    ),
    profile_id: uuid.UUID | None = Query(
        default=None, description="Filter by extraction profile"
    ),
    level_id: uuid.UUID | None = Query(
        default=None, description="Filter by extraction level"
    ),
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> QualityAnalysisResponse:
    """Analyze quality of extracted facts for a document.

    Detects conflicts between metrics and claims, and identifies
    open questions about missing or stale data.
    """
    # Check document exists
    result = await db.execute(
        select(Document).where(Document.id == document_id, Document.deleted_at.is_(None))
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found",
        )

    # Run quality analysis
    service = QualityAnalysisService(db=db)
    analysis_result = await service.analyze_document(
        document_id=document_id,
        version_id=version_id,
        profile_id=profile_id,
        level_id=level_id,
    )

    return QualityAnalysisResponse.from_analysis_result(analysis_result)


# =============================================================================
# Presigned Upload Endpoints (for large files - bypasses Vercel 4.5MB limit)
# =============================================================================


@router.post(
    "/presigned-upload",
    response_model=PresignedUploadResponse,
    summary="Get Presigned Upload URL",
    description="""
Get a presigned URL for direct upload to storage (Cloudflare R2).

This bypasses the Vercel serverless 4.5MB payload limit, allowing uploads
of any size directly to cloud storage.

**Flow:**
1. Call this endpoint with file metadata
2. Upload the file directly to the returned `upload_url` using PUT
3. Call `/documents/confirm-upload` to complete the process
    """,
)
async def get_presigned_upload_url(
    request: Request,
    body: PresignedUploadRequest,
    db: AsyncSession = Depends(get_db_session),
    storage: StorageBackend = Depends(get_storage),
    user: User = Depends(get_current_user),
) -> PresignedUploadResponse:
    """Generate a presigned URL for direct upload to storage."""
    from pathlib import Path
    from evidence_repository.storage.s3 import S3Storage

    settings = get_settings()

    # Validate storage backend supports presigned URLs
    if not isinstance(storage, S3Storage):
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Presigned uploads require S3-compatible storage (set STORAGE_BACKEND=s3)",
        )

    # Validate file extension
    extension = Path(body.filename).suffix.lower()
    if extension not in settings.supported_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: {extension}. Supported: {settings.supported_extensions}",
        )

    # Validate file size
    max_size = settings.max_file_size_mb * 1024 * 1024
    if body.file_size > max_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large ({body.file_size} bytes). Maximum: {max_size} bytes",
        )

    # Validate profile_code
    valid_profiles = {"general", "vc", "pharma", "insurance"}
    if body.profile_code not in valid_profiles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid profile_code: {body.profile_code}. Valid options: {', '.join(sorted(valid_profiles))}",
        )

    # Create document and version records (pending upload)
    import hashlib
    document_id = uuid.uuid4()
    version_id = uuid.uuid4()

    # Generate unique filename
    safe_filename = f"{document_id}{extension}"

    # Create document record
    document = Document(
        id=document_id,
        filename=safe_filename,
        original_filename=body.filename,
        content_type=body.content_type,
        profile_code=body.profile_code,
        metadata_={"uploaded_by": user.id, "pending_upload": True},
    )
    db.add(document)

    # Generate storage path (format: documents/{doc_id}/v{version}/filename)
    path_key = storage.generate_path_key(
        document_id=str(document_id),
        version_number=1,  # First version
        filename=body.filename,
    )

    # Create version record (pending upload)
    version = DocumentVersion(
        id=version_id,
        document_id=document_id,
        version_number=1,
        file_size=body.file_size,
        file_hash="pending",  # Will be updated after upload
        storage_path=path_key,
        upload_status=UploadStatus.PENDING,
        extraction_status=ExtractionStatus.PENDING,
        processing_status=ProcessingStatus.PENDING,
        metadata_={"pending_upload": True},
    )
    db.add(version)

    # Write audit log
    await _write_audit_log(
        db=db,
        action=AuditAction.DOCUMENT_UPLOAD,
        entity_type="document",
        entity_id=document_id,
        actor_id=user.id,
        details={
            "filename": body.filename,
            "content_type": body.content_type,
            "file_size": body.file_size,
            "presigned": True,
            "status": "pending_upload",
        },
        request=request,
    )

    await db.commit()

    # Generate presigned URL
    presigned = await storage.generate_presigned_upload_url(
        path_key=path_key,
        content_type=body.content_type,
        ttl_seconds=3600,  # 1 hour
    )

    return PresignedUploadResponse(
        upload_url=presigned["upload_url"],
        document_id=document_id,
        version_id=version_id,
        key=presigned["key"],
        content_type=body.content_type,
        expires_in=presigned["expires_in"],
        message=f"Upload '{body.filename}' to the presigned URL using PUT, then call /documents/confirm-upload",
    )


@router.post(
    "/confirm-upload",
    response_model=ConfirmUploadResponse,
    summary="Confirm Presigned Upload",
    description="""
Confirm that a presigned upload completed successfully.

Call this after uploading the file to the presigned URL.
This will verify the file exists and queue it for processing.
    """,
)
async def confirm_presigned_upload(
    request: Request,
    body: ConfirmUploadRequest,
    db: AsyncSession = Depends(get_db_session),
    storage: StorageBackend = Depends(get_storage),
    user: User = Depends(get_current_user),
) -> ConfirmUploadResponse:
    """Confirm a presigned upload and queue for processing."""
    # Get the document and version
    result = await db.execute(
        select(Document)
        .options(selectinload(Document.versions))
        .where(Document.id == body.document_id)
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {body.document_id} not found",
        )

    # Find the version
    version = next((v for v in document.versions if v.id == body.version_id), None)
    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Version {body.version_id} not found",
        )

    # Verify file exists in storage
    file_uri = f"s3://{storage.bucket_name}/{version.storage_path}"
    if not await storage.exists(file_uri):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File not found in storage. Please upload to the presigned URL first.",
        )

    # Get file metadata from storage
    try:
        metadata = await storage.get_metadata(file_uri)
        version.file_size = metadata.size
        version.file_hash = metadata.etag
    except Exception:
        # Continue without metadata update
        pass

    # Mark as no longer pending and update upload/processing status
    document.metadata_["pending_upload"] = False
    version.metadata_["pending_upload"] = False
    version.upload_status = UploadStatus.UPLOADED
    version.processing_status = ProcessingStatus.UPLOADED

    # Write audit log
    await _write_audit_log(
        db=db,
        action=AuditAction.DOCUMENT_UPLOAD,
        entity_type="document",
        entity_id=document.id,
        actor_id=user.id,
        details={
            "filename": document.original_filename,
            "version_id": str(version.id),
            "presigned": True,
            "status": "confirmed",
        },
        request=request,
    )

    await db.commit()

    # Mark version as pending for processing
    version.extraction_status = ExtractionStatus.PENDING
    await db.commit()

    # Trigger processing via fire-and-forget HTTP call to worker endpoint
    # This works on serverless (Vercel) where BackgroundTasks don't complete
    import os
    import httpx
    import logging

    logger = logging.getLogger(__name__)

    # Try to trigger processing immediately (fire-and-forget)
    # If this fails, the cron job will pick it up later
    try:
        # Get the base URL from environment or request
        base_url = os.environ.get("VERCEL_URL")
        if base_url:
            base_url = f"https://{base_url}"
        else:
            # For local development, use request host
            base_url = f"{request.url.scheme}://{request.url.netloc}"

        api_key = request.headers.get("x-api-key", "")

        # Fire-and-forget call to process this version
        # We don't await the full response - just fire the request
        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                await client.post(
                    f"{base_url}/api/v1/worker/process-version-sync/{version.id}",
                    headers={"x-api-key": api_key},
                )
            except httpx.TimeoutException:
                # Expected - we don't wait for completion
                pass
            except Exception as e:
                logger.warning(f"Fire-and-forget trigger failed: {e}")
    except Exception as e:
        logger.warning(f"Could not trigger immediate processing: {e}")
        # Processing will be picked up by cron job

    return ConfirmUploadResponse(
        document_id=document.id,
        version_id=version.id,
        job_id=None,  # No longer using job queue for immediate processing
        message=f"Upload confirmed. Document '{document.original_filename}' queued for processing.",
    )


@router.get(
    "/{document_id}/stats",
    summary="Get Document Statistics",
    description="""
Get statistics about a document's processing including:
- Number of spans (text chunks) created
- Number of embeddings generated
- Embedding dimensions and configuration
- Extracted metadata
    """,
)
async def get_document_stats(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> dict:
    """Get document processing statistics."""
    from sqlalchemy import func
    from evidence_repository.models.evidence import Span
    from evidence_repository.models.embedding import EmbeddingChunk

    # Get document with latest version
    result = await db.execute(
        select(Document)
        .options(selectinload(Document.versions))
        .where(Document.id == document_id, Document.deleted_at.is_(None))
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found",
        )

    # Get latest version
    version = document.versions[0] if document.versions else None
    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} has no versions",
        )

    # Count spans for this version
    spans_result = await db.execute(
        select(func.count(Span.id)).where(Span.document_version_id == version.id)
    )
    spans_count = spans_result.scalar() or 0

    # Count embeddings for this version
    embeddings_result = await db.execute(
        select(func.count(EmbeddingChunk.id)).where(EmbeddingChunk.document_version_id == version.id)
    )
    embeddings_count = embeddings_result.scalar() or 0

    # Get span types breakdown
    span_types_result = await db.execute(
        select(Span.span_type, func.count(Span.id))
        .where(Span.document_version_id == version.id)
        .group_by(Span.span_type)
    )
    span_types = {str(row[0].value): row[1] for row in span_types_result.fetchall()}

    # Get embedding model info from settings
    settings = get_settings()

    return {
        "document_id": str(document.id),
        "version_id": str(version.id),
        "filename": document.original_filename,
        "extraction_status": version.extraction_status.value if version.extraction_status else None,
        "extracted_at": version.extracted_at.isoformat() if version.extracted_at else None,
        "text_length": len(version.extracted_text or ""),
        "page_count": version.page_count,
        "spans": {
            "total": spans_count,
            "by_type": span_types,
        },
        "embeddings": {
            "total": embeddings_count,
            "model": settings.openai_embedding_model,
            "dimensions": 1536,  # text-embedding-3-small default
            "chunk_size": 512,
            "chunk_overlap": 50,
        },
        "metadata": document.metadata_ or {},
        "version_metadata": version.metadata_ or {},
    }


@router.get(
    "/{document_id}/spans",
    summary="List Document Spans",
    description="List all spans (text chunks) extracted from a document.",
)
async def list_document_spans(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict:
    """List spans for a document."""
    from evidence_repository.models.evidence import Span

    # Get document with latest version
    result = await db.execute(
        select(Document)
        .options(selectinload(Document.versions))
        .where(Document.id == document_id, Document.deleted_at.is_(None))
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found",
        )

    version = document.versions[0] if document.versions else None
    if not version:
        return {"items": [], "total": 0}

    # Get spans
    spans_result = await db.execute(
        select(Span)
        .where(Span.document_version_id == version.id)
        .order_by(Span.created_at)
        .offset(offset)
        .limit(limit)
    )
    spans = spans_result.scalars().all()

    # Get total count
    from sqlalchemy import func
    count_result = await db.execute(
        select(func.count(Span.id)).where(Span.document_version_id == version.id)
    )
    total = count_result.scalar() or 0

    return {
        "items": [
            {
                "id": str(span.id),
                "span_type": span.span_type.value,
                "text_content": span.text_content[:500] + "..." if len(span.text_content) > 500 else span.text_content,
                "text_length": len(span.text_content),
                "start_locator": span.start_locator,
                "end_locator": span.end_locator,
                "metadata": span.metadata_,
                "created_at": span.created_at.isoformat() if span.created_at else None,
            }
            for span in spans
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get(
    "/{document_id}/embeddings",
    summary="List Document Embeddings",
    description="List all embedding chunks generated for a document.",
)
async def list_document_embeddings(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict:
    """List embedding chunks for a document."""
    from evidence_repository.models.embedding import EmbeddingChunk

    # Get document with latest version
    result = await db.execute(
        select(Document)
        .options(selectinload(Document.versions))
        .where(Document.id == document_id, Document.deleted_at.is_(None))
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found",
        )

    version = document.versions[0] if document.versions else None
    if not version:
        return {"items": [], "total": 0}

    # Get embedding chunks (without the actual vector for efficiency)
    embeddings_result = await db.execute(
        select(EmbeddingChunk)
        .where(EmbeddingChunk.document_version_id == version.id)
        .order_by(EmbeddingChunk.chunk_index)
        .offset(offset)
        .limit(limit)
    )
    embeddings = embeddings_result.scalars().all()

    # Get total count
    from sqlalchemy import func
    count_result = await db.execute(
        select(func.count(EmbeddingChunk.id)).where(
            EmbeddingChunk.document_version_id == version.id
        )
    )
    total = count_result.scalar() or 0

    # Get embedding model info from settings
    settings = get_settings()

    return {
        "items": [
            {
                "id": str(emb.id),
                "chunk_index": emb.chunk_index,
                "text": emb.text[:500] + "..." if len(emb.text) > 500 else emb.text,
                "text_length": len(emb.text),
                "char_start": emb.char_start,
                "char_end": emb.char_end,
                "metadata": emb.metadata_,
                "created_at": emb.created_at.isoformat() if emb.created_at else None,
            }
            for emb in embeddings
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
        "model": settings.openai_embedding_model,
        "dimensions": 1536,
    }
