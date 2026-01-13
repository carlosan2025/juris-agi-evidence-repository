"""Bulk ingestion endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from evidence_repository.api.dependencies import User, get_current_user, get_storage
from evidence_repository.config import get_settings
from evidence_repository.db.session import get_db_session
from evidence_repository.models.audit import AuditAction, AuditLog
from evidence_repository.models.ingestion import IngestionBatchStatus, IngestionSource
from evidence_repository.schemas.ingestion import (
    FolderIngestionRequest,
    FolderIngestionResponse,
    IngestionBatchListResponse,
    IngestionBatchResponse,
    IngestionItemResponse,
    URLIngestionRequest,
    URLIngestionResponse,
)
from evidence_repository.services.bulk_ingestion_service import BulkIngestionService
from evidence_repository.storage.base import StorageBackend
from evidence_repository.utils.security import SSRFProtectionError, validate_url_for_ssrf

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
    "/folder",
    response_model=FolderIngestionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Bulk Ingest from Folder",
    description="""
Scan a local folder and ingest all supported files.

For each file matching the allowed types:
- Creates a document and version record
- Optionally attaches to the specified project
- Enqueues a processing job if auto_process is enabled

Use GET /ingest/batches/{batch_id} to track progress.
    """,
)
async def ingest_folder(
    request_obj: Request,
    request: FolderIngestionRequest,
    db: AsyncSession = Depends(get_db_session),
    storage: StorageBackend = Depends(get_storage),
    user: User = Depends(get_current_user),
) -> FolderIngestionResponse:
    """Initiate folder ingestion."""
    settings = get_settings()

    # Validate folder exists
    from pathlib import Path
    folder = Path(request.path)
    if not folder.exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Folder not found: {request.path}",
        )
    if not folder.is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Not a directory: {request.path}",
        )

    # Create service
    service = BulkIngestionService(storage=storage, db=db)

    # Scan folder for files
    try:
        files = await service.scan_folder(
            folder_path=request.path,
            recursive=request.recursive,
            allowed_types=request.allowed_types,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No supported files found in folder. Allowed types: {request.allowed_types}",
        )

    # Create batch and enqueue job
    try:
        batch, job_id = await service.create_folder_batch(
            folder_path=request.path,
            files=files,
            project_id=request.project_id,
            auto_process=request.auto_process,
            user_id=user.id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    # Write audit log
    await _write_audit_log(
        db=db,
        action=AuditAction.DOCUMENT_UPLOAD,
        entity_type="ingestion_batch",
        entity_id=batch.id,
        actor_id=user.id,
        details={
            "source_type": "folder",
            "folder_path": request.path,
            "total_files": len(files),
            "project_id": str(request.project_id) if request.project_id else None,
            "auto_process": request.auto_process,
        },
        request=request_obj,
    )

    await db.commit()

    return FolderIngestionResponse(
        batch_id=batch.id,
        job_id=job_id,
        total_files=len(files),
        message=f"Found {len(files)} files. Ingestion job queued.",
    )


@router.post(
    "/url",
    response_model=URLIngestionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest from URL",
    description="""
Download and ingest a file from a URL.

Security:
- Private/internal IPs are blocked (SSRF protection)
- Only http and https schemes are allowed
- Max file size is enforced during download

