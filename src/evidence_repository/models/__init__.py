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
from evidence_repository.models.deletion import (
    DeletionTask,
    DeletionTaskStatus,
    DeletionTaskType,
    TASK_TYPE_ORDER,
)
from evidence_repository.models.document import (
    DeletionStatus,
    Document,
    DocumentVersion,
    ExtractionStatus,
)
from evidence_repository.models.embedding import EmbeddingChunk
from evidence_repository.models.extraction import ExtractionRun, ExtractionRunStatus
from evidence_repository.models.evidence import (
    Certainty,
    Claim,
    ClaimType,
    EvidencePack,
    EvidencePackItem,
    Metric,
    MetricType,
    Reliability,
    Span,
    SpanType,
)
from evidence_repository.models.folder import Folder
from evidence_repository.models.extraction_level import (
    ComputeMode,
    ExtractionLevel,
    ExtractionLevelCode,
    ExtractionProfile,
    ExtractionProfileCode,
    ExtractionRunStatus as FactExtractionRunStatus,
    ExtractionSetting,
    FactExtractionRun,
    ProcessContext,
    ScopeType,
)
from evidence_repository.models.facts import (
    ConstraintType,
    FactCertainty,
    FactClaim,
    FactConstraint,
    FactMetric,
    FactRisk,
    RiskSeverity,
    SourceReliability,
)
from evidence_repository.models.ingestion import (
    IngestionBatch,
    IngestionBatchStatus,
    IngestionItem,
    IngestionItemStatus,
    IngestionSource,
)
from evidence_repository.models.integration_key import IntegrationKey, IntegrationProvider
from evidence_repository.models.job import Job, JobStatus, JobType
from evidence_repository.models.project import Project, ProjectDocument
from evidence_repository.models.quality import (
    ConflictSeverity as QualityConflictSeverity,
    QuestionCategory as QualityQuestionCategory,
    QualityConflict,
    QualityOpenQuestion,
)

__all__ = [
    # Base
    "Base",
    "TimestampMixin",
    "UUIDMixin",
    # Document
    "Document",
    "DocumentVersion",
    "ExtractionStatus",
    "DeletionStatus",
    # Deletion Tracking
    "DeletionTask",
    "DeletionTaskStatus",
    "DeletionTaskType",
    "TASK_TYPE_ORDER",
    # Project
    "Project",
    "ProjectDocument",
    # Folder
    "Folder",
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
    "ClaimType",
    "Metric",
    "MetricType",
    "Certainty",
    "Reliability",
    "EvidencePack",
    "EvidencePackItem",
    # Analysis (legacy)
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
    # Extraction (legacy)
    "ExtractionRun",
    "ExtractionRunStatus",
    # Multi-level Extraction
    "ExtractionProfile",
    "ExtractionProfileCode",
    "ExtractionLevel",
    "ExtractionLevelCode",
    "ExtractionSetting",
    "FactExtractionRun",
    "FactExtractionRunStatus",
    "ComputeMode",
    "ProcessContext",
    "ScopeType",
    # Facts
    "FactClaim",
    "FactMetric",
    "FactConstraint",
    "FactRisk",
    "FactCertainty",
    "SourceReliability",
    "ConstraintType",
    "RiskSeverity",
    # Quality
    "QualityConflict",
    "QualityOpenQuestion",
    "QualityConflictSeverity",
    "QualityQuestionCategory",
    # Audit
    "AuditLog",
    "AuditAction",
    # Integration Keys
    "IntegrationKey",
    "IntegrationProvider",
]
