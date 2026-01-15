"""Folder management endpoints."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from evidence_repository.api.dependencies import User, get_current_user
from evidence_repository.db.session import get_db_session
from evidence_repository.models.folder import Folder
from evidence_repository.models.project import Project, ProjectDocument
from evidence_repository.schemas.folder import (
    BulkMoveDocumentsRequest,
    FolderCreate,
    FolderResponse,
    FolderTreeNode,
    FolderTreeResponse,
    FolderUpdate,
    MoveDocumentRequest,
    MoveFolderRequest,
)

router = APIRouter()


# =============================================================================
# Helper Functions
# =============================================================================


async def _get_project_or_404(db: AsyncSession, project_id: uuid.UUID) -> Project:
    """Get project or raise 404."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )
    return project


async def _get_folder_or_404(db: AsyncSession, folder_id: uuid.UUID) -> Folder:
    """Get folder or raise 404."""
    result = await db.execute(
        select(Folder).where(
            Folder.id == folder_id,
            Folder.deleted_at.is_(None),
        )
    )
    folder = result.scalar_one_or_none()
    if not folder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Folder {folder_id} not found",
        )
    return folder


async def _build_folder_response(db: AsyncSession, folder: Folder) -> FolderResponse:
    """Build folder response with counts."""
    doc_count = (
        await db.scalar(
            select(func.count()).where(ProjectDocument.folder_id == folder.id)
        )
        or 0
    )
    subfolder_count = (
        await db.scalar(
            select(func.count()).where(
                Folder.parent_folder_id == folder.id,
                Folder.deleted_at.is_(None),
            )
        )
        or 0
    )

    return FolderResponse(
        id=folder.id,
        name=folder.name,
        description=folder.description,
        project_id=folder.project_id,
        parent_folder_id=folder.parent_folder_id,
        display_order=folder.display_order,
        color=folder.color,
        icon=folder.icon,
        created_at=folder.created_at,
        updated_at=folder.updated_at,
        deleted_at=folder.deleted_at,
        metadata_=folder.metadata_,
        document_count=doc_count,
        subfolder_count=subfolder_count,
    )


# =============================================================================
# Folder CRUD Operations
# =============================================================================


