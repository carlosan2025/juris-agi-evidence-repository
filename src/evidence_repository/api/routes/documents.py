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
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> PaginatedResponse[DocumentResponse]:
    """List documents with pagination."""
    # Build query
    query = select(Document).options(selectinload(Document.versions))

    if not include_deleted:
        query = query.where(Document.deleted_at.is_(None))

    # Count total
    count_query = select(func.count()).select_from(Document)
    if not include_deleted:
        count_query = count_query.where(Document.deleted_at.is_(None))
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


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Document",
    description="Permanently delete a document, cancel pending jobs, and remove files from storage.",
)
async def delete_document(
    document_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
    storage: StorageBackend = Depends(get_storage),
    user: User = Depends(get_current_user),
) -> None:
    """Permanently delete a document, cancel any pending jobs, and remove files from storage."""
    import logging
    from evidence_repository.models.job import Job, JobStatus

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

    # Get version IDs for this document
    version_ids = [str(v.id) for v in document.versions]
    canceled_jobs = 0

    # Cancel any pending/running jobs for this document's versions
    if version_ids:
        # Find jobs that reference these versions in their payload
        jobs_result = await db.execute(
            select(Job).where(
                Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.RETRYING])
            )
        )
        jobs = jobs_result.scalars().all()

        for job in jobs:
            # Check if job payload contains any of our version IDs
            payload_version_id = job.payload.get("version_id")
            payload_document_id = job.payload.get("document_id")
            if payload_version_id in version_ids or payload_document_id == str(document_id):
                job.status = JobStatus.CANCELED
                job.error = f"Document {document_id} was deleted"
                canceled_jobs += 1
                logging.info(f"Canceled job {job.id} for deleted document {document_id}")

    # Delete files from storage for each version
    for version in document.versions:
        try:
            # Convert storage path key to full URI using storage backend's method
            file_uri = storage._key_to_uri(version.storage_path)
            await storage.delete(file_uri)
        except Exception as e:
            # Log but continue - file might already be deleted or upload never completed
            logging.warning(f"Failed to delete file {version.storage_path}: {e}")

    # Write audit log for deletion
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
        },
        request=request,
    )

    # Hard delete from database (cascades to versions, spans, etc.)
    await db.delete(document)
    await db.commit()


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

    # Generate storage path
    path_key = storage.generate_path_key(
        document_id=str(document_id),
        version_id=str(version_id),
        extension=extension,
    )

    # Create version record (pending upload)
    version = DocumentVersion(
        id=version_id,
        document_id=document_id,
        version_number=1,
        file_size=body.file_size,
        file_hash="pending",  # Will be updated after upload
        storage_path=path_key,
        upload_status=UploadStatus.PENDING,  # Awaiting presigned upload
        processing_status=ProcessingStatus.PENDING,  # Full pipeline pending
        extraction_status=ExtractionStatus.PENDING,
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

    # Enqueue processing job
    job_queue = get_job_queue()
    job_id = job_queue.enqueue(
        job_type=JobType.PROCESS_DOCUMENT_VERSION,
        payload={
            "version_id": str(version.id),
            "profile_code": document.profile_code,
            "extraction_level": 2,
        },
        priority=0,
    )

    return ConfirmUploadResponse(
        document_id=document.id,
        version_id=version.id,
        job_id=job_id,
        message=f"Upload confirmed. Document '{document.original_filename}' queued for processing.",
    )
