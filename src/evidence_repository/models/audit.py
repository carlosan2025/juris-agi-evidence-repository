"""Audit log model for tracking all system actions."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from evidence_repository.models.base import Base, UUIDMixin


class AuditAction(str, enum.Enum):
    """Types of auditable actions."""

    # Document actions
    DOCUMENT_UPLOAD = "document_upload"
    DOCUMENT_DOWNLOAD = "document_download"
    DOCUMENT_DELETE = "document_delete"
    DOCUMENT_RESTORE = "document_restore"
    VERSION_CREATE = "version_create"

    # Project actions
    PROJECT_CREATE = "project_create"
    PROJECT_UPDATE = "project_update"
    PROJECT_DELETE = "project_delete"

    # Document-Project linking
    DOCUMENT_ATTACH = "document_attach"
    DOCUMENT_DETACH = "document_detach"
    VERSION_PIN = "version_pin"
    VERSION_UNPIN = "version_unpin"

    # Extraction
    EXTRACTION_START = "extraction_start"
    EXTRACTION_COMPLETE = "extraction_complete"
    EXTRACTION_FAIL = "extraction_fail"

    # Embedding
    EMBEDDING_START = "embedding_start"
    EMBEDDING_COMPLETE = "embedding_complete"
    EMBEDDING_FAIL = "embedding_fail"

    # Evidence
    SPAN_CREATE = "span_create"
    SPAN_DELETE = "span_delete"
    CLAIM_CREATE = "claim_create"
    CLAIM_DELETE = "claim_delete"
    METRIC_CREATE = "metric_create"
    METRIC_DELETE = "metric_delete"

    # Evidence packs
    EVIDENCE_PACK_CREATE = "evidence_pack_create"
    EVIDENCE_PACK_UPDATE = "evidence_pack_update"
    EVIDENCE_PACK_DELETE = "evidence_pack_delete"
    EVIDENCE_PACK_EXPORT = "evidence_pack_export"

    # Search
    SEARCH_EXECUTE = "search_execute"


class AuditLog(Base, UUIDMixin):
    """Immutable audit log entry.

    Captures all significant actions in the system for compliance and debugging.
    """

    __tablename__ = "audit_logs"

    # When
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # What
    action: Mapped[AuditAction] = mapped_column(
        Enum(AuditAction, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        index=True,
    )

    # Target entity
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)

    # Who
    actor_id: Mapped[str | None] = mapped_column(String(255), index=True)

    # Details (action-specific data)
    details: Mapped[dict] = mapped_column(JSON, default=dict)

    # Request context
    ip_address: Mapped[str | None] = mapped_column(String(45))  # IPv6 max length
    user_agent: Mapped[str | None] = mapped_column(Text)

    # Composite indexes for common queries
    __table_args__ = (
        Index("ix_audit_logs_entity", "entity_type", "entity_id"),
        Index("ix_audit_logs_actor_time", "actor_id", "timestamp"),
        Index("ix_audit_logs_action_time", "action", "timestamp"),
    )
