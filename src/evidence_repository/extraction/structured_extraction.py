"""Structured extraction service for extracting Juris-critical facts.

Extracts metrics and claims from document spans using LLM-based extraction
with structured output parsing.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import UUID

from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from evidence_repository.config import get_settings
from evidence_repository.models.evidence import (
    Certainty,
    Claim,
    ClaimType,
    Metric,
    MetricType,
    Reliability,
    Span,
    SpanType,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Extraction Output Schemas (Pydantic models for structured output)
# =============================================================================


class ExtractedMetric(BaseModel):
    """Structured output for an extracted metric."""

    metric_type: str = Field(
        description="Type of metric: arr, mrr, revenue, burn, runway, cash, headcount, churn, nrr, gross_margin, cac, ltv, ebitda, growth_rate, other"
    )
    metric_name: str = Field(description="Human-readable name of the metric")
    metric_value: str = Field(description="Value as stated in the document")
    numeric_value: float | None = Field(
        default=None, description="Parsed numeric value (if applicable)"
    )
    unit: str | None = Field(default=None, description="Unit of measurement (USD, %, months, etc.)")
    time_scope: str | None = Field(
        default=None, description="Time period (e.g., 'Q4 2024', 'FY2023', 'as of Jan 2024')"
    )
    certainty: str = Field(
        default="probable",
        description="Certainty level: definite, probable, possible, speculative",
    )
    reliability: str = Field(
        default="unknown",
        description="Source reliability: verified, official, internal, third_party, unknown",
    )
    extraction_confidence: float = Field(
        ge=0.0, le=1.0, description="Confidence in extraction accuracy (0.0-1.0)"
    )
    evidence_quote: str = Field(description="Exact quote from source supporting this metric")


class ExtractedClaim(BaseModel):
    """Structured output for an extracted claim."""

    claim_type: str = Field(
        description="Type of claim: soc2, iso27001, gdpr, hipaa, ip_ownership, security_incident, compliance, certification, audit, policy, other"
    )
    claim_text: str = Field(description="The claim statement")
    time_scope: str | None = Field(
        default=None, description="Time period or effective date of the claim"
    )
    certainty: str = Field(
        default="probable",
        description="Certainty level: definite, probable, possible, speculative",
    )
    reliability: str = Field(
        default="unknown",
        description="Source reliability: verified, official, internal, third_party, unknown",
    )
    extraction_confidence: float = Field(
        ge=0.0, le=1.0, description="Confidence in extraction accuracy (0.0-1.0)"
    )
    evidence_quote: str = Field(description="Exact quote from source supporting this claim")


class ExtractionResult(BaseModel):
    """Combined extraction result from a span."""

    metrics: list[ExtractedMetric] = Field(default_factory=list)
    claims: list[ExtractedClaim] = Field(default_factory=list)


# =============================================================================
# Extraction Prompts
# =============================================================================

SYSTEM_PROMPT = """You are a specialized extraction system for legal due diligence.
Your task is to extract structured information from document text, focusing on:

METRICS (Financial/Business KPIs):
- ARR (Annual Recurring Revenue)
- MRR (Monthly Recurring Revenue)
- Revenue
- Burn rate
- Runway (months of cash)
- Cash on hand
- Headcount
- Churn rate
- NRR (Net Revenue Retention)
- Gross margin
- CAC (Customer Acquisition Cost)
- LTV (Lifetime Value)
- EBITDA
- Growth rate

CLAIMS (Compliance/Legal):
- SOC2 certification or compliance
- ISO27001 certification
- GDPR compliance
- HIPAA compliance
- IP ownership assertions
- Security incidents
- Other compliance claims
- Audit results
- Policy statements

For each extraction:
1. ALWAYS include the exact quote from the source text
2. Assess certainty: definite (explicitly stated), probable (strongly implied), possible (mentioned but uncertain), speculative (inferred)
3. Assess reliability based on document type: verified (audited), official (company docs), internal (unverified), third_party, unknown
4. Provide extraction confidence (0.0-1.0) based on clarity of the information
5. Include time scope when mentioned (dates, quarters, fiscal years)

