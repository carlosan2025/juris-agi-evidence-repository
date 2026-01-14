"""Add jobs, ingestion batches, and analysis tables.

Revision ID: 002
Revises: 001
Create Date: 2025-01-13
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ==========================================================================
    # Create enums for new tables using raw SQL
    # ==========================================================================
    op.execute("CREATE TYPE jobstatus AS ENUM ('queued', 'running', 'succeeded', 'failed', 'canceled', 'retrying')")
    op.execute("""CREATE TYPE jobtype AS ENUM (
        'document_ingest', 'document_extract', 'document_embed', 'document_process_full',
        'bulk_folder_ingest', 'bulk_url_ingest', 'batch_extract', 'batch_embed',
        'span_extract', 'claim_extract', 'metric_extract', 'cleanup', 'reindex'
    )""")
    op.execute("CREATE TYPE ingestionbatchstatus AS ENUM ('pending', 'processing', 'completed', 'partial', 'failed', 'canceled')")
    op.execute("CREATE TYPE ingestionitemstatus AS ENUM ('pending', 'downloading', 'processing', 'extracting', 'embedding', 'completed', 'failed', 'skipped')")
    op.execute("CREATE TYPE ingestionsource AS ENUM ('file_upload', 'local_folder', 'url', 's3_bucket', 'api_import')")
    op.execute("CREATE TYPE conflicttype AS ENUM ('contradiction', 'inconsistency', 'metric_mismatch', 'temporal', 'numeric', 'factual', 'other')")
    op.execute("CREATE TYPE conflictstatus AS ENUM ('open', 'under_review', 'resolved', 'dismissed', 'escalated')")
    op.execute("CREATE TYPE conflictseverity AS ENUM ('low', 'medium', 'high', 'critical')")
    op.execute("CREATE TYPE questionpriority AS ENUM ('low', 'medium', 'high', 'urgent')")
    op.execute("CREATE TYPE questionstatus AS ENUM ('open', 'in_progress', 'answered', 'deferred', 'closed')")
    op.execute("CREATE TYPE questioncategory AS ENUM ('missing_evidence', 'clarification', 'verification', 'ambiguity', 'follow_up', 'methodology', 'other')")

    # ==========================================================================
    # Create jobs table
    # ==========================================================================
    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("type", postgresql.ENUM(
            "document_ingest", "document_extract", "document_embed", "document_process_full",
            "bulk_folder_ingest", "bulk_url_ingest", "batch_extract", "batch_embed",
            "span_extract", "claim_extract", "metric_extract",
            "cleanup", "reindex",
            name="jobtype", create_type=False
        ), nullable=False),
        sa.Column("status", postgresql.ENUM(
            "queued", "running", "succeeded", "failed", "canceled", "retrying",
            name="jobstatus", create_type=False
        ), nullable=False, server_default="queued"),
        sa.Column("priority", sa.Integer, nullable=False, server_default="0"),
        sa.Column("payload", postgresql.JSON, nullable=False, server_default="{}"),
        sa.Column("result", postgresql.JSON),
        sa.Column("error", sa.Text),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer, nullable=False, server_default="3"),
        sa.Column("progress", sa.Integer, nullable=False, server_default="0"),
        sa.Column("progress_message", sa.String(500)),
        sa.Column("worker_id", sa.String(255)),
        sa.Column("queue_job_id", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_jobs_type", "jobs", ["type"])
    op.create_index("ix_jobs_status", "jobs", ["status"])
    op.create_index("ix_jobs_queue_job_id", "jobs", ["queue_job_id"])
    op.create_index("ix_jobs_status_created_at", "jobs", ["status", "created_at"])
    op.create_index("ix_jobs_type_status", "jobs", ["type", "status"])
    op.create_index("ix_jobs_priority_created_at", "jobs", ["priority", "created_at"])

    # ==========================================================================
    # Create ingestion_batches table
    # ==========================================================================
    op.create_table(
        "ingestion_batches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("name", sa.String(255)),
        sa.Column("description", sa.Text),
        sa.Column("source_type", postgresql.ENUM(
            "file_upload", "local_folder", "url", "s3_bucket", "api_import",
            name="ingestionsource", create_type=False
        ), nullable=False),
        sa.Column("source_path", sa.Text),
        sa.Column("status", postgresql.ENUM(
            "pending", "processing", "completed", "partial", "failed", "canceled",
            name="ingestionbatchstatus", create_type=False
        ), nullable=False, server_default="pending"),
        sa.Column("total_items", sa.Integer, nullable=False, server_default="0"),
        sa.Column("processed_items", sa.Integer, nullable=False, server_default="0"),
        sa.Column("successful_items", sa.Integer, nullable=False, server_default="0"),
        sa.Column("failed_items", sa.Integer, nullable=False, server_default="0"),
        sa.Column("skipped_items", sa.Integer, nullable=False, server_default="0"),
        sa.Column("job_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("jobs.id", ondelete="SET NULL")),
        sa.Column("created_by", sa.String(255)),
        sa.Column("metadata", postgresql.JSON, server_default="{}"),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_ingestion_batches_status", "ingestion_batches", ["status"])
    op.create_index("ix_ingestion_batches_job_id", "ingestion_batches", ["job_id"])
    op.create_index("ix_ingestion_batches_status_created_at", "ingestion_batches",
                    ["status", "created_at"])
    op.create_index("ix_ingestion_batches_source_type", "ingestion_batches", ["source_type"])

    # ==========================================================================
    # Create ingestion_items table
    # ==========================================================================
    op.create_table(
        "ingestion_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("ingestion_batches.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("source_path", sa.Text, nullable=False),
        sa.Column("source_filename", sa.String(500), nullable=False),
        sa.Column("source_size", sa.Integer),
        sa.Column("status", postgresql.ENUM(
            "pending", "downloading", "processing", "extracting", "embedding",
            "completed", "failed", "skipped",
            name="ingestionitemstatus", create_type=False
        ), nullable=False, server_default="pending"),
        sa.Column("document_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("documents.id", ondelete="SET NULL")),
        sa.Column("document_version_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("document_versions.id", ondelete="SET NULL")),
        sa.Column("error_message", sa.Text),
        sa.Column("error_code", sa.String(100)),
        sa.Column("content_type", sa.String(255)),
        sa.Column("file_hash", sa.String(64)),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("metadata", postgresql.JSON, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_ingestion_items_batch_id", "ingestion_items", ["batch_id"])
    op.create_index("ix_ingestion_items_status", "ingestion_items", ["status"])
    op.create_index("ix_ingestion_items_document_id", "ingestion_items", ["document_id"])
    op.create_index("ix_ingestion_items_batch_status", "ingestion_items",
                    ["batch_id", "status"])
    op.create_index("ix_ingestion_items_file_hash", "ingestion_items", ["file_hash"])

    # ==========================================================================
    # Create conflicts table
    # ==========================================================================
    op.create_table(
        "conflicts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("project_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("projects.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("conflict_type", postgresql.ENUM(
            "contradiction", "inconsistency", "metric_mismatch", "temporal",
            "numeric", "factual", "other",
            name="conflicttype", create_type=False
        ), nullable=False, server_default="other"),
        sa.Column("severity", postgresql.ENUM(
            "low", "medium", "high", "critical",
            name="conflictseverity", create_type=False
        ), nullable=False, server_default="medium"),
        sa.Column("status", postgresql.ENUM(
            "open", "under_review", "resolved", "dismissed", "escalated",
            name="conflictstatus", create_type=False
        ), nullable=False, server_default="open"),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("confidence", sa.Float),
        # Evidence references (pairs of conflicting items)
        sa.Column("claim_a_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("claims.id", ondelete="SET NULL")),
        sa.Column("claim_b_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("claims.id", ondelete="SET NULL")),
        sa.Column("metric_a_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("metrics.id", ondelete="SET NULL")),
        sa.Column("metric_b_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("metrics.id", ondelete="SET NULL")),
        sa.Column("span_a_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("spans.id", ondelete="SET NULL")),
        sa.Column("span_b_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("spans.id", ondelete="SET NULL")),
        # Resolution
        sa.Column("resolution", sa.Text),
        sa.Column("resolved_by", sa.String(255)),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        # Tracking
        sa.Column("detected_by", sa.String(255)),
        sa.Column("assigned_to", sa.String(255)),
        sa.Column("metadata", postgresql.JSON, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_conflicts_project_id", "conflicts", ["project_id"])
    op.create_index("ix_conflicts_conflict_type", "conflicts", ["conflict_type"])
    op.create_index("ix_conflicts_severity", "conflicts", ["severity"])
    op.create_index("ix_conflicts_status", "conflicts", ["status"])
    op.create_index("ix_conflicts_claim_a_id", "conflicts", ["claim_a_id"])
    op.create_index("ix_conflicts_claim_b_id", "conflicts", ["claim_b_id"])
    op.create_index("ix_conflicts_metric_a_id", "conflicts", ["metric_a_id"])
    op.create_index("ix_conflicts_metric_b_id", "conflicts", ["metric_b_id"])
    op.create_index("ix_conflicts_span_a_id", "conflicts", ["span_a_id"])
    op.create_index("ix_conflicts_span_b_id", "conflicts", ["span_b_id"])
    op.create_index("ix_conflicts_project_status", "conflicts", ["project_id", "status"])
    op.create_index("ix_conflicts_severity_status", "conflicts", ["severity", "status"])
    op.create_index("ix_conflicts_type_status", "conflicts", ["conflict_type", "status"])

    # ==========================================================================
    # Create open_questions table
    # ==========================================================================
    op.create_table(
        "open_questions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("project_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("projects.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("question", sa.Text, nullable=False),
        sa.Column("context", sa.Text),
        sa.Column("category", postgresql.ENUM(
            "missing_evidence", "clarification", "verification", "ambiguity",
            "follow_up", "methodology", "other",
            name="questioncategory", create_type=False
        ), nullable=False, server_default="other"),
        sa.Column("priority", postgresql.ENUM(
            "low", "medium", "high", "urgent",
            name="questionpriority", create_type=False
        ), nullable=False, server_default="medium"),
        sa.Column("status", postgresql.ENUM(
            "open", "in_progress", "answered", "deferred", "closed",
            name="questionstatus", create_type=False
        ), nullable=False, server_default="open"),
        # Related evidence
        sa.Column("span_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("spans.id", ondelete="SET NULL")),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("claims.id", ondelete="SET NULL")),
        sa.Column("conflict_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("conflicts.id", ondelete="SET NULL")),
        # Answer
        sa.Column("answer", sa.Text),
        sa.Column("answer_source", sa.Text),
        # Tracking
        sa.Column("raised_by", sa.String(255)),
        sa.Column("assigned_to", sa.String(255)),
        sa.Column("answered_by", sa.String(255)),
        sa.Column("answered_at", sa.DateTime(timezone=True)),
        sa.Column("due_date", sa.DateTime(timezone=True)),
        sa.Column("metadata", postgresql.JSON, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_open_questions_project_id", "open_questions", ["project_id"])
    op.create_index("ix_open_questions_category", "open_questions", ["category"])
    op.create_index("ix_open_questions_priority", "open_questions", ["priority"])
    op.create_index("ix_open_questions_status", "open_questions", ["status"])
    op.create_index("ix_open_questions_span_id", "open_questions", ["span_id"])
    op.create_index("ix_open_questions_claim_id", "open_questions", ["claim_id"])
    op.create_index("ix_open_questions_conflict_id", "open_questions", ["conflict_id"])
    op.create_index("ix_open_questions_project_status", "open_questions",
                    ["project_id", "status"])
    op.create_index("ix_open_questions_priority_status", "open_questions",
                    ["priority", "status"])
    op.create_index("ix_open_questions_due_date", "open_questions", ["due_date"])

    # ==========================================================================
    # Add span_hash column and unique constraint to spans table
    # ==========================================================================
    op.add_column("spans", sa.Column("span_hash", sa.String(64), nullable=True))

    # Compute hash for existing rows (if any)
    op.execute("""
        UPDATE spans
        SET span_hash = encode(sha256(
            (document_version_id::text || '|' ||
             start_locator::text || '|' ||
             COALESCE(end_locator::text, '') || '|' ||
             text_content)::bytea
        ), 'hex')
        WHERE span_hash IS NULL
    """)

    # Make column non-nullable after populating
    op.alter_column("spans", "span_hash", nullable=False)

    # Add index and unique constraint
    op.create_index("ix_spans_span_hash", "spans", ["span_hash"])
    op.create_unique_constraint(
        "uq_spans_version_hash",
        "spans",
        ["document_version_id", "span_hash"]
    )

    # ==========================================================================
    # Add metric_name index to metrics table
    # ==========================================================================
    op.create_index("ix_metrics_metric_name", "metrics", ["metric_name"])

    # ==========================================================================
    # Add unique constraint to document_versions for idempotency
    # ==========================================================================
    op.create_unique_constraint(
        "uq_document_versions_document_hash",
        "document_versions",
        ["document_id", "file_hash"]
    )


def downgrade() -> None:
    # Remove unique constraints and indexes
    op.drop_constraint("uq_document_versions_document_hash", "document_versions")
    op.drop_index("ix_metrics_metric_name", table_name="metrics")
    op.drop_constraint("uq_spans_version_hash", "spans")
    op.drop_index("ix_spans_span_hash", table_name="spans")
    op.drop_column("spans", "span_hash")

    # Drop tables in reverse order
    op.drop_table("open_questions")
    op.drop_table("conflicts")
    op.drop_table("ingestion_items")
    op.drop_table("ingestion_batches")
    op.drop_table("jobs")

    # Drop enums
    op.execute("DROP TYPE IF EXISTS questioncategory")
    op.execute("DROP TYPE IF EXISTS questionstatus")
    op.execute("DROP TYPE IF EXISTS questionpriority")
    op.execute("DROP TYPE IF EXISTS conflictseverity")
    op.execute("DROP TYPE IF EXISTS conflictstatus")
    op.execute("DROP TYPE IF EXISTS conflicttype")
    op.execute("DROP TYPE IF EXISTS ingestionsource")
    op.execute("DROP TYPE IF EXISTS ingestionitemstatus")
    op.execute("DROP TYPE IF EXISTS ingestionbatchstatus")
    op.execute("DROP TYPE IF EXISTS jobtype")
    op.execute("DROP TYPE IF EXISTS jobstatus")
