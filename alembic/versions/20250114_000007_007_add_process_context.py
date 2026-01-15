"""Add process_context, schema_version, vocab_version to extraction tables.

Revision ID: 007
Revises: 006
Create Date: 2025-01-14 00:00:07

This migration adds:
- process_context enum and column to extraction_runs_multilevel, facts_*, and quality_* tables
- schema_version and vocab_version columns to extraction_runs_multilevel
- Updated indexes to include process_context for proper partitioning
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Process context enum values
PROCESS_CONTEXT_VALUES = [
    "unspecified",
    "vc.ic_decision",
    "vc.due_diligence",
    "vc.portfolio_review",
    "vc.market_analysis",
    "pharma.clinical_trial",
    "pharma.regulatory",
    "pharma.safety",
    "pharma.market_access",
    "insurance.underwriting",
    "insurance.claims",
    "insurance.compliance",
    "general.research",
    "general.compliance",
    "general.audit",
]


def upgrade() -> None:
    # Create the process_context enum type
    process_context_enum = postgresql.ENUM(
        *PROCESS_CONTEXT_VALUES,
        name="processcontext",
        create_type=False,
    )
    process_context_enum.create(op.get_bind(), checkfirst=True)

    # Add columns to extraction_runs_multilevel
    op.add_column(
        "extraction_runs_multilevel",
        sa.Column(
            "process_context",
            sa.Enum(*PROCESS_CONTEXT_VALUES, name="processcontext"),
            nullable=False,
            server_default="unspecified",
            comment="Business process context for this extraction",
        ),
    )
    op.add_column(
        "extraction_runs_multilevel",
        sa.Column(
            "schema_version",
            sa.String(50),
            nullable=False,
            server_default="1.0",
            comment="Schema version used for this extraction",
        ),
    )
    op.add_column(
        "extraction_runs_multilevel",
        sa.Column(
            "vocab_version",
            sa.String(50),
            nullable=False,
            server_default="1.0",
            comment="Vocabulary version used for this extraction",
        ),
    )

    # Add process_context to facts_claims
    op.add_column(
        "facts_claims",
        sa.Column(
            "process_context",
            sa.Enum(*PROCESS_CONTEXT_VALUES, name="processcontext"),
            nullable=False,
            server_default="unspecified",
            comment="Business process context",
        ),
    )

    # Add process_context to facts_metrics
    op.add_column(
        "facts_metrics",
        sa.Column(
            "process_context",
            sa.Enum(*PROCESS_CONTEXT_VALUES, name="processcontext"),
            nullable=False,
            server_default="unspecified",
            comment="Business process context",
        ),
    )

    # Add process_context to facts_constraints
    op.add_column(
        "facts_constraints",
        sa.Column(
            "process_context",
            sa.Enum(*PROCESS_CONTEXT_VALUES, name="processcontext"),
            nullable=False,
            server_default="unspecified",
            comment="Business process context",
        ),
    )

    # Add process_context to facts_risks
    op.add_column(
        "facts_risks",
        sa.Column(
            "process_context",
            sa.Enum(*PROCESS_CONTEXT_VALUES, name="processcontext"),
            nullable=False,
            server_default="unspecified",
            comment="Business process context",
        ),
    )

    # Add process_context to quality_conflicts
    op.add_column(
        "quality_conflicts",
        sa.Column(
            "process_context",
            sa.Enum(*PROCESS_CONTEXT_VALUES, name="processcontext"),
            nullable=False,
            server_default="unspecified",
            comment="Business process context",
        ),
    )

    # Add process_context to quality_open_questions
    op.add_column(
        "quality_open_questions",
        sa.Column(
            "process_context",
            sa.Enum(*PROCESS_CONTEXT_VALUES, name="processcontext"),
            nullable=False,
            server_default="unspecified",
            comment="Business process context",
        ),
    )

    # Create indexes on extraction_runs_multilevel
    op.create_index(
        "ix_extraction_runs_multilevel_process_context",
        "extraction_runs_multilevel",
        ["process_context"],
    )

    # Drop old index and create new one with process_context
    op.drop_index("ix_extraction_runs_multilevel_version_profile_level", table_name="extraction_runs_multilevel")
    op.create_index(
        "ix_extraction_runs_multilevel_version_profile_context_level",
        "extraction_runs_multilevel",
        ["version_id", "profile_id", "process_context", "level_id"],
    )

    # Create the unique partial index for active runs with process_context
    # Note: No need to drop old one as it was never created in migration 003
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS ix_extraction_runs_multilevel_active
        ON extraction_runs_multilevel (version_id, profile_id, process_context, level_id)
        WHERE status IN ('queued', 'running')
    """)

    # Create indexes on facts_claims
    op.create_index(
        "ix_facts_claims_process_context",
        "facts_claims",
        ["process_context"],
    )
    op.drop_index("ix_facts_claims_version_profile_level", table_name="facts_claims")
    op.create_index(
        "ix_facts_claims_version_profile_context_level",
        "facts_claims",
        ["version_id", "profile_id", "process_context", "level_id"],
    )

    # Create indexes on facts_metrics
    op.create_index(
        "ix_facts_metrics_process_context",
        "facts_metrics",
        ["process_context"],
    )
    op.drop_index("ix_facts_metrics_version_profile_level", table_name="facts_metrics")
    op.create_index(
        "ix_facts_metrics_version_profile_context_level",
        "facts_metrics",
        ["version_id", "profile_id", "process_context", "level_id"],
    )

    # Create indexes on facts_constraints
    op.create_index(
        "ix_facts_constraints_process_context",
        "facts_constraints",
        ["process_context"],
    )
    op.drop_index("ix_facts_constraints_version_profile_level", table_name="facts_constraints")
    op.create_index(
        "ix_facts_constraints_version_profile_context_level",
        "facts_constraints",
        ["version_id", "profile_id", "process_context", "level_id"],
    )

    # Create indexes on facts_risks
    op.create_index(
        "ix_facts_risks_process_context",
        "facts_risks",
        ["process_context"],
    )
    op.drop_index("ix_facts_risks_version_profile_level", table_name="facts_risks")
    op.create_index(
        "ix_facts_risks_version_profile_context_level",
        "facts_risks",
        ["version_id", "profile_id", "process_context", "level_id"],
    )

    # Create indexes on quality_conflicts
    op.create_index(
        "ix_quality_conflicts_process_context",
        "quality_conflicts",
        ["process_context"],
    )
    op.drop_index("ix_quality_conflicts_version_profile_level", table_name="quality_conflicts")
    op.create_index(
        "ix_quality_conflicts_version_profile_context_level",
        "quality_conflicts",
        ["version_id", "profile_id", "process_context", "level_id"],
    )

    # Create indexes on quality_open_questions
    op.create_index(
        "ix_quality_open_questions_process_context",
        "quality_open_questions",
        ["process_context"],
    )
    op.drop_index("ix_quality_open_questions_version_profile_level", table_name="quality_open_questions")
    op.create_index(
        "ix_quality_open_questions_version_profile_context_level",
        "quality_open_questions",
        ["version_id", "profile_id", "process_context", "level_id"],
    )


