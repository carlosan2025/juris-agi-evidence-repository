"""Document management endpoints."""

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
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
from evidence_repository.models.document import Document, DocumentVersion, ExtractionStatus
from evidence_repository.models.job import JobType
from evidence_repository.queue.job_queue import get_job_queue
from evidence_repository.schemas.common import PaginatedResponse
from evidence_repository.schemas.document import (
    DocumentResponse,
    DocumentUploadResponse,
    DocumentVersionResponse,
    ExtractionTriggerResponse,
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

    # Store file and create document/version records
    ingestion = IngestionService(storage=storage, db=db)
    document, version = await ingestion.ingest_document(
        filename=file.filename,
        content_type=file.content_type or "application/octet-stream",
        data=content,
        metadata={"uploaded_by": user.id},
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

    # Enqueue processing job
    job_queue = get_job_queue()
    job_id = job_queue.enqueue(
        job_type=JobType.DOCUMENT_PROCESS_FULL,
        payload={
            "document_id": str(document.id),
            "version_id": str(version.id),
            "user_id": user.id,
        },
        priority=0,
    )

    return DocumentUploadResponse(
        document_id=document.id,
        version_id=version.id,
        job_id=job_id,
        message=f"Document '{file.filename}' stored and queued for processing",
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

    # Enqueue processing job
    job_queue = get_job_queue()
    job_id = job_queue.enqueue(
        job_type=JobType.DOCUMENT_PROCESS_FULL,
        payload={
            "document_id": str(document.id),
            "version_id": str(version.id),
            "user_id": user.id,
        },
        priority=0,
    )

    return VersionUploadResponse(
        document_id=document.id,
        version_id=version.id,
        version_number=version.version_number,
        job_id=job_id,
        message=f"Version {version.version_number} stored and queued for processing",
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
    description="Soft delete a document.",
)
async def delete_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    storage: StorageBackend = Depends(get_storage),
    user: User = Depends(get_current_user),
) -> None:
    """Soft delete a document."""
    result = await db.execute(select(Document).where(Document.id == document_id))
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found",
        )

    ingestion = IngestionService(storage=storage, db=db)
    await ingestion.soft_delete_document(document)
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