Use GET /ingest/batches/{batch_id} to track progress.
    """,
)
async def ingest_url(
    request_obj: Request,
    request: URLIngestionRequest,
    db: AsyncSession = Depends(get_db_session),
    storage: StorageBackend = Depends(get_storage),
    user: User = Depends(get_current_user),
) -> URLIngestionResponse:
    """Initiate URL ingestion."""
    # Validate URL for SSRF
    try:
        validate_url_for_ssrf(request.url)
    except SSRFProtectionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"URL validation failed: {e}",
        )

    # Create service
    service = BulkIngestionService(storage=storage, db=db)

    # Create batch and enqueue job
    try:
        batch, item, job_id = await service.create_url_batch(
            url=request.url,
            filename=request.filename,
            project_id=request.project_id,
            auto_process=request.auto_process,
            user_id=user.id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    # Write audit log
    await _write_audit_log(
        db=db,
        action=AuditAction.DOCUMENT_UPLOAD,
        entity_type="ingestion_batch",
        entity_id=batch.id,
        actor_id=user.id,
        details={
            "source_type": "url",
            "url": request.url,
            "project_id": str(request.project_id) if request.project_id else None,
            "auto_process": request.auto_process,
        },
        request=request_obj,
    )

    await db.commit()

    return URLIngestionResponse(
        batch_id=batch.id,
        item_id=item.id,
        job_id=job_id,
        message=f"URL ingestion job queued: {request.url}",
    )


# =============================================================================
# Batch Management Endpoints
# =============================================================================


@router.get(
    "/batches",
    response_model=IngestionBatchListResponse,
    summary="List Ingestion Batches",
    description="List all ingestion batches with optional filtering.",
)
async def list_batches(
    status_filter: str | None = Query(None, alias="status", description="Filter by status"),
    source_type: str | None = Query(None, description="Filter by source type"),
    limit: int = Query(default=50, ge=1, le=200, description="Maximum batches to return"),
    offset: int = Query(default=0, ge=0, description="Offset for pagination"),
    db: AsyncSession = Depends(get_db_session),
    storage: StorageBackend = Depends(get_storage),
    user: User = Depends(get_current_user),
) -> IngestionBatchListResponse:
    """List ingestion batches."""
    service = BulkIngestionService(storage=storage, db=db)

    # Parse status filter
    batch_status = None
    if status_filter:
        try:
            batch_status = IngestionBatchStatus(status_filter)
        except ValueError:
            valid_statuses = [s.value for s in IngestionBatchStatus]
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {status_filter}. Valid values: {valid_statuses}",
            )

    # Parse source type filter
    source = None
    if source_type:
        try:
            source = IngestionSource(source_type)
        except ValueError:
            valid_sources = [s.value for s in IngestionSource]
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid source type: {source_type}. Valid values: {valid_sources}",
            )

    batches = await service.list_batches(
        status=batch_status,
        source_type=source,
        limit=limit,
        offset=offset,
    )

    batch_responses = [
        IngestionBatchResponse(
            id=b.id,
            name=b.name,
            source_type=b.source_type.value,
            source_path=b.source_path,
            status=b.status.value,
            total_items=b.total_items,
            processed_items=b.processed_items,
            successful_items=b.successful_items,
            failed_items=b.failed_items,
            skipped_items=b.skipped_items,
            progress_percent=b.progress_percent,
            job_id=str(b.job_id) if b.job_id else None,
            created_at=b.created_at,
            started_at=b.started_at,
            completed_at=b.completed_at,
            metadata=b.metadata_,
        )
        for b in batches
    ]

    return IngestionBatchListResponse(
        batches=batch_responses,
        total=len(batch_responses),
    )


@router.get(
    "/batches/{batch_id}",
    response_model=IngestionBatchResponse,
    summary="Get Ingestion Batch",
    description="Get details of an ingestion batch including all items.",
)
async def get_batch(
    batch_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    storage: StorageBackend = Depends(get_storage),
    user: User = Depends(get_current_user),
) -> IngestionBatchResponse:
    """Get a specific ingestion batch."""
    service = BulkIngestionService(storage=storage, db=db)

    batch = await service.get_batch(batch_id)
    if not batch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Batch {batch_id} not found",
        )

    return IngestionBatchResponse(
        id=batch.id,
        name=batch.name,
        source_type=batch.source_type.value,
        source_path=batch.source_path,
        status=batch.status.value,
        total_items=batch.total_items,
        processed_items=batch.processed_items,
        successful_items=batch.successful_items,
        failed_items=batch.failed_items,
        skipped_items=batch.skipped_items,
        progress_percent=batch.progress_percent,
        job_id=str(batch.job_id) if batch.job_id else None,
        created_at=batch.created_at,
        started_at=batch.started_at,
        completed_at=batch.completed_at,
        metadata=batch.metadata_,
    )


@router.get(
    "/batches/{batch_id}/items",
    response_model=list[IngestionItemResponse],
    summary="Get Batch Items",
    description="Get all items in an ingestion batch.",
)
async def get_batch_items(
    batch_id: uuid.UUID,
    status_filter: str | None = Query(None, alias="status", description="Filter by status"),
    db: AsyncSession = Depends(get_db_session),
    storage: StorageBackend = Depends(get_storage),
    user: User = Depends(get_current_user),
) -> list[IngestionItemResponse]:
    """Get items in a batch."""
    service = BulkIngestionService(storage=storage, db=db)

    batch = await service.get_batch(batch_id)
    if not batch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Batch {batch_id} not found",
        )

    items = batch.items

    # Filter by status if provided
    if status_filter:
        from evidence_repository.models.ingestion import IngestionItemStatus
        try:
            item_status = IngestionItemStatus(status_filter)
            items = [i for i in items if i.status == item_status]
        except ValueError:
            valid_statuses = [s.value for s in IngestionItemStatus]
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {status_filter}. Valid values: {valid_statuses}",
            )

    return [
        IngestionItemResponse(
            id=item.id,
            source_path=item.source_path,
            source_filename=item.source_filename,
            status=item.status.value,
            document_id=item.document_id,
            version_id=item.document_version_id,
            error_message=item.error_message,
            content_type=item.content_type,
            created_at=item.created_at,
        )
        for item in items
    ]
