"""Project and ProjectDocument models."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from evidence_repository.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from evidence_repository.models.document import Document, DocumentVersion
    from evidence_repository.models.evidence import Claim, EvidencePack, Metric
    from evidence_repository.models.folder import Folder


class Project(Base, UUIDMixin, TimestampMixin):
    """Evaluation context (case file) for grouping documents and evidence.

    Projects reference documents without duplicating them. Documents can be
    attached to multiple projects.
    """

    __tablename__ = "projects"

    # Core fields
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    # External reference (e.g., case number)
    case_ref: Mapped[str | None] = mapped_column(String(255), index=True)

    # Flexible metadata
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)

    # Soft delete
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    project_documents: Mapped[list["ProjectDocument"]] = relationship(
        "ProjectDocument",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    claims: Mapped[list["Claim"]] = relationship(
        "Claim",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    metrics: Mapped[list["Metric"]] = relationship(
        "Metric",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    evidence_packs: Mapped[list["EvidencePack"]] = relationship(
        "EvidencePack",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    folders: Mapped[list["Folder"]] = relationship(
        "Folder",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="Folder.display_order, Folder.name",
    )

    # Indexes
    __table_args__ = (
        Index("ix_projects_name", "name"),
        Index("ix_projects_deleted_at", "deleted_at"),
    )

    @property
    def documents(self) -> list["Document"]:
        """Get all documents attached to this project."""
        return [pd.document for pd in self.project_documents]

    @property
    def is_deleted(self) -> bool:
        """Check if project is soft-deleted."""
        return self.deleted_at is not None


class ProjectDocument(Base, UUIDMixin):
    """Junction table linking projects to documents.

    Represents the attachment of a document to a project, optionally
    pinning to a specific version.
    """

    __tablename__ = "project_documents"

    # Foreign keys
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Optional: pin to specific version (null = latest)
    pinned_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_versions.id", ondelete="SET NULL"),
    )

    # Attachment metadata
    attached_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    attached_by: Mapped[str | None] = mapped_column(String(255))

    # Notes about why this document was attached
    notes: Mapped[str | None] = mapped_column(Text)

    # Folder assignment (null = project root)
    folder_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("folders.id", ondelete="SET NULL"),
        index=True,
    )

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="project_documents")
    document: Mapped["Document"] = relationship("Document", back_populates="project_documents")
    pinned_version: Mapped["DocumentVersion | None"] = relationship("DocumentVersion")
    folder: Mapped["Folder | None"] = relationship(
        "Folder",
        back_populates="project_documents",
        foreign_keys=[folder_id],
    )

    # Constraints and indexes
    __table_args__ = (
        UniqueConstraint("project_id", "document_id", name="uq_project_document"),
        Index("ix_project_documents_project_id", "project_id"),
        Index("ix_project_documents_document_id", "document_id"),
    )

    @property
    def effective_version(self) -> "DocumentVersion | None":
        """Get the effective version (pinned or latest)."""
        if self.pinned_version_id:
            return self.pinned_version
        return self.document.latest_version