@router.post(
    "/{project_id}/folders",
    response_model=FolderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Folder",
    description="Create a new folder in a project.",
)
async def create_folder(
    project_id: uuid.UUID,
    folder_in: FolderCreate,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> FolderResponse:
    """Create a new folder."""
    # Verify project exists
    await _get_project_or_404(db, project_id)

    # If parent_folder_id specified, verify it exists and belongs to same project
    if folder_in.parent_folder_id:
        parent = await _get_folder_or_404(db, folder_in.parent_folder_id)
        if parent.project_id != project_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Parent folder must belong to the same project",
            )

    # Check for duplicate name in same parent
    existing = await db.execute(
        select(Folder).where(
            Folder.project_id == project_id,
            Folder.parent_folder_id == folder_in.parent_folder_id,
            Folder.name == folder_in.name,
            Folder.deleted_at.is_(None),
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A folder with this name already exists in this location",
        )

    folder = Folder(
        name=folder_in.name,
        description=folder_in.description,
        project_id=project_id,
        parent_folder_id=folder_in.parent_folder_id,
        color=folder_in.color,
        icon=folder_in.icon,
        metadata_=folder_in.metadata,
    )
    db.add(folder)
    await db.commit()
    await db.refresh(folder)

    return await _build_folder_response(db, folder)


@router.get(
    "/{project_id}/folders",
    response_model=list[FolderResponse],
    summary="List Folders",
    description="List all folders in a project (flat list).",
)
async def list_folders(
    project_id: uuid.UUID,
    include_deleted: bool = Query(default=False, description="Include deleted folders"),
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> list[FolderResponse]:
    """List all folders in a project."""
    await _get_project_or_404(db, project_id)

    query = select(Folder).where(Folder.project_id == project_id)
    if not include_deleted:
        query = query.where(Folder.deleted_at.is_(None))
    query = query.order_by(Folder.display_order, Folder.name)

    result = await db.execute(query)
    folders = result.scalars().all()

    responses = []
    for f in folders:
        responses.append(await _build_folder_response(db, f))

    return responses


@router.get(
    "/{project_id}/folders/tree",
    response_model=FolderTreeResponse,
    summary="Get Folder Tree",
    description="Get hierarchical folder tree for a project.",
)
async def get_folder_tree(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> FolderTreeResponse:
    """Get folder tree structure."""
    await _get_project_or_404(db, project_id)

    # Get all folders for project with document counts
    result = await db.execute(
        select(Folder)
        .options(selectinload(Folder.project_documents))
        .where(
            Folder.project_id == project_id,
            Folder.deleted_at.is_(None),
        )
        .order_by(Folder.display_order, Folder.name)
    )
    all_folders = result.scalars().all()

    # Count root documents (no folder)
    root_doc_count = (
        await db.scalar(
            select(func.count()).where(
                ProjectDocument.project_id == project_id,
                ProjectDocument.folder_id.is_(None),
            )
        )
        or 0
    )

    # Build tree structure
    folder_map = {f.id: f for f in all_folders}

    def build_node(folder: Folder) -> FolderTreeNode:
        children = [
            build_node(folder_map[child.id])
            for child in all_folders
            if child.parent_folder_id == folder.id
        ]
        return FolderTreeNode(
            id=folder.id,
            name=folder.name,
            description=folder.description,
            parent_folder_id=folder.parent_folder_id,
            display_order=folder.display_order,
            color=folder.color,
            icon=folder.icon,
            document_count=len(folder.project_documents),
            children=children,
        )

    root_folders = []
    for f in all_folders:
        if f.parent_folder_id is None:
            root_folders.append(build_node(f))

    return FolderTreeResponse(
        project_id=project_id,
        root_document_count=root_doc_count,
        folders=root_folders,
    )


@router.get(
    "/{project_id}/folders/{folder_id}",
    response_model=FolderResponse,
    summary="Get Folder",
    description="Get folder details.",
)
async def get_folder(
    project_id: uuid.UUID,
    folder_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> FolderResponse:
    """Get a folder by ID."""
    folder = await _get_folder_or_404(db, folder_id)

    if folder.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Folder not found in this project",
        )

    return await _build_folder_response(db, folder)


@router.patch(
    "/{project_id}/folders/{folder_id}",
    response_model=FolderResponse,
    summary="Update Folder",
    description="Update folder details.",
)
async def update_folder(
    project_id: uuid.UUID,
    folder_id: uuid.UUID,
    folder_in: FolderUpdate,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> FolderResponse:
    """Update a folder."""
    folder = await _get_folder_or_404(db, folder_id)

    if folder.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Folder not found in this project",
        )

    # Update fields if provided
    if folder_in.name is not None:
        # Check for duplicate name if name is changing
        if folder_in.name != folder.name:
            existing = await db.execute(
                select(Folder).where(
                    Folder.project_id == project_id,
                    Folder.parent_folder_id == folder.parent_folder_id,
                    Folder.name == folder_in.name,
                    Folder.id != folder_id,
                    Folder.deleted_at.is_(None),
                )
            )
            if existing.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="A folder with this name already exists in this location",
                )
        folder.name = folder_in.name

    if folder_in.description is not None:
        folder.description = folder_in.description
    if folder_in.display_order is not None:
        folder.display_order = folder_in.display_order
    if folder_in.color is not None:
        folder.color = folder_in.color
    if folder_in.icon is not None:
        folder.icon = folder_in.icon
    if folder_in.metadata is not None:
        folder.metadata_ = folder_in.metadata

    folder.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(folder)

    return await _build_folder_response(db, folder)


@router.delete(
    "/{project_id}/folders/{folder_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Folder",
    description="Soft delete a folder. Documents and subfolders move to parent.",
)
async def delete_folder(
    project_id: uuid.UUID,
    folder_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> None:
    """Soft delete a folder."""
    folder = await _get_folder_or_404(db, folder_id)

    if folder.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Folder not found in this project",
        )

    # Move documents to parent folder (or root if no parent)
    await db.execute(
        ProjectDocument.__table__.update()
        .where(ProjectDocument.folder_id == folder_id)
        .values(folder_id=folder.parent_folder_id)
    )

    # Move subfolders to parent
    await db.execute(
        Folder.__table__.update()
        .where(Folder.parent_folder_id == folder_id)
        .values(parent_folder_id=folder.parent_folder_id)
    )

    # Soft delete
    folder.deleted_at = datetime.utcnow()
    await db.commit()


# =============================================================================
# Document Movement Operations
# =============================================================================


@router.patch(
    "/{project_id}/documents/{document_id}/folder",
    status_code=status.HTTP_200_OK,
    summary="Move Document to Folder",
    description="Move a document to a different folder within the project.",
)
async def move_document_to_folder(
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    request: MoveDocumentRequest,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> dict:
    """Move a document to a folder."""
    # Get project document attachment
    result = await db.execute(
        select(ProjectDocument).where(
            ProjectDocument.project_id == project_id,
            ProjectDocument.document_id == document_id,
        )
    )
    pd = result.scalar_one_or_none()

    if not pd:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not attached to this project",
        )

    # Validate target folder if specified
    if request.folder_id:
        folder = await _get_folder_or_404(db, request.folder_id)
        if folder.project_id != project_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Target folder must belong to the same project",
            )

    pd.folder_id = request.folder_id
    await db.commit()

    return {
        "status": "success",
        "document_id": str(document_id),
        "folder_id": str(request.folder_id) if request.folder_id else None,
    }


@router.post(
    "/{project_id}/folders/bulk-move-documents",
    status_code=status.HTTP_200_OK,
    summary="Bulk Move Documents",
    description="Move multiple documents to a folder at once.",
)
async def bulk_move_documents(
    project_id: uuid.UUID,
    request: BulkMoveDocumentsRequest,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> dict:
    """Move multiple documents to a folder."""
    # Validate project exists
    await _get_project_or_404(db, project_id)

    # Validate target folder
    if request.folder_id:
        folder = await _get_folder_or_404(db, request.folder_id)
        if folder.project_id != project_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Target folder must belong to the same project",
            )

    # Update all specified documents
    result = await db.execute(
        ProjectDocument.__table__.update()
        .where(
            ProjectDocument.project_id == project_id,
            ProjectDocument.document_id.in_(request.document_ids),
        )
        .values(folder_id=request.folder_id)
    )
    await db.commit()

    return {
        "status": "success",
        "moved_count": result.rowcount,
        "folder_id": str(request.folder_id) if request.folder_id else None,
    }


@router.patch(
    "/{project_id}/folders/{folder_id}/move",
    response_model=FolderResponse,
    summary="Move Folder",
    description="Move a folder to a new parent.",
)
async def move_folder(
    project_id: uuid.UUID,
    folder_id: uuid.UUID,
    request: MoveFolderRequest,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> FolderResponse:
    """Move a folder to a new parent."""
    folder = await _get_folder_or_404(db, folder_id)

    if folder.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Folder not found in this project",
        )

    # Prevent moving folder into itself
    if request.parent_folder_id == folder_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot move folder into itself",
        )

    # Validate target parent if specified
    if request.parent_folder_id:
        target = await _get_folder_or_404(db, request.parent_folder_id)
        if target.project_id != project_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Target folder must belong to the same project",
            )

        # Walk up from target to check for circular reference
        current_id = target.parent_folder_id
        while current_id:
            if current_id == folder_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot move folder into its own descendant",
                )
            parent_result = await db.execute(
                select(Folder.parent_folder_id).where(Folder.id == current_id)
            )
            current_id = parent_result.scalar_one_or_none()

        # Check for duplicate name in target parent
        existing = await db.execute(
            select(Folder).where(
                Folder.project_id == project_id,
                Folder.parent_folder_id == request.parent_folder_id,
                Folder.name == folder.name,
                Folder.id != folder_id,
                Folder.deleted_at.is_(None),
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A folder with this name already exists in the target location",
            )

    folder.parent_folder_id = request.parent_folder_id
    folder.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(folder)

    return await _build_folder_response(db, folder)
