"""Add multi-level extraction tables.

Revision ID: 003
Revises: 002
Create Date: 2025-01-13 00:00:03

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create extraction_profiles table
    op.create_table(
        "extraction_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(50), unique=True, nullable=False, index=True),
        sa.Column("code", sa.String(50), unique=True, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, default=True),
        sa.Column("config", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Create extraction_levels table
    op.create_table(
        "extraction_levels",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("code", sa.String(50), unique=True, nullable=False),
        sa.Column("rank", sa.Integer, unique=True, nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, default=True),
        sa.Column("config", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("rank >= 1 AND rank <= 10", name="ck_extraction_levels_rank"),
    )

    # Create extraction_settings table
    op.create_table(
        "extraction_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("scope_type", sa.String(50), nullable=False, index=True),
        sa.Column("scope_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("extraction_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("level_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("extraction_levels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("compute_mode", sa.String(50), nullable=False, default="exact_only"),
        sa.Column("is_enabled", sa.Boolean, nullable=False, default=True),
        sa.Column("updated_by", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.UniqueConstraint("scope_type", "scope_id", name="uq_extraction_settings_scope"),
    )
    op.create_index("ix_extraction_settings_scope", "extraction_settings", ["scope_type", "scope_id"])

    # Create extraction_runs table (new multi-level version)
    op.create_table(
        "extraction_runs_multilevel",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("extraction_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("level_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("extraction_levels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, default="queued", index=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("metadata", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("parent_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("extraction_runs_multilevel.id", ondelete="SET NULL"), nullable=True),
        sa.Column("job_id", sa.String(255), nullable=True),
        sa.Column("triggered_by", sa.String(255), nullable=True),
    )
    op.create_index("ix_extraction_runs_multilevel_version_profile_level", "extraction_runs_multilevel", ["version_id", "profile_id", "level_id"])

    # Create facts_claims table
    op.create_table(
        "facts_claims",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("extraction_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("level_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("extraction_levels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("extraction_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("extraction_runs_multilevel.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("subject", postgresql.JSONB, nullable=False),
        sa.Column("predicate", sa.String(255), nullable=False, index=True),
        sa.Column("object", postgresql.JSONB, nullable=False),
        sa.Column("claim_type", sa.String(100), nullable=False, index=True),
        sa.Column("time_scope", postgresql.JSONB, nullable=True),
        sa.Column("certainty", sa.String(50), nullable=False, default="probable"),
        sa.Column("source_reliability", sa.String(50), nullable=False, default="unknown"),
        sa.Column("extraction_confidence", sa.Float, nullable=True),
        sa.Column("span_refs", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("evidence_quote", sa.Text, nullable=True),
        sa.Column("metadata", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_facts_claims_version_profile_level", "facts_claims", ["version_id", "profile_id", "level_id"])

    # Create facts_metrics table
    op.create_table(
        "facts_metrics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("extraction_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("level_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("extraction_levels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("extraction_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("extraction_runs_multilevel.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("entity_id", sa.String(255), nullable=True, index=True),
        sa.Column("entity_type", sa.String(100), nullable=True),
        sa.Column("metric_name", sa.String(255), nullable=False, index=True),
        sa.Column("metric_category", sa.String(100), nullable=True, index=True),
        sa.Column("value_numeric", sa.Float, nullable=True),
        sa.Column("value_raw", sa.String(255), nullable=True),
        sa.Column("unit", sa.String(50), nullable=True),
        sa.Column("currency", sa.String(10), nullable=True),
        sa.Column("period_start", sa.Date, nullable=True),
        sa.Column("period_end", sa.Date, nullable=True),
        sa.Column("as_of", sa.Date, nullable=True),
        sa.Column("period_type", sa.String(50), nullable=True),
        sa.Column("method", sa.String(100), nullable=True),
        sa.Column("certainty", sa.String(50), nullable=False, default="probable"),
        sa.Column("source_reliability", sa.String(50), nullable=False, default="unknown"),
        sa.Column("extraction_confidence", sa.Float, nullable=True),
        sa.Column("quality_flags", postgresql.JSONB, nullable=True),
        sa.Column("span_refs", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("evidence_quote", sa.Text, nullable=True),
        sa.Column("metadata", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_facts_metrics_version_profile_level", "facts_metrics", ["version_id", "profile_id", "level_id"])
    op.create_index("ix_facts_metrics_entity", "facts_metrics", ["entity_id", "metric_name"])

    # Create facts_constraints table
    op.create_table(
        "facts_constraints",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("extraction_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("level_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("extraction_levels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("extraction_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("extraction_runs_multilevel.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("constraint_type", sa.String(50), nullable=False, index=True),
        sa.Column("applies_to", postgresql.JSONB, nullable=False),
        sa.Column("statement", sa.Text, nullable=False),
        sa.Column("certainty", sa.String(50), nullable=False, default="probable"),
        sa.Column("extraction_confidence", sa.Float, nullable=True),
        sa.Column("span_refs", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("metadata", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_facts_constraints_version_profile_level", "facts_constraints", ["version_id", "profile_id", "level_id"])

    # Create facts_risks table
    op.create_table(
        "facts_risks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("extraction_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("level_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("extraction_levels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("extraction_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("extraction_runs_multilevel.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("risk_type", sa.String(100), nullable=False, index=True),
        sa.Column("risk_category", sa.String(100), nullable=True),
        sa.Column("severity", sa.String(50), nullable=False, default="medium", index=True),
        sa.Column("statement", sa.Text, nullable=False),
        sa.Column("rationale", sa.Text, nullable=True),
        sa.Column("related_claims", postgresql.JSONB, nullable=True),
        sa.Column("related_metrics", postgresql.JSONB, nullable=True),
        sa.Column("extraction_confidence", sa.Float, nullable=True),
        sa.Column("span_refs", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("metadata", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_facts_risks_version_profile_level", "facts_risks", ["version_id", "profile_id", "level_id"])
    op.create_index("ix_facts_risks_type_severity", "facts_risks", ["risk_type", "severity"])

    # Create quality_conflicts table
    op.create_table(
        "quality_conflicts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("extraction_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("level_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("extraction_levels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("extraction_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("extraction_runs_multilevel.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("topic", sa.Text, nullable=False),
        sa.Column("severity", sa.String(50), nullable=False, default="medium", index=True),
        sa.Column("claim_ids", postgresql.JSONB, nullable=True),
        sa.Column("metric_ids", postgresql.JSONB, nullable=True),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("resolution", sa.Text, nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.String(255), nullable=True),
        sa.Column("metadata", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_quality_conflicts_version_profile_level", "quality_conflicts", ["version_id", "profile_id", "level_id"])

    # Create quality_open_questions table
    op.create_table(
        "quality_open_questions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("extraction_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("level_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("extraction_levels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("extraction_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("extraction_runs_multilevel.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("question", sa.Text, nullable=False),
        sa.Column("category", sa.String(50), nullable=False, default="missing_data", index=True),
        sa.Column("context", sa.Text, nullable=True),
        sa.Column("related_claim_ids", postgresql.JSONB, nullable=True),
        sa.Column("related_metric_ids", postgresql.JSONB, nullable=True),
        sa.Column("answer", sa.Text, nullable=True),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("answered_by", sa.String(255), nullable=True),
        sa.Column("metadata", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_quality_open_questions_version_profile_level", "quality_open_questions", ["version_id", "profile_id", "level_id"])

    # Insert default profiles
    op.execute("""
        INSERT INTO extraction_profiles (name, code, description, is_active)
        VALUES
            ('General', 'general', 'General-purpose extraction profile', true),
            ('Venture Capital', 'vc', 'VC/Startup due diligence extraction', true),
            ('Pharmaceutical', 'pharma', 'Pharmaceutical/Life Sciences extraction', true),
            ('Insurance', 'insurance', 'Insurance underwriting extraction', true)
        ON CONFLICT (code) DO NOTHING
    """)

    # Insert default levels
    op.execute("""
        INSERT INTO extraction_levels (code, rank, name, description, is_active)
        VALUES
            ('L1_BASIC', 1, 'Basic', 'Minimal key metrics and essential claims', true),
            ('L2_STANDARD', 2, 'Standard', 'Comprehensive metrics, compliance claims, constraints', true),
            ('L3_DEEP', 3, 'Deep', 'Entity resolution, time-series, table-aware, risks', true),
            ('L4_FORENSIC', 4, 'Forensic', 'Maximum extraction, cross-doc reconciliation', true)
        ON CONFLICT (code) DO NOTHING
    """)


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_table("quality_open_questions")
    op.drop_table("quality_conflicts")
    op.drop_table("facts_risks")
    op.drop_table("facts_constraints")
    op.drop_table("facts_metrics")
    op.drop_table("facts_claims")
    op.drop_table("extraction_runs_multilevel")
    op.drop_table("extraction_settings")
    op.drop_table("extraction_levels")
    op.drop_table("extraction_profiles")
