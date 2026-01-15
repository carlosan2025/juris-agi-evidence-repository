"""Add extraction_runs table.

Revision ID: 011
Revises: 010
Create Date: 2025-01-15

This migration adds the extraction_runs table that tracks document extraction runs.
The table is referenced by DocumentVersion.extraction_runs relationship.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade():
    # Create extraction run status enum
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE extractionrunstatus AS ENUM (
                'pending', 'running', 'completed', 'failed', 'skipped'
            );
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)

    # Create extraction_runs table (enum already exists from a previous migration)
    extractionrunstatus = postgresql.ENUM(
        'pending', 'running', 'completed', 'failed', 'skipped',
        name='extractionrunstatus',
        create_type=False  # Don't create - already exists
    )

    op.create_table(
        "extraction_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("document_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("status", extractionrunstatus, nullable=False, server_default="pending"),
        sa.Column("extractor_name", sa.String(100), nullable=False),
        sa.Column("extractor_version", sa.String(50), default="1.0.0"),
        sa.Column("artifact_path", sa.Text, nullable=True),
        sa.Column("has_text", sa.Boolean, default=False),
        sa.Column("has_tables", sa.Boolean, default=False),
        sa.Column("has_images", sa.Boolean, default=False),
        sa.Column("char_count", sa.Integer, nullable=True),
        sa.Column("word_count", sa.Integer, nullable=True),
        sa.Column("page_count", sa.Integer, nullable=True),
        sa.Column("table_count", sa.Integer, nullable=True),
        sa.Column("image_count", sa.Integer, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_time_ms", sa.Integer, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("warnings", postgresql.JSON, default=list),
        sa.Column("metadata", postgresql.JSON, default=dict),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Create indexes
    op.create_index("ix_extraction_runs_version_status", "extraction_runs", ["document_version_id", "status"])
    op.create_index("ix_extraction_runs_extractor", "extraction_runs", ["extractor_name"])
    op.create_index("ix_extraction_runs_created_at", "extraction_runs", ["created_at"])


def downgrade():
    op.drop_table("extraction_runs")
    # Don't drop the enum - it may be used by other tables
