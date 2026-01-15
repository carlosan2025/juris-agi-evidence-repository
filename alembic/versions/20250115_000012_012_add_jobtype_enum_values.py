"""Add missing jobtype enum values.

Revision ID: 012
Revises: 011
Create Date: 2025-01-15

Adds the following jobtype enum values:
- process_document_version (for idempotent document version processing pipeline)
- fact_extract (for fact extraction jobs)
- multilevel_extract (for multi-level extraction)
- multilevel_extract_batch (for batch multi-level extraction)
- upgrade_extraction_level (for upgrading extraction levels)
- quality_check (for quality analysis jobs)
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add missing jobtype enum values."""
    # Add new enum values to the existing jobtype enum
    # Using raw SQL since Alembic doesn't have direct enum value manipulation
    op.execute("ALTER TYPE jobtype ADD VALUE IF NOT EXISTS 'process_document_version'")
    op.execute("ALTER TYPE jobtype ADD VALUE IF NOT EXISTS 'fact_extract'")
    op.execute("ALTER TYPE jobtype ADD VALUE IF NOT EXISTS 'multilevel_extract'")
    op.execute("ALTER TYPE jobtype ADD VALUE IF NOT EXISTS 'multilevel_extract_batch'")
    op.execute("ALTER TYPE jobtype ADD VALUE IF NOT EXISTS 'upgrade_extraction_level'")
    op.execute("ALTER TYPE jobtype ADD VALUE IF NOT EXISTS 'quality_check'")


def downgrade() -> None:
    """Cannot remove enum values in PostgreSQL without recreating the type.

    PostgreSQL doesn't support removing values from an enum type directly.
    If a downgrade is needed, the enum would need to be recreated, which
    requires dropping and recreating all columns that use it.
    """
    pass
