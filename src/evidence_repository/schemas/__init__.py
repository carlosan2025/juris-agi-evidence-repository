"""Pydantic schemas for API request/response models."""

from evidence_repository.schemas.common import (
    ErrorResponse,
    HealthResponse,
    PaginatedResponse,
    PaginationParams,
)
from evidence_repository.schemas.document import (
    DocumentCreate,
    DocumentResponse,
    DocumentVersionResponse,
    ExtractionTriggerResponse,
)
from evidence_repository.schemas.evidence import (
    ClaimCreate,
    ClaimResponse,
    EvidencePackCreate,
    EvidencePackItemCreate,
    EvidencePackItemResponse,
    EvidencePackResponse,
    LocatorSchema,
    MetricCreate,
    MetricResponse,
    SpanCreate,
    SpanResponse,
)
from evidence_repository.schemas.project import (
    AttachDocumentRequest,
    ProjectCreate,
    ProjectDocumentResponse,
    ProjectResponse,
    ProjectUpdate,
)
from evidence_repository.schemas.search import (
    SearchQuery,
    SearchResult,
    SearchResultItem,
)
from evidence_repository.schemas.job import (
    JobResponse,
    JobEnqueueResponse,
    BulkJobEnqueueResponse,
    JobListResponse,
    DocumentUploadRequest,
    BulkFolderIngestRequest,
    URLIngestRequest,
    BatchExtractRequest,
    BatchEmbedRequest,
)

__all__ = [
    # Common
    "ErrorResponse",
    "HealthResponse",
    "PaginationParams",
    "PaginatedResponse",
    # Document
    "DocumentCreate",
    "DocumentResponse",
    "DocumentVersionResponse",
    "ExtractionTriggerResponse",
    # Project
    "ProjectCreate",
    "ProjectUpdate",
    "ProjectResponse",
    "AttachDocumentRequest",
    "ProjectDocumentResponse",
    # Evidence
    "LocatorSchema",
    "SpanCreate",
    "SpanResponse",
    "ClaimCreate",
    "ClaimResponse",
    "MetricCreate",
    "MetricResponse",
    "EvidencePackCreate",
    "EvidencePackResponse",
    "EvidencePackItemCreate",
    "EvidencePackItemResponse",
    # Search
    "SearchQuery",
    "SearchResult",
    "SearchResultItem",
    # Jobs
    "JobResponse",
    "JobEnqueueResponse",
    "BulkJobEnqueueResponse",
    "JobListResponse",
    "DocumentUploadRequest",
    "BulkFolderIngestRequest",
    "URLIngestRequest",
    "BatchExtractRequest",
    "BatchEmbedRequest",
]
