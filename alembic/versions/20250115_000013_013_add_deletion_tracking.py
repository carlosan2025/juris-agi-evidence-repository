"""Add deletion tracking for safe cascading document deletion.

Revision ID: 013
Revises: 012
Create Date: 2025-01-15

This migration adds:
1. deletion_status enum and tracking fields to documents table
2. New deletion_tasks table to track each resource deletion step
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create deletion_status enum
    deletion_status_enum = postgresql.ENUM(
        "active",
        "marked",
        "deleting",
        "failed",
        "deleted",
        name="deletionstatus",
        create_type=False,
    )
    deletion_status_enum.create(op.get_bind(), checkfirst=True)

    # Create deletion_task_status enum
    deletion_task_status_enum = postgresql.ENUM(
        "pending",
        "in_progress",
        "completed",
        "failed",
        "skipped",
        name="deletiontaskstatus",
        create_type=False,
    )
    deletion_task_status_enum.create(op.get_bind(), checkfirst=True)

    # Create deletion_task_type enum
    deletion_task_type_enum = postgresql.ENUM(
        "storage_file",
        "embedding_chunks",
        "spans",
        "facts_claims",
        "facts_metrics",
        "facts_constraints",
        "facts_risks",
        "quality_conflicts",
        "quality_questions",
        "extraction_runs",
        "project_documents",
        "document_versions",
        "document_record",
        name="deletiontasktype",
        create_type=False,
    )
    deletion_task_type_enum.create(op.get_bind(), checkfirst=True)

    # Add deletion tracking columns to documents table
    op.add_column(
        "documents",
        sa.Column(
            "deletion_status",
            deletion_status_enum,
            nullable=False,
            server_default="active",
        ),
    )
    op.add_column(
        "documents",
        sa.Column("deletion_requested_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("deletion_requested_by", sa.String(100), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("deletion_completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("deletion_error", sa.Text(), nullable=True),
    )

    # Add index on deletion_status
    op.create_index(
        "ix_documents_deletion_status",
        "documents",
        ["deletion_status"],
    )

    # Create deletion_tasks table
    op.create_table(
        "deletion_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("version_id", postgresql.UUID(as_uuid=True), nullable=True, index=True),
        sa.Column("task_type", deletion_task_type_enum, nullable=False),
        sa.Column("resource_id", sa.String(1024), nullable=False),
        sa.Column("resource_count", sa.Integer(), default=1),
        sa.Column("processing_order", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            deletion_task_status_enum,
            nullable=False,
            server_default="pending",
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), default=0),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Create composite indexes for deletion_tasks
    op.create_index(
        "ix_deletion_tasks_document_status",
        "deletion_tasks",
        ["document_id", "status"],
    )
    op.create_index(
        "ix_deletion_tasks_document_order",
        "deletion_tasks",
        ["document_id", "processing_order"],
    )


def downgrade() -> None:
    # Drop deletion_tasks table
    op.drop_index("ix_deletion_tasks_document_order", table_name="deletion_tasks")
    op.drop_index("ix_deletion_tasks_document_status", table_name="deletion_tasks")
    op.drop_table("deletion_tasks")

    # Remove columns from documents table
    op.drop_index("ix_documents_deletion_status", table_name="documents")
    op.drop_column("documents", "deletion_error")
    op.drop_column("documents", "deletion_completed_at")
    op.drop_column("documents", "deletion_requested_by")
    op.drop_column("documents", "deletion_requested_at")
    op.drop_column("documents", "deletion_status")

    # Drop enums
    op.execute("DROP TYPE IF EXISTS deletiontasktype")
    op.execute("DROP TYPE IF EXISTS deletiontaskstatus")
    op.execute("DROP TYPE IF EXISTS deletionstatus")
