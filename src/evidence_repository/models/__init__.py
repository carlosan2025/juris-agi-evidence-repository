"""SQLAlchemy ORM models for Evidence Repository."""

from evidence_repository.models.analysis import (
    Conflict,
    ConflictSeverity,
    ConflictStatus,
    ConflictType,
    OpenQuestion,
    QuestionCategory,
    QuestionPriority,
    QuestionStatus,
)
from evidence_repository.models.audit import AuditAction, AuditLog
from evidence_repository.models.base import Base, TimestampMixin, UUIDMixin
from evidence_repository.models.document import Document, DocumentVersion, ExtractionStatus
from evidence_repository.models.embedding import EmbeddingChunk
from evidence_repository.models.extraction import ExtractionRun, ExtractionRunStatus
from evidence_repository.models.evidence import (
    Claim,
    EvidencePack,
    EvidencePackItem,
    Metric,
    Span,
    SpanType,
)
from evidence_repository.models.ingestion import (
    IngestionBatch,
    IngestionBatchStatus,
    IngestionItem,
    IngestionItemStatus,
    IngestionSource,
)
from evidence_repository.models.job import Job, JobStatus, JobType
from evidence_repository.models.project import Project, ProjectDocument

__all__ = [
    # Base
    "Base",
    "TimestampMixin",
    "UUIDMixin",
    # Document
    "Document",
    "DocumentVersion",
    "ExtractionStatus",
    # Project
    "Project",
    "ProjectDocument",
    # Job
    "Job",
    "JobStatus",
    "JobType",
    # Ingestion
    "IngestionBatch",
    "IngestionBatchStatus",
    "IngestionItem",
    "IngestionItemStatus",
    "IngestionSource",
    # Evidence
    "Span",
    "SpanType",
    "Claim",
    "Metric",
    "EvidencePack",
    "EvidencePackItem",
    # Analysis
    "Conflict",
    "ConflictType",
    "ConflictStatus",
    "ConflictSeverity",
    "OpenQuestion",
    "QuestionCategory",
    "QuestionPriority",
    "QuestionStatus",
    # Embedding
    "EmbeddingChunk",
    # Extraction
    "ExtractionRun",
    "ExtractionRunStatus",
    # Audit
    "AuditLog",
    "AuditAction",
]
