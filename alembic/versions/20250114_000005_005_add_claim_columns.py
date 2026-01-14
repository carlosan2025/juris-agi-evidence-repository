"""Add missing columns to claims and metrics tables.

Revision ID: 005
Revises: 004
Create Date: 2025-01-14 00:00:05

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add missing columns to claims table
    op.add_column("claims", sa.Column("time_scope", sa.String(100), nullable=True))
    op.add_column("claims", sa.Column("certainty", sa.String(50), nullable=False, server_default="probable"))
    op.add_column("claims", sa.Column("reliability", sa.String(50), nullable=False, server_default="unknown"))
    op.add_column("claims", sa.Column("extraction_confidence", sa.Float, nullable=True))

    # Update claim_type to use proper enum values if needed
    op.alter_column("claims", "claim_type", nullable=True)

    # Create index on claim_type if not exists
    op.create_index("ix_claims_claim_type", "claims", ["claim_type"], if_not_exists=True)

    # Add missing columns to metrics table
    op.add_column("metrics", sa.Column("metric_type", sa.String(50), nullable=False, server_default="other"))
    op.add_column("metrics", sa.Column("numeric_value", sa.Float, nullable=True))
    op.add_column("metrics", sa.Column("time_scope", sa.String(100), nullable=True))
    op.add_column("metrics", sa.Column("certainty", sa.String(50), nullable=False, server_default="probable"))
    op.add_column("metrics", sa.Column("reliability", sa.String(50), nullable=False, server_default="unknown"))
    op.add_column("metrics", sa.Column("extraction_confidence", sa.Float, nullable=True))

    # Create index on metric_type
    op.create_index("ix_metrics_metric_type", "metrics", ["metric_type"], if_not_exists=True)


def downgrade() -> None:
    op.drop_index("ix_metrics_metric_type", table_name="metrics")
    op.drop_column("metrics", "extraction_confidence")
    op.drop_column("metrics", "reliability")
    op.drop_column("metrics", "certainty")
    op.drop_column("metrics", "time_scope")
    op.drop_column("metrics", "numeric_value")
    op.drop_column("metrics", "metric_type")

    op.drop_index("ix_claims_claim_type", table_name="claims")
    op.drop_column("claims", "extraction_confidence")
    op.drop_column("claims", "reliability")
    op.drop_column("claims", "certainty")
    op.drop_column("claims", "time_scope")
