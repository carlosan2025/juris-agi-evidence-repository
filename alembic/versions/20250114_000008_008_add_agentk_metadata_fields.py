"""Add Agent-K style metadata fields to documents.

Revision ID: 008
Revises: 007
Create Date: 2025-01-14 00:00:08

This migration adds enhanced metadata fields inspired by Agent-K:
- document_type enum for classification
- sectors array for industry tagging
- main_topics array for topic classification
- geographies array for geographic relevance
- company_names array for entity extraction
- truthfulness_score for credibility assessment
- source_url and source_type for provenance
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Document type enum values (from Agent-K)
DOCUMENT_TYPE_VALUES = [
    "academic_paper",
    "news_article",
    "blog_post",
    "company_report",
    "financial_statement",
    "legal_document",
    "technical_documentation",
    "press_release",
    "marketing_material",
    "government_document",
    "patent",
    "presentation",
    "whitepaper",
    "case_study",
    "policy_document",
    "regulatory_filing",
    "internal_memo",
    "contract",
    "invoice",
    "spreadsheet_data",
    "unknown",
]

# Source type enum values
SOURCE_TYPE_VALUES = [
    "upload",
    "url",
    "email",
    "api",
    "crawler",
    "batch_import",
    "unknown",
]


def upgrade() -> None:
    # Create document_type enum
    document_type_enum = postgresql.ENUM(
        *DOCUMENT_TYPE_VALUES,
        name="documenttype",
        create_type=False,
    )
    document_type_enum.create(op.get_bind(), checkfirst=True)

    # Create source_type enum
    source_type_enum = postgresql.ENUM(
        *SOURCE_TYPE_VALUES,
        name="sourcetype",
        create_type=False,
    )
    source_type_enum.create(op.get_bind(), checkfirst=True)

    # Add columns to documents table
    op.add_column(
        "documents",
        sa.Column(
            "document_type",
            sa.Enum(*DOCUMENT_TYPE_VALUES, name="documenttype"),
            nullable=True,
            server_default="unknown",
            comment="Document classification type",
        ),
    )

    op.add_column(
        "documents",
        sa.Column(
            "source_type",
            sa.Enum(*SOURCE_TYPE_VALUES, name="sourcetype"),
            nullable=True,
            server_default="unknown",
            comment="How the document was ingested",
        ),
    )

    op.add_column(
        "documents",
        sa.Column(
            "source_url",
            sa.Text,
            nullable=True,
            comment="Original source URL if applicable",
        ),
    )

    op.add_column(
        "documents",
        sa.Column(
            "sectors",
            postgresql.ARRAY(sa.String(100)),
            nullable=True,
            server_default="{}",
            comment="Industry sectors relevant to document",
        ),
    )

    op.add_column(
        "documents",
        sa.Column(
            "main_topics",
            postgresql.ARRAY(sa.String(200)),
            nullable=True,
            server_default="{}",
            comment="Main topics discussed in document",
        ),
    )

    op.add_column(
        "documents",
        sa.Column(
            "geographies",
            postgresql.ARRAY(sa.String(100)),
            nullable=True,
            server_default="{}",
            comment="Geographic regions mentioned",
        ),
    )

    op.add_column(
        "documents",
        sa.Column(
            "company_names",
            postgresql.ARRAY(sa.String(200)),
            nullable=True,
            server_default="{}",
            comment="Company names mentioned in document",
        ),
    )

    op.add_column(
        "documents",
        sa.Column(
            "authors",
            postgresql.ARRAY(sa.String(200)),
            nullable=True,
            server_default="{}",
            comment="Document authors if identified",
        ),
    )

    op.add_column(
        "documents",
        sa.Column(
            "publishing_organization",
            sa.String(300),
            nullable=True,
            comment="Organization that published the document",
        ),
    )

    op.add_column(
        "documents",
        sa.Column(
            "publication_date",
            sa.Date,
            nullable=True,
            comment="Publication date if identified",
        ),
    )

    # Add truthfulness assessment columns to document_versions
    op.add_column(
        "document_versions",
        sa.Column(
            "truthfulness_score",
            sa.Float,
            nullable=True,
            comment="Overall truthfulness score 0-100",
        ),
    )

    op.add_column(
        "document_versions",
        sa.Column(
            "bias_score",
            sa.Float,
            nullable=True,
            comment="Bias level score 0-100 (0=neutral)",
        ),
    )

    op.add_column(
        "document_versions",
        sa.Column(
            "credibility_assessment",
            postgresql.JSON,
            nullable=True,
            comment="Detailed credibility assessment JSON",
        ),
    )

    # Create indexes for array fields (for overlap queries)
    op.create_index(
        "ix_documents_sectors",
        "documents",
        ["sectors"],
        postgresql_using="gin",
    )

    op.create_index(
        "ix_documents_main_topics",
        "documents",
        ["main_topics"],
        postgresql_using="gin",
    )

    op.create_index(
        "ix_documents_geographies",
        "documents",
        ["geographies"],
        postgresql_using="gin",
    )

    op.create_index(
        "ix_documents_company_names",
        "documents",
        ["company_names"],
        postgresql_using="gin",
    )

    # Create index for document type
    op.create_index(
        "ix_documents_document_type",
        "documents",
        ["document_type"],
    )

    # Create index for source type
    op.create_index(
        "ix_documents_source_type",
        "documents",
        ["source_type"],
    )


def downgrade() -> None:
    # Drop indexes
    op.drop_index("ix_documents_source_type", table_name="documents")
    op.drop_index("ix_documents_document_type", table_name="documents")
    op.drop_index("ix_documents_company_names", table_name="documents")
    op.drop_index("ix_documents_geographies", table_name="documents")
    op.drop_index("ix_documents_main_topics", table_name="documents")
    op.drop_index("ix_documents_sectors", table_name="documents")

    # Drop document_versions columns
    op.drop_column("document_versions", "credibility_assessment")
    op.drop_column("document_versions", "bias_score")
    op.drop_column("document_versions", "truthfulness_score")

    # Drop documents columns
    op.drop_column("documents", "publication_date")
    op.drop_column("documents", "publishing_organization")
    op.drop_column("documents", "authors")
    op.drop_column("documents", "company_names")
    op.drop_column("documents", "geographies")
    op.drop_column("documents", "main_topics")
    op.drop_column("documents", "sectors")
    op.drop_column("documents", "source_url")
    op.drop_column("documents", "source_type")
    op.drop_column("documents", "document_type")

    # Drop enums
    op.execute("DROP TYPE IF EXISTS sourcetype")
    op.execute("DROP TYPE IF EXISTS documenttype")
