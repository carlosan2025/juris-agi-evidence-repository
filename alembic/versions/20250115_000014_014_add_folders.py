"""Add folders table for document organization within projects.

Revision ID: 014
Revises: 013
Create Date: 2025-01-15

This migration adds:
1. New folders table for hierarchical folder organization
2. folder_id column to project_documents for folder assignment
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create folders table
    op.create_table(
        "folders",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "parent_folder_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("folders.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("display_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("color", sa.String(7), nullable=True),
        sa.Column("icon", sa.String(50), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSON,
            nullable=False,
            server_default="{}",
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # Unique constraint for folder names within same parent
        sa.UniqueConstraint(
            "project_id",
            "parent_folder_id",
            "name",
            name="uq_folder_name_in_parent",
        ),
    )

    # Create indexes for folders table
    op.create_index("ix_folders_project_id", "folders", ["project_id"])
    op.create_index("ix_folders_parent_folder_id", "folders", ["parent_folder_id"])
    op.create_index("ix_folders_project_parent", "folders", ["project_id", "parent_folder_id"])
    op.create_index("ix_folders_deleted_at", "folders", ["deleted_at"])

    # Add folder_id to project_documents
    op.add_column(
        "project_documents",
        sa.Column(
            "folder_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("folders.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_project_documents_folder_id", "project_documents", ["folder_id"])


def downgrade() -> None:
    # Remove folder_id from project_documents
    op.drop_index("ix_project_documents_folder_id", table_name="project_documents")
    op.drop_column("project_documents", "folder_id")

    # Drop folders table and indexes
    op.drop_index("ix_folders_deleted_at", table_name="folders")
    op.drop_index("ix_folders_project_parent", table_name="folders")
    op.drop_index("ix_folders_parent_folder_id", table_name="folders")
    op.drop_index("ix_folders_project_id", table_name="folders")
    op.drop_table("folders")
