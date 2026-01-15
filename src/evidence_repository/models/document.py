"""Document and DocumentVersion models."""

import enum
import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Date, DateTime, Enum, Float, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from evidence_repository.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from evidence_repository.models.embedding import EmbeddingChunk
    from evidence_repository.models.evidence import Span
    from evidence_repository.models.extraction import ExtractionRun
    from evidence_repository.models.project import ProjectDocument


class UploadStatus(str, enum.Enum):
    """Status of file upload to storage."""

    PENDING = "pending"  # Presigned URL generated, awaiting upload
    UPLOADED = "uploaded"  # File successfully uploaded to storage
    FAILED = "failed"  # Upload failed or timed out


class ExtractionStatus(str, enum.Enum):
    """Status of text extraction for a document version."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ProcessingStatus(str, enum.Enum):
    """Overall processing status tracking the full pipeline.

    Pipeline stages in order:
    1. UPLOADED - File is in storage
    2. EXTRACTED - Text extraction complete
    3. SPANS_BUILT - Evidence spans created
    4. EMBEDDED - Vector embeddings generated
    5. FACTS_EXTRACTED - Metrics/claims extracted via LLM
    6. QUALITY_CHECKED - Conflict/quality analysis complete

    FAILED indicates processing stopped due to an error.
    """

    PENDING = "pending"  # Awaiting processing (upload may be pending)
    UPLOADED = "uploaded"  # File in storage, awaiting extraction
    EXTRACTED = "extracted"  # Text extraction complete
    SPANS_BUILT = "spans_built"  # Evidence spans created
    EMBEDDED = "embedded"  # Vector embeddings generated
    FACTS_EXTRACTED = "facts_extracted"  # Metrics/claims extracted
    QUALITY_CHECKED = "quality_checked"  # Full pipeline complete
    FAILED = "failed"  # Processing failed at some stage


class DocumentType(str, enum.Enum):
    """Document classification type (inspired by Agent-K)."""

    ACADEMIC_PAPER = "academic_paper"
    NEWS_ARTICLE = "news_article"
    BLOG_POST = "blog_post"
    COMPANY_REPORT = "company_report"
    FINANCIAL_STATEMENT = "financial_statement"
    LEGAL_DOCUMENT = "legal_document"
    TECHNICAL_DOCUMENTATION = "technical_documentation"
    PRESS_RELEASE = "press_release"
    MARKETING_MATERIAL = "marketing_material"
    GOVERNMENT_DOCUMENT = "government_document"
    PATENT = "patent"
    PRESENTATION = "presentation"
    WHITEPAPER = "whitepaper"
    CASE_STUDY = "case_study"
    POLICY_DOCUMENT = "policy_document"
    REGULATORY_FILING = "regulatory_filing"
    INTERNAL_MEMO = "internal_memo"
    CONTRACT = "contract"
    INVOICE = "invoice"
    SPREADSHEET_DATA = "spreadsheet_data"
    UNKNOWN = "unknown"


class SourceType(str, enum.Enum):
    """Source of document ingestion."""

    UPLOAD = "upload"
    URL = "url"
    EMAIL = "email"
    API = "api"
    CRAWLER = "crawler"
    BATCH_IMPORT = "batch_import"
    UNKNOWN = "unknown"


class Document(Base, UUIDMixin, TimestampMixin):
    """Global document asset.

    Documents are standalone entities that can be attached to multiple projects.
    Each document can have multiple versions.
    """

    __tablename__ = "documents"

    # Core fields
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)

    # Content hash for deduplication (SHA-256 of original file)
    file_hash: Mapped[str | None] = mapped_column(String(64), index=True)

    # Industry profile for extraction (vc, pharma, insurance, general)
    profile_code: Mapped[str] = mapped_column(String(50), default="general", nullable=False)

    # Document classification (Agent-K inspired)
    document_type: Mapped[DocumentType | None] = mapped_column(
        Enum(DocumentType, values_callable=lambda x: [e.value for e in x]),
        default=DocumentType.UNKNOWN,
    )

    # Source tracking
    source_type: Mapped[SourceType | None] = mapped_column(
        Enum(SourceType, values_callable=lambda x: [e.value for e in x]),
        default=SourceType.UNKNOWN,
    )
    source_url: Mapped[str | None] = mapped_column(Text)

    # Extracted metadata arrays (for efficient filtering)
    sectors: Mapped[list[str] | None] = mapped_column(ARRAY(String(100)))
    main_topics: Mapped[list[str] | None] = mapped_column(ARRAY(String(200)))
    geographies: Mapped[list[str] | None] = mapped_column(ARRAY(String(100)))
    company_names: Mapped[list[str] | None] = mapped_column(ARRAY(String(200)))
    authors: Mapped[list[str] | None] = mapped_column(ARRAY(String(200)))

    # Publishing info
    publishing_organization: Mapped[str | None] = mapped_column(String(300))
    publication_date: Mapped[date | None] = mapped_column(Date)

    # Flexible metadata storage
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)

    # Soft delete support
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    versions: Mapped[list["DocumentVersion"]] = relationship(
        "DocumentVersion",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentVersion.version_number.desc()",
    )
    project_documents: Mapped[list["ProjectDocument"]] = relationship(
        "ProjectDocument",
        back_populates="document",
        cascade="all, delete-orphan",
    )

    # Indexes
    __table_args__ = (
        Index("ix_documents_filename", "filename"),
        Index("ix_documents_content_type", "content_type"),
        Index("ix_documents_deleted_at", "deleted_at"),
    )

    @property
    def latest_version(self) -> "DocumentVersion | None":
        """Get the latest version of this document."""
        return self.versions[0] if self.versions else None

    @property
    def is_deleted(self) -> bool:
        """Check if document is soft-deleted."""
        return self.deleted_at is not None


class DocumentVersion(Base, UUIDMixin):
    """Immutable version of a document.

    Each version represents a specific state of the document file.
    Versions are immutable once created - edits create new versions.
    """

    __tablename__ = "document_versions"

    # Foreign key to parent document
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Version tracking
    version_number: Mapped[int] = mapped_column(nullable=False, default=1)

    # Storage location (relative path in storage backend)
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)

    # File metadata
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    # Upload status (tracks whether file is actually in storage)
    # TEMPORARY FIX: Column commented out until migration 009 runs on production
    # Once migration 009_add_upload_status runs, uncomment this and remove the property below
    # upload_status: Mapped[UploadStatus] = mapped_column(
    #     Enum(UploadStatus, values_callable=lambda x: [e.value for e in x]),
    #     default=UploadStatus.UPLOADED,  # Default for direct uploads
    #     nullable=False,
    # )

    @property
    def upload_status(self) -> UploadStatus:
        """Get upload status.

        TEMPORARY: Returns UPLOADED until migration runs and column is added.
        All existing documents were uploaded via direct upload, so UPLOADED is correct.
        """
        return UploadStatus.UPLOADED

    # Overall processing status (tracks progress through full pipeline)
    # TEMPORARY FIX: Column commented out until migration runs on production
    # Once migration 010_add_processing_status runs, uncomment this and remove the property below
    # processing_status: Mapped[ProcessingStatus | None] = mapped_column(
    #     Enum(ProcessingStatus, values_callable=lambda x: [e.value for e in x]),
    #     default=ProcessingStatus.PENDING,
    #     nullable=True,
    # )

    @property
    def processing_status(self) -> ProcessingStatus | None:
        """Get processing status derived from extraction_status.

        TEMPORARY: Returns derived status until migration runs and column is added.
        """
        # Derive from extraction_status for backwards compatibility
        if self.extraction_status == ExtractionStatus.COMPLETED:
            return ProcessingStatus.EXTRACTED
        elif self.extraction_status == ExtractionStatus.PROCESSING:
            return ProcessingStatus.UPLOADED
        elif self.extraction_status == ExtractionStatus.FAILED:
            return ProcessingStatus.FAILED
        return ProcessingStatus.PENDING

    # Extracted text content
    extracted_text: Mapped[str | None] = mapped_column(Text)
    extraction_status: Mapped[ExtractionStatus] = mapped_column(
        Enum(ExtractionStatus, values_callable=lambda x: [e.value for e in x]),
        default=ExtractionStatus.PENDING,
        nullable=False,
    )
    extraction_error: Mapped[str | None] = mapped_column(Text)
    extracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Page/sheet count (for PDFs, spreadsheets)
    page_count: Mapped[int | None] = mapped_column()

    # Truthfulness assessment (Agent-K inspired)
    truthfulness_score: Mapped[float | None] = mapped_column(Float)
    bias_score: Mapped[float | None] = mapped_column(Float)
    credibility_assessment: Mapped[dict | None] = mapped_column(JSON)

    # Version metadata
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    document: Mapped["Document"] = relationship("Document", back_populates="versions")
    spans: Mapped[list["Span"]] = relationship(
        "Span",
        back_populates="document_version",
        cascade="all, delete-orphan",
    )
    embedding_chunks: Mapped[list["EmbeddingChunk"]] = relationship(
        "EmbeddingChunk",
        back_populates="document_version",
        cascade="all, delete-orphan",
    )
    extraction_runs: Mapped[list["ExtractionRun"]] = relationship(
        "ExtractionRun",
        back_populates="document_version",
        cascade="all, delete-orphan",
        order_by="ExtractionRun.created_at.desc()",
    )

    # Indexes
    __table_args__ = (
        Index("ix_document_versions_document_version", "document_id", "version_number"),
        Index("ix_document_versions_extraction_status", "extraction_status"),
    )
