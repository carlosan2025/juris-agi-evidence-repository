"""Deletion tracking models for safe, auditable document deletion."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from evidence_repository.models.base import Base, UUIDMixin


class DeletionTaskStatus(str, enum.Enum):
    """Status of an individual deletion task."""

    PENDING = "pending"  # Task created, waiting to be processed
    IN_PROGRESS = "in_progress"  # Currently being processed
    COMPLETED = "completed"  # Successfully deleted
    FAILED = "failed"  # Deletion failed
    SKIPPED = "skipped"  # Resource didn't exist or already deleted


class DeletionTaskType(str, enum.Enum):
    """Type of resource being deleted.

    Tasks are processed in this order (dependencies must be deleted before dependents):
    1. STORAGE_FILE - Files in R2/S3
    2. EMBEDDING_CHUNKS - Vector embeddings (depends on version)
    3. SPANS - Text spans (depends on version)
    4. FACTS_* - Fact extraction results (depends on document/version)
    5. QUALITY_* - Quality analysis results (depends on document/version)
    6. EXTRACTION_RUNS - Extraction metadata (depends on version)
    7. PROJECT_DOCUMENTS - Project associations (depends on document)
    8. DOCUMENT_VERSIONS - Version records (depends on document)
    9. DOCUMENT_RECORD - Final document record (last step)
    """

    STORAGE_FILE = "storage_file"
    EMBEDDING_CHUNKS = "embedding_chunks"
    SPANS = "spans"
    FACTS_CLAIMS = "facts_claims"
    FACTS_METRICS = "facts_metrics"
    FACTS_CONSTRAINTS = "facts_constraints"
    FACTS_RISKS = "facts_risks"
    QUALITY_CONFLICTS = "quality_conflicts"
    QUALITY_QUESTIONS = "quality_questions"
    EXTRACTION_RUNS = "extraction_runs"
    PROJECT_DOCUMENTS = "project_documents"
    DOCUMENT_VERSIONS = "document_versions"
    DOCUMENT_RECORD = "document_record"  # Final step - only after all above complete


# Processing order for task types (lower number = delete first)
TASK_TYPE_ORDER = {
    DeletionTaskType.STORAGE_FILE: 1,
    DeletionTaskType.EMBEDDING_CHUNKS: 2,
    DeletionTaskType.SPANS: 3,
    DeletionTaskType.FACTS_CLAIMS: 4,
    DeletionTaskType.FACTS_METRICS: 4,
    DeletionTaskType.FACTS_CONSTRAINTS: 4,
    DeletionTaskType.FACTS_RISKS: 4,
    DeletionTaskType.QUALITY_CONFLICTS: 5,
    DeletionTaskType.QUALITY_QUESTIONS: 5,
    DeletionTaskType.EXTRACTION_RUNS: 6,
    DeletionTaskType.PROJECT_DOCUMENTS: 7,
    DeletionTaskType.DOCUMENT_VERSIONS: 8,
    DeletionTaskType.DOCUMENT_RECORD: 9,
}


class DeletionTask(Base, UUIDMixin):
    """Tracks individual resource deletion within a document deletion process.

    Each task represents one resource (or batch of resources) to be deleted.
    Tasks are processed in dependency order to ensure clean cascade deletion.
    """

    __tablename__ = "deletion_tasks"

    # Reference to the document being deleted
    # Note: NOT using CASCADE here - we manage deletion manually
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,  # Allow null after document record is finally deleted
        index=True,
    )

    # Version reference (for version-specific resources)
    version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
    )

    # Task details
    task_type: Mapped[DeletionTaskType] = mapped_column(
        Enum(DeletionTaskType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    resource_id: Mapped[str] = mapped_column(
        String(1024),  # UUID string or storage path
        nullable=False,
    )
    resource_count: Mapped[int] = mapped_column(
        Integer,
        default=1,  # Number of items (for batch deletes like "500 embeddings")
    )

    # Processing order within the document deletion
    processing_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Status tracking
    status: Mapped[DeletionTaskStatus] = mapped_column(
        Enum(DeletionTaskStatus, values_callable=lambda x: [e.value for e in x]),
        default=DeletionTaskStatus.PENDING,
        nullable=False,
        index=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    document: Mapped["Document"] = relationship(  # noqa: F821
        "Document",
        foreign_keys=[document_id],
    )

    # Indexes
    __table_args__ = (
        Index("ix_deletion_tasks_document_status", "document_id", "status"),
        Index("ix_deletion_tasks_document_order", "document_id", "processing_order"),
    )

    def __repr__(self) -> str:
        return (
            f"<DeletionTask {self.task_type.value} "
            f"doc={self.document_id} status={self.status.value}>"
        )