Return ONLY valid JSON matching the schema. Extract ALL relevant metrics and claims found."""

USER_PROMPT_TEMPLATE = """Extract all metrics and claims from the following text:

---
{text}
---

Return a JSON object with this structure:
{{
  "metrics": [
    {{
      "metric_type": "arr|mrr|revenue|burn|runway|cash|headcount|churn|nrr|gross_margin|cac|ltv|ebitda|growth_rate|other",
      "metric_name": "Human readable name",
      "metric_value": "Value as stated",
      "numeric_value": 1234.56,
      "unit": "USD|%|months|etc",
      "time_scope": "Q4 2024|FY2023|etc",
      "certainty": "definite|probable|possible|speculative",
      "reliability": "verified|official|internal|third_party|unknown",
      "extraction_confidence": 0.95,
      "evidence_quote": "exact quote from text"
    }}
  ],
  "claims": [
    {{
      "claim_type": "soc2|iso27001|gdpr|hipaa|ip_ownership|security_incident|compliance|certification|audit|policy|other",
      "claim_text": "The claim statement",
      "time_scope": "as of 2024|etc",
      "certainty": "definite|probable|possible|speculative",
      "reliability": "verified|official|internal|third_party|unknown",
      "extraction_confidence": 0.90,
      "evidence_quote": "exact quote from text"
    }}
  ]
}}

