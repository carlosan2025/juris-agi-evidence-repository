"""Add upload_status column to document_versions table.

Revision ID: 009
Revises: 008
Create Date: 2025-01-15 00:00:09

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create the enum type first
    upload_status_enum = sa.Enum('pending', 'uploaded', 'failed', name='uploadstatus')
    upload_status_enum.create(op.get_bind(), checkfirst=True)

    # Add upload_status column to document_versions table
    # Default to 'uploaded' for existing records (they were uploaded via direct upload)
    op.add_column(
        "document_versions",
        sa.Column(
            "upload_status",
            upload_status_enum,
            nullable=False,
            server_default="uploaded"
        )
    )

    # Create index for filtering by upload status
    op.create_index("ix_document_versions_upload_status", "document_versions", ["upload_status"])


def downgrade() -> None:
    op.drop_index("ix_document_versions_upload_status", table_name="document_versions")
    op.drop_column("document_versions", "upload_status")

    # Drop the enum type
    upload_status_enum = sa.Enum(name='uploadstatus')
    upload_status_enum.drop(op.get_bind(), checkfirst=True)
