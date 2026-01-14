"""Initial schema for Evidence Repository.

Revision ID: 001
Revises:
Create Date: 2025-01-12
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable required extensions
    op.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\"")
    op.execute("CREATE EXTENSION IF NOT EXISTS \"vector\"")

    # Create enum types manually with raw SQL to avoid duplication issues
    op.execute("CREATE TYPE extractionstatus AS ENUM ('pending', 'processing', 'completed', 'failed')")
    op.execute("CREATE TYPE spantype AS ENUM ('text', 'table', 'figure', 'citation', 'heading', 'footnote', 'other')")
    op.execute("""CREATE TYPE auditaction AS ENUM (
        'document_upload', 'document_download', 'document_delete', 'document_restore',
        'version_create', 'project_create', 'project_update', 'project_delete',
        'document_attach', 'document_detach', 'version_pin', 'version_unpin',
        'extraction_start', 'extraction_complete', 'extraction_fail',
        'embedding_start', 'embedding_complete', 'embedding_fail',
        'span_create', 'span_delete', 'claim_create', 'claim_delete',
        'metric_create', 'metric_delete', 'evidence_pack_create',
        'evidence_pack_update', 'evidence_pack_delete', 'evidence_pack_export',
        'search_execute'
    )""")

    # Create documents table
    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("content_type", sa.String(255), nullable=False),
        sa.Column("original_filename", sa.String(512), nullable=False),
        sa.Column("file_hash", sa.String(64), index=True),
        sa.Column("metadata", postgresql.JSON, server_default="{}"),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_documents_filename", "documents", ["filename"])
    op.create_index("ix_documents_content_type", "documents", ["content_type"])
    op.create_index("ix_documents_deleted_at", "documents", ["deleted_at"])

    # Create document_versions table
    op.create_table(
        "document_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("version_number", sa.Integer, nullable=False, server_default="1"),
        sa.Column("storage_path", sa.String(1024), nullable=False),
        sa.Column("file_size", sa.BigInteger, nullable=False),
        sa.Column("file_hash", sa.String(64), nullable=False),
        sa.Column("extracted_text", sa.Text),
        sa.Column("extraction_status", postgresql.ENUM("pending", "processing", "completed", "failed", name="extractionstatus", create_type=False), nullable=False, server_default="pending"),
        sa.Column("extraction_error", sa.Text),
        sa.Column("extracted_at", sa.DateTime(timezone=True)),
        sa.Column("page_count", sa.Integer),
        sa.Column("metadata", postgresql.JSON, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_document_versions_document_version", "document_versions", ["document_id", "version_number"])
    op.create_index("ix_document_versions_extraction_status", "document_versions", ["extraction_status"])

    # Create projects table
    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("case_ref", sa.String(255), index=True),
        sa.Column("metadata", postgresql.JSON, server_default="{}"),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_projects_name", "projects", ["name"])
    op.create_index("ix_projects_deleted_at", "projects", ["deleted_at"])

    # Create project_documents table
    op.create_table(
        "project_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pinned_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("document_versions.id", ondelete="SET NULL")),
        sa.Column("attached_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("attached_by", sa.String(255)),
        sa.Column("notes", sa.Text),
        sa.UniqueConstraint("project_id", "document_id", name="uq_project_document"),
    )
    op.create_index("ix_project_documents_project_id", "project_documents", ["project_id"])
    op.create_index("ix_project_documents_document_id", "project_documents", ["document_id"])

    # Create spans table
    op.create_table(
        "spans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("document_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("start_locator", postgresql.JSON, nullable=False),
        sa.Column("end_locator", postgresql.JSON),
        sa.Column("text_content", sa.Text, nullable=False),
        sa.Column("span_type", postgresql.ENUM("text", "table", "figure", "citation", "heading", "footnote", "other", name="spantype", create_type=False), nullable=False, server_default="text"),
        sa.Column("metadata", postgresql.JSON, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_spans_span_type", "spans", ["span_type"])

    # Create claims table
    op.create_table(
        "claims",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("span_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("spans.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("claim_text", sa.Text, nullable=False),
        sa.Column("claim_type", sa.String(100)),
        sa.Column("confidence", sa.Float),
        sa.Column("metadata", postgresql.JSON, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # Create metrics table
    op.create_table(
        "metrics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("span_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("spans.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("metric_name", sa.String(255), nullable=False),
        sa.Column("metric_value", sa.String(255), nullable=False),
        sa.Column("unit", sa.String(100)),
        sa.Column("metadata", postgresql.JSON, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # Create embedding_chunks table
    op.create_table(
        "embedding_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("document_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("span_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("spans.id", ondelete="SET NULL"), index=True),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("embedding", Vector(1536), nullable=False),
        sa.Column("metadata", postgresql.JSON, server_default="{}"),
        sa.Column("char_start", sa.Integer),
        sa.Column("char_end", sa.Integer),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_embedding_chunks_document_version", "embedding_chunks", ["document_version_id"])
    op.create_index("ix_embedding_chunks_chunk_index", "embedding_chunks", ["document_version_id", "chunk_index"])

    # Create vector index for similarity search (using IVFFlat for faster queries)
    op.execute("""
        CREATE INDEX ix_embedding_chunks_embedding
        ON embedding_chunks
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100)
    """)

    # Create evidence_packs table
    op.create_table(
        "evidence_packs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("created_by", sa.String(255)),
        sa.Column("metadata", postgresql.JSON, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # Create evidence_pack_items table
    op.create_table(
        "evidence_pack_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("evidence_pack_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("evidence_packs.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("span_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("spans.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("claims.id", ondelete="SET NULL")),
        sa.Column("metric_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("metrics.id", ondelete="SET NULL")),
        sa.Column("order_index", sa.Integer, server_default="0"),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # Create audit_logs table
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False, index=True),
        sa.Column("action", postgresql.ENUM(
            "document_upload", "document_download", "document_delete", "document_restore",
            "version_create", "project_create", "project_update", "project_delete",
            "document_attach", "document_detach", "version_pin", "version_unpin",
            "extraction_start", "extraction_complete", "extraction_fail",
            "embedding_start", "embedding_complete", "embedding_fail",
            "span_create", "span_delete", "claim_create", "claim_delete",
            "metric_create", "metric_delete", "evidence_pack_create",
            "evidence_pack_update", "evidence_pack_delete", "evidence_pack_export",
            "search_execute",
            name="auditaction", create_type=False
        ), nullable=False, index=True),
        sa.Column("entity_type", sa.String(100), nullable=False, index=True),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), index=True),
        sa.Column("actor_id", sa.String(255), index=True),
        sa.Column("details", postgresql.JSON, server_default="{}"),
        sa.Column("ip_address", sa.String(45)),
        sa.Column("user_agent", sa.Text),
    )
    op.create_index("ix_audit_logs_entity", "audit_logs", ["entity_type", "entity_id"])
    op.create_index("ix_audit_logs_actor_time", "audit_logs", ["actor_id", "timestamp"])
    op.create_index("ix_audit_logs_action_time", "audit_logs", ["action", "timestamp"])


def downgrade() -> None:
    # Drop tables in reverse order of creation
    op.drop_table("audit_logs")
    op.drop_table("evidence_pack_items")
    op.drop_table("evidence_packs")
    op.drop_index("ix_embedding_chunks_embedding", table_name="embedding_chunks")
    op.drop_table("embedding_chunks")
    op.drop_table("metrics")
    op.drop_table("claims")
    op.drop_table("spans")
    op.drop_table("project_documents")
    op.drop_table("projects")
    op.drop_table("document_versions")
    op.drop_table("documents")

    # Drop enums
    op.execute("DROP TYPE IF EXISTS auditaction")
    op.execute("DROP TYPE IF EXISTS spantype")
    op.execute("DROP TYPE IF EXISTS extractionstatus")