If no metrics or claims are found, return empty arrays."""


# =============================================================================
# Extraction Service
# =============================================================================


@dataclass
class ExtractionStats:
    """Statistics from an extraction run."""

    spans_processed: int = 0
    metrics_extracted: int = 0
    claims_extracted: int = 0
    errors: int = 0
    tokens_used: int = 0


class StructuredExtractionService:
    """Service for extracting structured metrics and claims from spans.

    Uses OpenAI GPT-4 for extraction with structured output parsing.
    All extractions reference source spans for traceability.
    """

    # Span types to process for extraction
    EXTRACTABLE_SPAN_TYPES = {SpanType.TEXT, SpanType.HEADING, SpanType.TABLE}

    def __init__(
        self,
        db: AsyncSession,
        api_key: str | None = None,
        model: str = "gpt-4o",
        max_tokens: int = 4096,
    ):
        """Initialize extraction service.

        Args:
            db: Database session.
            api_key: OpenAI API key (uses settings if not provided).
            model: OpenAI model to use.
            max_tokens: Maximum tokens for response.
        """
        self.db = db
        settings = get_settings()
        self.api_key = api_key or settings.openai_api_key
        self.model = model
        self.max_tokens = max_tokens
        self._client: AsyncOpenAI | None = None

    @property
    def client(self) -> AsyncOpenAI:
        """Get or create the AsyncOpenAI client."""
        if self._client is None:
            if not self.api_key:
                raise ValueError("OpenAI API key not configured")
            self._client = AsyncOpenAI(api_key=self.api_key)
        return self._client

    async def extract_from_version(
        self,
        version_id: UUID,
        project_id: UUID,
        reprocess: bool = False,
    ) -> ExtractionStats:
        """Extract metrics and claims from all spans of a document version.

        Args:
            version_id: Document version to extract from.
            project_id: Project to associate extractions with.
            reprocess: If True, delete existing extractions first.

        Returns:
            ExtractionStats with results.
        """
        stats = ExtractionStats()

        # Get extractable spans
        spans = await self._get_extractable_spans(version_id)

        if not spans:
            logger.info(f"No extractable spans found for version {version_id}")
            return stats

        # Delete existing extractions if reprocessing
        if reprocess:
            await self._delete_existing_extractions(version_id, project_id)

        logger.info(f"Extracting from {len(spans)} spans for version {version_id}")

        for span in spans:
            try:
                result = await self._extract_from_span(span)
                if result:
                    # Persist extractions
                    metrics_created = await self._persist_metrics(
                        result.metrics, span.id, project_id
                    )
                    claims_created = await self._persist_claims(
                        result.claims, span.id, project_id
                    )
                    stats.metrics_extracted += metrics_created
                    stats.claims_extracted += claims_created
                stats.spans_processed += 1
            except Exception as e:
                logger.error(f"Extraction failed for span {span.id}: {e}")
                stats.errors += 1

        await self.db.flush()

        logger.info(
            f"Extraction complete: {stats.metrics_extracted} metrics, "
            f"{stats.claims_extracted} claims from {stats.spans_processed} spans"
        )

        return stats

    async def extract_from_span(
        self,
        span_id: UUID,
        project_id: UUID,
    ) -> ExtractionResult | None:
        """Extract metrics and claims from a single span.

        Args:
            span_id: Span to extract from.
            project_id: Project to associate extractions with.

        Returns:
            ExtractionResult or None if extraction failed.
        """
        # Get span
        result = await self.db.execute(select(Span).where(Span.id == span_id))
        span = result.scalar_one_or_none()

        if not span:
            raise ValueError(f"Span {span_id} not found")

        extraction = await self._extract_from_span(span)

        if extraction:
            # Persist extractions
            await self._persist_metrics(extraction.metrics, span_id, project_id)
            await self._persist_claims(extraction.claims, span_id, project_id)
            await self.db.flush()

        return extraction

    async def _extract_from_span(self, span: Span) -> ExtractionResult | None:
        """Extract from a single span using LLM.

        Args:
            span: Span to extract from.

        Returns:
            ExtractionResult or None.
        """
        if not span.text_content or len(span.text_content.strip()) < 20:
            return None

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": USER_PROMPT_TEMPLATE.format(text=span.text_content),
                    },
                ],
                max_tokens=self.max_tokens,
                temperature=0.1,  # Low temperature for consistent extraction
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content
            if not content:
                return None

            # Parse JSON response
            data = json.loads(content)
            return ExtractionResult(
                metrics=[ExtractedMetric(**m) for m in data.get("metrics", [])],
                claims=[ExtractedClaim(**c) for c in data.get("claims", [])],
            )

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse extraction response: {e}")
            return None
        except Exception as e:
            logger.error(f"Extraction API call failed: {e}")
            raise

    async def _persist_metrics(
        self,
        metrics: list[ExtractedMetric],
        span_id: UUID,
        project_id: UUID,
    ) -> int:
        """Persist extracted metrics to database.

        Args:
            metrics: Extracted metrics.
            span_id: Source span ID.
            project_id: Project ID.

        Returns:
            Number of metrics created.
        """
        created = 0

        for extracted in metrics:
            # Parse metric type
            try:
                metric_type = MetricType(extracted.metric_type.lower())
            except ValueError:
                metric_type = MetricType.OTHER

            # Parse certainty
            try:
                certainty = Certainty(extracted.certainty.lower())
            except ValueError:
                certainty = Certainty.PROBABLE

            # Parse reliability
            try:
                reliability = Reliability(extracted.reliability.lower())
            except ValueError:
                reliability = Reliability.UNKNOWN

            metric = Metric(
                project_id=project_id,
                span_id=span_id,
                metric_name=extracted.metric_name,
                metric_type=metric_type,
                metric_value=extracted.metric_value,
                numeric_value=extracted.numeric_value,
                unit=extracted.unit,
                time_scope=extracted.time_scope,
                certainty=certainty,
                reliability=reliability,
                extraction_confidence=extracted.extraction_confidence,
                metadata_={
                    "evidence_quote": extracted.evidence_quote,
                    "extraction_model": self.model,
                },
            )
            self.db.add(metric)
            created += 1

        return created

    async def _persist_claims(
        self,
        claims: list[ExtractedClaim],
        span_id: UUID,
        project_id: UUID,
    ) -> int:
        """Persist extracted claims to database.

        Args:
            claims: Extracted claims.
            span_id: Source span ID.
            project_id: Project ID.

        Returns:
            Number of claims created.
        """
        created = 0

        for extracted in claims:
            # Parse claim type
            try:
                claim_type = ClaimType(extracted.claim_type.lower())
            except ValueError:
                claim_type = ClaimType.OTHER

            # Parse certainty
            try:
                certainty = Certainty(extracted.certainty.lower())
            except ValueError:
                certainty = Certainty.PROBABLE

            # Parse reliability
            try:
                reliability = Reliability(extracted.reliability.lower())
            except ValueError:
                reliability = Reliability.UNKNOWN

            claim = Claim(
                project_id=project_id,
                span_id=span_id,
                claim_text=extracted.claim_text,
                claim_type=claim_type,
                time_scope=extracted.time_scope,
                certainty=certainty,
                reliability=reliability,
                extraction_confidence=extracted.extraction_confidence,
                metadata_={
                    "evidence_quote": extracted.evidence_quote,
                    "extraction_model": self.model,
                },
            )
            self.db.add(claim)
            created += 1

        return created

    async def _get_extractable_spans(self, version_id: UUID) -> list[Span]:
        """Get spans suitable for extraction.

        Args:
            version_id: Document version ID.

        Returns:
            List of extractable Span records.
        """
        result = await self.db.execute(
            select(Span)
            .where(
                Span.document_version_id == version_id,
                Span.span_type.in_(self.EXTRACTABLE_SPAN_TYPES),
            )
            .order_by(Span.created_at)
        )
        return list(result.scalars().all())

    async def _delete_existing_extractions(
        self,
        version_id: UUID,
        project_id: UUID,
    ) -> tuple[int, int]:
        """Delete existing extractions for a version.

        Args:
            version_id: Document version ID.
            project_id: Project ID.

        Returns:
            Tuple of (metrics_deleted, claims_deleted).
        """
        from sqlalchemy import delete

        # Get span IDs for this version
        span_ids_result = await self.db.execute(
            select(Span.id).where(Span.document_version_id == version_id)
        )
        span_ids = [row[0] for row in span_ids_result.fetchall()]

        if not span_ids:
            return 0, 0

        # Delete metrics
        metrics_result = await self.db.execute(
            delete(Metric).where(
                Metric.project_id == project_id,
                Metric.span_id.in_(span_ids),
            )
        )

        # Delete claims
        claims_result = await self.db.execute(
            delete(Claim).where(
                Claim.project_id == project_id,
                Claim.span_id.in_(span_ids),
            )
        )

        await self.db.flush()

        return metrics_result.rowcount, claims_result.rowcount

    async def get_extraction_stats(
        self,
        version_id: UUID,
        project_id: UUID,
    ) -> dict[str, Any]:
        """Get extraction statistics for a version.

        Args:
            version_id: Document version ID.
            project_id: Project ID.

        Returns:
            Dict with extraction statistics.
        """
        from sqlalchemy import func

        # Get span IDs for this version
        span_ids_result = await self.db.execute(
            select(Span.id).where(Span.document_version_id == version_id)
        )
        span_ids = [row[0] for row in span_ids_result.fetchall()]

        if not span_ids:
            return {
                "version_id": str(version_id),
                "project_id": str(project_id),
                "total_spans": 0,
                "total_metrics": 0,
                "total_claims": 0,
                "metrics_by_type": {},
                "claims_by_type": {},
            }

        # Count metrics by type
        metrics_result = await self.db.execute(
            select(Metric.metric_type, func.count(Metric.id))
            .where(
                Metric.project_id == project_id,
                Metric.span_id.in_(span_ids),
            )
            .group_by(Metric.metric_type)
        )
        metrics_by_type = {row[0].value: row[1] for row in metrics_result.fetchall()}

        # Count claims by type
        claims_result = await self.db.execute(
            select(Claim.claim_type, func.count(Claim.id))
            .where(
                Claim.project_id == project_id,
                Claim.span_id.in_(span_ids),
            )
            .group_by(Claim.claim_type)
        )
        claims_by_type = {row[0].value: row[1] for row in claims_result.fetchall()}

        return {
            "version_id": str(version_id),
            "project_id": str(project_id),
            "total_spans": len(span_ids),
            "total_metrics": sum(metrics_by_type.values()),
            "total_claims": sum(claims_by_type.values()),
            "metrics_by_type": metrics_by_type,
            "claims_by_type": claims_by_type,
        }

    async def close(self) -> None:
        """Close the client connection."""
        if self._client:
            await self._client.close()
            self._client = None