def downgrade() -> None:
    # Drop new indexes and recreate old ones

    # quality_open_questions
    op.drop_index("ix_quality_open_questions_process_context", table_name="quality_open_questions")
    op.drop_index("ix_quality_open_questions_version_profile_context_level", table_name="quality_open_questions")
    op.create_index(
        "ix_quality_open_questions_version_profile_level",
        "quality_open_questions",
        ["version_id", "profile_id", "level_id"],
    )

    # quality_conflicts
    op.drop_index("ix_quality_conflicts_process_context", table_name="quality_conflicts")
    op.drop_index("ix_quality_conflicts_version_profile_context_level", table_name="quality_conflicts")
    op.create_index(
        "ix_quality_conflicts_version_profile_level",
        "quality_conflicts",
        ["version_id", "profile_id", "level_id"],
    )

    # facts_risks
    op.drop_index("ix_facts_risks_process_context", table_name="facts_risks")
    op.drop_index("ix_facts_risks_version_profile_context_level", table_name="facts_risks")
    op.create_index(
        "ix_facts_risks_version_profile_level",
        "facts_risks",
        ["version_id", "profile_id", "level_id"],
    )

    # facts_constraints
    op.drop_index("ix_facts_constraints_process_context", table_name="facts_constraints")
    op.drop_index("ix_facts_constraints_version_profile_context_level", table_name="facts_constraints")
    op.create_index(
        "ix_facts_constraints_version_profile_level",
        "facts_constraints",
        ["version_id", "profile_id", "level_id"],
    )

    # facts_metrics
    op.drop_index("ix_facts_metrics_process_context", table_name="facts_metrics")
    op.drop_index("ix_facts_metrics_version_profile_context_level", table_name="facts_metrics")
    op.create_index(
        "ix_facts_metrics_version_profile_level",
        "facts_metrics",
        ["version_id", "profile_id", "level_id"],
    )

    # facts_claims
    op.drop_index("ix_facts_claims_process_context", table_name="facts_claims")
    op.drop_index("ix_facts_claims_version_profile_context_level", table_name="facts_claims")
    op.create_index(
        "ix_facts_claims_version_profile_level",
        "facts_claims",
        ["version_id", "profile_id", "level_id"],
    )

    # extraction_runs_multilevel
    op.execute("DROP INDEX IF EXISTS ix_extraction_runs_multilevel_active")
    op.execute("DROP INDEX IF EXISTS ix_extraction_runs_multilevel_process_context")
    op.execute("DROP INDEX IF EXISTS ix_extraction_runs_multilevel_version_profile_context_level")
    # Recreate original index (if it was dropped)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_extraction_runs_multilevel_version_profile_level
        ON extraction_runs_multilevel (version_id, profile_id, level_id)
    """)

    # Drop columns
    op.drop_column("quality_open_questions", "process_context")
    op.drop_column("quality_conflicts", "process_context")
    op.drop_column("facts_risks", "process_context")
    op.drop_column("facts_constraints", "process_context")
    op.drop_column("facts_metrics", "process_context")
    op.drop_column("facts_claims", "process_context")
    op.drop_column("extraction_runs_multilevel", "vocab_version")
    op.drop_column("extraction_runs_multilevel", "schema_version")
    op.drop_column("extraction_runs_multilevel", "process_context")

    # Drop the enum type
    op.execute("DROP TYPE IF EXISTS processcontext")
