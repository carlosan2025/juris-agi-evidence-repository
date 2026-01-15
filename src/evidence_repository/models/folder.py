"""Folder model for organizing documents within projects."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from evidence_repository.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from evidence_repository.models.project import Project, ProjectDocument


class Folder(Base, UUIDMixin, TimestampMixin):
    """Folder for organizing documents within a project.

    Supports nested folder hierarchy through self-referential parent_folder_id.
    Each folder belongs to exactly one project.
    """

    __tablename__ = "folders"

    # Core fields
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    # Project ownership - folders are project-specific
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Self-referential for nested folders (null = root level)
    parent_folder_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("folders.id", ondelete="CASCADE"),
        index=True,
    )

    # Display order within parent (for custom sorting)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Folder color/icon for UI customization
    color: Mapped[str | None] = mapped_column(String(7))  # Hex color e.g. #FF5733
    icon: Mapped[str | None] = mapped_column(String(50))  # Icon identifier

    # Flexible metadata
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)

    # Soft delete
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    project: Mapped["Project"] = relationship(
        "Project",
        back_populates="folders",
    )
    parent_folder: Mapped["Folder | None"] = relationship(
        "Folder",
        remote_side="Folder.id",
        back_populates="child_folders",
        foreign_keys=[parent_folder_id],
    )
    child_folders: Mapped[list["Folder"]] = relationship(
        "Folder",
        back_populates="parent_folder",
        cascade="all, delete-orphan",
        order_by="Folder.display_order, Folder.name",
        foreign_keys="Folder.parent_folder_id",
    )
    project_documents: Mapped[list["ProjectDocument"]] = relationship(
        "ProjectDocument",
        back_populates="folder",
        foreign_keys="ProjectDocument.folder_id",
    )

    # Constraints and indexes
    __table_args__ = (
        # Unique folder name within same parent (and project)
        UniqueConstraint(
            "project_id",
            "parent_folder_id",
            "name",
            name="uq_folder_name_in_parent",
        ),
        Index("ix_folders_project_parent", "project_id", "parent_folder_id"),
        Index("ix_folders_deleted_at", "deleted_at"),
    )

    @property
    def is_root(self) -> bool:
        """Check if this is a root-level folder."""
        return self.parent_folder_id is None

    @property
    def is_deleted(self) -> bool:
        """Check if folder is soft-deleted."""
        return self.deleted_at is not None

    @property
    def path(self) -> str:
        """Get full path from root (e.g., '/Research/2024/Q1')."""
        parts = [self.name]
        current = self.parent_folder
        while current:
            parts.insert(0, current.name)
            current = current.parent_folder
        return "/" + "/".join(parts)

    def __repr__(self) -> str:
        return f"<Folder(id={self.id}, name='{self.name}', project_id={self.project_id})>"
