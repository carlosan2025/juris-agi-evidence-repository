"""Project business service layer."""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from evidence_repository.models.document import Document, DocumentVersion
from evidence_repository.models.project import Project, ProjectDocument


class ProjectService:
    """High-level project operations."""

    def __init__(self, db: AsyncSession):
        """Initialize project service.

        Args:
            db: Database session.
        """
        self.db = db

    async def create_project(
        self,
        name: str,
        description: str | None = None,
        case_ref: str | None = None,
        metadata: dict | None = None,
    ) -> Project:
        """Create a new project.

        Args:
            name: Project name.
            description: Optional description.
            case_ref: Optional external case reference.
            metadata: Optional metadata.

        Returns:
            Created project.
        """
        project = Project(
            name=name,
            description=description,
            case_ref=case_ref,
            metadata_=metadata or {},
        )
        self.db.add(project)
        await self.db.flush()
        return project

    async def get_project(
        self,
        project_id: uuid.UUID,
        include_documents: bool = False,
        include_evidence: bool = False,
    ) -> Project | None:
        """Get a project by ID.

        Args:
            project_id: Project ID.
            include_documents: Whether to load attached documents.
            include_evidence: Whether to load claims and metrics.

        Returns:
            Project or None.
        """
        query = select(Project).where(Project.id == project_id)

        if include_documents:
            query = query.options(
                selectinload(Project.project_documents).selectinload(
                    ProjectDocument.document
                )
            )

        if include_evidence:
            query = query.options(
                selectinload(Project.claims),
                selectinload(Project.metrics),
                selectinload(Project.evidence_packs),
            )

        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def attach_document(
        self,
        project: Project,
        document: Document,
        pinned_version: DocumentVersion | None = None,
        attached_by: str | None = None,
        notes: str | None = None,
    ) -> ProjectDocument:
        """Attach a document to a project.

        Args:
            project: Target project.
            document: Document to attach.
            pinned_version: Optional version to pin to.
            attached_by: ID of user who attached it.
            notes: Optional notes.

        Returns:
            ProjectDocument junction record.

        Raises:
            ValueError: If document is already attached.
        """
        # Check if already attached
        existing = await self.db.execute(
            select(ProjectDocument).where(
                ProjectDocument.project_id == project.id,
                ProjectDocument.document_id == document.id,
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError("Document already attached to this project")

        project_document = ProjectDocument(
            project_id=project.id,
            document_id=document.id,
            pinned_version_id=pinned_version.id if pinned_version else None,
            attached_by=attached_by,
            notes=notes,
        )
        self.db.add(project_document)
        await self.db.flush()
        return project_document

    async def detach_document(
        self,
        project: Project,
        document: Document,
    ) -> bool:
        """Detach a document from a project.

        Args:
            project: Source project.
            document: Document to detach.

        Returns:
            True if detached, False if wasn't attached.
        """
        result = await self.db.execute(
            select(ProjectDocument).where(
                ProjectDocument.project_id == project.id,
                ProjectDocument.document_id == document.id,
            )
        )
        project_document = result.scalar_one_or_none()

        if not project_document:
            return False

        await self.db.delete(project_document)
        await self.db.flush()
        return True

    async def pin_document_version(
        self,
        project: Project,
        document: Document,
        version: DocumentVersion,
    ) -> ProjectDocument:
        """Pin a document to a specific version within a project.

        Args:
            project: Project context.
            document: Document to pin.
            version: Version to pin to.

        Returns:
            Updated ProjectDocument.

        Raises:
            ValueError: If document not attached or version doesn't belong to document.
        """
        result = await self.db.execute(
            select(ProjectDocument).where(
                ProjectDocument.project_id == project.id,
                ProjectDocument.document_id == document.id,
            )
        )
        project_document = result.scalar_one_or_none()

        if not project_document:
            raise ValueError("Document not attached to this project")

        if version.document_id != document.id:
            raise ValueError("Version does not belong to this document")

        project_document.pinned_version_id = version.id
        await self.db.flush()
        return project_document

    async def unpin_document_version(
        self,
        project: Project,
        document: Document,
    ) -> ProjectDocument:
        """Unpin a document to use latest version.

        Args:
            project: Project context.
            document: Document to unpin.

        Returns:
            Updated ProjectDocument.

        Raises:
            ValueError: If document not attached.
        """
        result = await self.db.execute(
            select(ProjectDocument).where(
                ProjectDocument.project_id == project.id,
                ProjectDocument.document_id == document.id,
            )
        )
        project_document = result.scalar_one_or_none()

        if not project_document:
            raise ValueError("Document not attached to this project")

        project_document.pinned_version_id = None
        await self.db.flush()
        return project_document

    async def get_project_documents(
        self, project: Project
    ) -> list[ProjectDocument]:
        """Get all documents attached to a project.

        Args:
            project: Project to get documents for.

        Returns:
            List of ProjectDocument junction records with documents loaded.
        """
        result = await self.db.execute(
            select(ProjectDocument)
            .options(
                selectinload(ProjectDocument.document).selectinload(
                    Document.versions
                ),
                selectinload(ProjectDocument.pinned_version),
            )
            .where(ProjectDocument.project_id == project.id)
            .order_by(ProjectDocument.attached_at.desc())
        )
        return list(result.scalars().all())

    async def delete_project(
        self,
        project: Project,
        hard_delete: bool = False,
    ) -> None:
        """Delete a project.

        Args:
            project: Project to delete.
            hard_delete: If True, permanently delete. If False, soft delete.
        """
        if hard_delete:
            await self.db.delete(project)
        else:
            project.deleted_at = datetime.utcnow()

        await self.db.flush()

    async def restore_project(self, project: Project) -> None:
        """Restore a soft-deleted project.

        Args:
            project: Project to restore.
        """
        project.deleted_at = None
        await self.db.flush()
