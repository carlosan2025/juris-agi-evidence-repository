"""Add integration_keys table for third-party API key management.

Revision ID: 004_add_integration_keys
Revises: 003_add_multilevel_extraction
Create Date: 2025-01-13

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create integration_keys table."""
    # Create enum type for integration provider
    op.execute(
        "CREATE TYPE integrationprovider AS ENUM "
        "('openai', 'lovepdf', 'aws', 'anthropic', 'custom')"
    )

    # Create integration_keys table
    op.create_table(
        "integration_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "provider",
            postgresql.ENUM(
                "openai",
                "lovepdf",
                "aws",
                "anthropic",
                "custom",
                name="integrationprovider",
                create_type=False,
            ),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("key_type", sa.String(100), nullable=False),
        sa.Column("encrypted_value", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, default=True),
        sa.Column(
            "last_used_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.Column("updated_by", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )

    # Create index on provider for faster lookups
    op.create_index(
        "ix_integration_keys_provider_key_type",
        "integration_keys",
        ["provider", "key_type"],
    )


def downgrade() -> None:
    """Drop integration_keys table."""
    op.drop_index("ix_integration_keys_provider_key_type")
    op.drop_table("integration_keys")
    op.execute("DROP TYPE integrationprovider")
