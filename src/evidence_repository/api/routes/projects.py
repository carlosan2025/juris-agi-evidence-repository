"""Project management endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from evidence_repository.api.dependencies import User, get_current_user
from evidence_repository.db.session import get_db_session
from evidence_repository.models.document import Document
from evidence_repository.models.project import Project, ProjectDocument
from evidence_repository.schemas.common import PaginatedResponse
from evidence_repository.schemas.project import (
    AttachDocumentRequest,
    ProjectCreate,
    ProjectDocumentResponse,
    ProjectResponse,
    ProjectUpdate,
)

router = APIRouter()


@router.post(
    "",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Project",
    description="Create a new project (evaluation context).",
)
async def create_project(
    project_in: ProjectCreate,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> ProjectResponse:
    """Create a new project."""
    project = Project(
        name=project_in.name,
        description=project_in.description,
        case_ref=project_in.case_ref,
        metadata_=project_in.metadata,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)

    return ProjectResponse(
        **project.__dict__,
        document_count=0,
        claim_count=0,
        metric_count=0,
    )


@router.get(
    "",
    response_model=PaginatedResponse[ProjectResponse],
    summary="List Projects",
    description="List all projects with pagination.",
)
async def list_projects(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    include_deleted: bool = Query(default=False),
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> PaginatedResponse[ProjectResponse]:
    """List projects with pagination."""
    query = select(Project).options(
        selectinload(Project.project_documents),
        selectinload(Project.claims),
        selectinload(Project.metrics),
    )

    if not include_deleted:
        query = query.where(Project.deleted_at.is_(None))

    # Count total
    count_query = select(func.count()).select_from(Project)
    if not include_deleted:
        count_query = count_query.where(Project.deleted_at.is_(None))
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Paginate
    query = query.order_by(Project.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    projects = result.scalars().all()

    items = []
    for p in projects:
        items.append(
            ProjectResponse(
                id=p.id,
                name=p.name,
                description=p.description,
                case_ref=p.case_ref,
                created_at=p.created_at,
                updated_at=p.updated_at,
                deleted_at=p.deleted_at,
                metadata_=p.metadata_,
                document_count=len(p.project_documents),
                claim_count=len(p.claims),
                metric_count=len(p.metrics),
            )
        )

    return PaginatedResponse.create(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
    summary="Get Project",
    description="Get project details by ID.",
)
async def get_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> ProjectResponse:
    """Get a project by ID."""
    result = await db.execute(
        select(Project)
        .options(
            selectinload(Project.project_documents),
            selectinload(Project.claims),
            selectinload(Project.metrics),
        )
        .where(Project.id == project_id)
    )
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )

    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        case_ref=project.case_ref,
        created_at=project.created_at,
        updated_at=project.updated_at,
        deleted_at=project.deleted_at,
        metadata_=project.metadata_,
        document_count=len(project.project_documents),
        claim_count=len(project.claims),
        metric_count=len(project.metrics),
    )


@router.patch(
    "/{project_id}",
    response_model=ProjectResponse,
    summary="Update Project",
    description="Update project details.",
)
async def update_project(
    project_id: uuid.UUID,
    project_in: ProjectUpdate,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> ProjectResponse:
    """Update a project."""
    result = await db.execute(
        select(Project)
        .options(
            selectinload(Project.project_documents),
            selectinload(Project.claims),
            selectinload(Project.metrics),
        )
        .where(Project.id == project_id)
    )
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )

    # Update fields
    if project_in.name is not None:
        project.name = project_in.name
    if project_in.description is not None:
        project.description = project_in.description
    if project_in.case_ref is not None:
        project.case_ref = project_in.case_ref
    if project_in.metadata is not None:
        project.metadata_ = project_in.metadata

    await db.commit()
    await db.refresh(project)

    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        case_ref=project.case_ref,
        created_at=project.created_at,
        updated_at=project.updated_at,
        deleted_at=project.deleted_at,
        metadata_=project.metadata_,
        document_count=len(project.project_documents),
        claim_count=len(project.claims),
        metric_count=len(project.metrics),
    )


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Project",
    description="Soft delete a project.",
)
async def delete_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> None:
    """Soft delete a project."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )

    from datetime import datetime

    project.deleted_at = datetime.utcnow()
    await db.commit()


# =============================================================================
# Project Document Attachment
# =============================================================================


@router.post(
    "/{project_id}/documents",
    response_model=ProjectDocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Attach Document",
    description="Attach a document to a project.",
)
async def attach_document(
    project_id: uuid.UUID,
    request: AttachDocumentRequest,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> ProjectDocumentResponse:
    """Attach a document to a project."""
    # Verify project exists
    project_result = await db.execute(select(Project).where(Project.id == project_id))
    project = project_result.scalar_one_or_none()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )

    # Verify document exists
    doc_result = await db.execute(
        select(Document)
        .options(selectinload(Document.versions))
        .where(Document.id == request.document_id)
    )
    document = doc_result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {request.document_id} not found",
        )

    # Check if already attached
    existing = await db.execute(
        select(ProjectDocument).where(
            ProjectDocument.project_id == project_id,
            ProjectDocument.document_id == request.document_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document already attached to this project",
        )

    # Create attachment
    project_document = ProjectDocument(
        project_id=project_id,
        document_id=request.document_id,
        pinned_version_id=request.pinned_version_id,
        attached_by=user.id,
        notes=request.notes,
    )
    db.add(project_document)
    await db.commit()
    await db.refresh(project_document)

    return ProjectDocumentResponse.model_validate(project_document)


@router.get(
    "/{project_id}/documents",
    response_model=list[ProjectDocumentResponse],
    summary="List Project Documents",
    description="List all documents attached to a project.",
)
async def list_project_documents(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> list[ProjectDocumentResponse]:
    """List documents attached to a project."""
    result = await db.execute(
        select(ProjectDocument)
        .options(
            selectinload(ProjectDocument.document).selectinload(Document.versions),
            selectinload(ProjectDocument.pinned_version),
        )
        .where(ProjectDocument.project_id == project_id)
        .order_by(ProjectDocument.attached_at.desc())
    )
    project_documents = result.scalars().all()

    return [ProjectDocumentResponse.model_validate(pd) for pd in project_documents]


@router.delete(
    "/{project_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Detach Document",
    description="Detach a document from a project.",
)
async def detach_document(
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> None:
    """Detach a document from a project."""
    result = await db.execute(
        select(ProjectDocument).where(
            ProjectDocument.project_id == project_id,
            ProjectDocument.document_id == document_id,
        )
    )
    project_document = result.scalar_one_or_none()

    if not project_document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not attached to this project",
        )

    await db.delete(project_document)
    await db.commit()
