"""Add profile_code column to documents table.

Revision ID: 006
Revises: 005
Create Date: 2025-01-14 00:00:06

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add profile_code column to documents table for industry-specific extraction
    op.add_column(
        "documents",
        sa.Column("profile_code", sa.String(50), nullable=False, server_default="general")
    )

    # Create index for filtering by profile
    op.create_index("ix_documents_profile_code", "documents", ["profile_code"])


def downgrade() -> None:
    op.drop_index("ix_documents_profile_code", table_name="documents")
    op.drop_column("documents", "profile_code")
