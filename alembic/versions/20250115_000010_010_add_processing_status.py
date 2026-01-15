"""Add processing_status column to document_versions table.

Revision ID: 010
Revises: 009
Create Date: 2025-01-15 00:00:10

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create the enum type first
    processing_status_enum = sa.Enum(
        'pending', 'uploaded', 'extracted', 'spans_built',
        'embedded', 'facts_extracted', 'quality_checked', 'failed',
        name='processingstatus'
    )
    processing_status_enum.create(op.get_bind(), checkfirst=True)

    # Add processing_status column to document_versions table
    # Default to 'pending' for new records
    # For existing records, set based on their current extraction_status:
    # - If extraction completed, they're at least 'extracted'
    # - Otherwise 'pending'
    op.add_column(
        "document_versions",
        sa.Column(
            "processing_status",
            processing_status_enum,
            nullable=False,
            server_default="pending"
        )
    )

    # Update existing records: if extraction is completed, set to 'extracted'
    # This is a best-effort since we don't know if spans/embeddings exist
    op.execute("""
        UPDATE document_versions
        SET processing_status = 'extracted'
        WHERE extraction_status = 'completed'
    """)

    # Create index for filtering by processing status
    op.create_index(
        "ix_document_versions_processing_status",
        "document_versions",
        ["processing_status"]
    )


def downgrade() -> None:
    op.drop_index("ix_document_versions_processing_status", table_name="document_versions")
    op.drop_column("document_versions", "processing_status")

    # Drop the enum type
    processing_status_enum = sa.Enum(name='processingstatus')
    processing_status_enum.drop(op.get_bind(), checkfirst=True)
