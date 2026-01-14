"""Multi-level extraction service for domain-specific fact extraction."""

import json
import logging
import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from evidence_repository.config import get_settings
from evidence_repository.extraction.multilevel.prompts import (
    build_system_prompt,
    build_user_prompt,
)

# Get settings instance
settings = get_settings()
from evidence_repository.extraction.multilevel.schemas import (
    ExtractedFactClaim,
    ExtractedFactConstraint,
    ExtractedFactMetric,
    ExtractedFactRisk,
    ExtractedQualityConflict,
    ExtractedQualityQuestion,
    MultiLevelExtractionResult,
)
from evidence_repository.extraction.vocabularies import get_vocabulary
from evidence_repository.models.document import DocumentVersion
from evidence_repository.models.extraction_level import (
    ExtractionLevel,
    ExtractionLevelCode,
    ExtractionProfile,
    ExtractionProfileCode,
    ExtractionRunStatus,
    FactExtractionRun,
    ProcessContext,
)
from evidence_repository.models.facts import (
    ConstraintType,
    FactCertainty,
    FactClaim,
    FactConstraint,
    FactMetric,
    FactRisk,
    RiskSeverity,
    SourceReliability,
)
from evidence_repository.models.quality import (
    ConflictSeverity,
    QualityConflict,
    QualityOpenQuestion,
    QuestionCategory,
)

logger = logging.getLogger(__name__)


class MultiLevelExtractionService:
    """Service for multi-level domain-specific fact extraction.

    Handles extraction at different levels of detail (L1-L4) using
    profile-specific vocabularies and LLM-based extraction.
    """

    def __init__(self, openai_client: Any | None = None):
        """Initialize extraction service.

        Args:
            openai_client: OpenAI client instance (optional, will create if not provided)
        """
        self._openai_client = openai_client
        self._model = settings.openai_model if hasattr(settings, "openai_model") else "gpt-4o"

    @property
    def openai_client(self) -> Any:
        """Get or create OpenAI client."""
        if self._openai_client is None:
            from openai import OpenAI
            self._openai_client = OpenAI(api_key=settings.openai_api_key)
        return self._openai_client

    async def extract(
        self,
        session: AsyncSession,
        version_id: uuid.UUID,
        profile_code: str,
        level: int,
        process_context: str = "unspecified",
        triggered_by: str | None = None,
        schema_version: str = "1.0",
        vocab_version: str = "1.0",
    ) -> FactExtractionRun:
        """Run extraction for a document version at specified profile/context/level.

        Args:
            session: Database session
            version_id: Document version ID
            profile_code: Extraction profile code (vc, pharma, insurance, general)
            level: Extraction level (1-4)
            process_context: Business process context (e.g., vc.ic_decision)
            triggered_by: User who triggered extraction
            schema_version: Schema version for output
            vocab_version: Vocabulary version used

        Returns:
            ExtractionRun record
        """
        # Get document version with document
        version = await session.get(
            DocumentVersion,
            version_id,
            options=[selectinload(DocumentVersion.document)],
        )
        if not version:
            raise ValueError(f"Document version {version_id} not found")

        # Parse process context
        try:
            process_ctx = ProcessContext(process_context)
        except ValueError:
            process_ctx = ProcessContext.UNSPECIFIED

        # Get profile and level records
        profile = await self._get_or_create_profile(session, profile_code)
        level_record = await self._get_or_create_level(session, level)

        # Check for existing active run (now includes process_context)
        existing_run = await self._get_active_run(
            session, version_id, profile.id, process_ctx, level_record.id
        )
        if existing_run:
            logger.info(
                f"Active extraction run already exists for version={version_id}, "
                f"profile={profile_code}, process_context={process_context}, level={level}"
            )
            return existing_run

        # Create extraction run
        run = FactExtractionRun(
            document_id=version.document_id,
            version_id=version_id,
            profile_id=profile.id,
            process_context=process_ctx,
            level_id=level_record.id,
            status=ExtractionRunStatus.RUNNING,
            started_at=datetime.utcnow(),
            triggered_by=triggered_by,
            schema_version=schema_version,
            vocab_version=vocab_version,
        )
        session.add(run)
        await session.flush()

        try:
            # Get document text
            document_text = version.extracted_text or ""
            if not document_text:
                raise ValueError("No extracted text available for document version")

            # Get vocabulary and build prompts
            vocabulary = get_vocabulary(profile_code)
            vocab_context = vocabulary.get_extraction_prompt_context(level)
            system_prompt = build_system_prompt(vocab_context, level)

            # Get previous extraction results if available (for incremental)
            previous_extraction = None
            if level > 1:
                previous_extraction = await self._get_previous_extraction(
                    session, version_id, profile.id, level - 1
                )

            user_prompt = build_user_prompt(
                document_text,
                spans=None,  # TODO: Add span support
                previous_extraction=previous_extraction,
            )

            # Call LLM
            result = await self._call_llm(system_prompt, user_prompt)

            # Parse and persist results
            await self._persist_results(session, run, result)

            # Update run status
            run.status = ExtractionRunStatus.SUCCEEDED
            run.finished_at = datetime.utcnow()
            run.metadata_ = {
                "claims_count": len(result.claims),
                "metrics_count": len(result.metrics),
                "constraints_count": len(result.constraints),
                "risks_count": len(result.risks),
                "conflicts_count": len(result.conflicts),
                "questions_count": len(result.open_questions),
            }

        except Exception as e:
            logger.exception(f"Extraction failed for run {run.id}")
            run.status = ExtractionRunStatus.FAILED
            run.finished_at = datetime.utcnow()
            run.error = str(e)
            raise

        await session.commit()
        return run

    async def _get_or_create_profile(
        self, session: AsyncSession, profile_code: str
    ) -> ExtractionProfile:
        """Get or create extraction profile."""
        try:
            code_enum = ExtractionProfileCode(profile_code)
        except ValueError:
            code_enum = ExtractionProfileCode.GENERAL

        stmt = select(ExtractionProfile).where(ExtractionProfile.code == code_enum)
        result = await session.execute(stmt)
        profile = result.scalar_one_or_none()

        if not profile:
            vocabulary = get_vocabulary(profile_code)
            profile = ExtractionProfile(
                name=vocabulary.profile_name,
                code=code_enum,
                description=f"Extraction profile for {vocabulary.profile_name}",
                is_active=True,
                config={},
            )
            session.add(profile)
            await session.flush()

        return profile

    async def _get_or_create_level(
        self, session: AsyncSession, level: int
    ) -> ExtractionLevel:
        """Get or create extraction level."""
        level_mapping = {
            1: ExtractionLevelCode.L1_BASIC,
            2: ExtractionLevelCode.L2_STANDARD,
            3: ExtractionLevelCode.L3_DEEP,
            4: ExtractionLevelCode.L4_FORENSIC,
        }
        code = level_mapping.get(level, ExtractionLevelCode.L2_STANDARD)

        stmt = select(ExtractionLevel).where(ExtractionLevel.code == code)
        result = await session.execute(stmt)
        level_record = result.scalar_one_or_none()

        if not level_record:
            level_names = {
                1: "Basic",
                2: "Standard",
                3: "Deep",
                4: "Forensic",
            }
            level_record = ExtractionLevel(
                code=code,
                rank=level,
                name=level_names.get(level, "Standard"),
                description=f"Level {level} extraction",
                is_active=True,
                config={},
            )
            session.add(level_record)
            await session.flush()

        return level_record

    async def _get_active_run(
        self,
        session: AsyncSession,
        version_id: uuid.UUID,
        profile_id: uuid.UUID,
        process_context: ProcessContext,
        level_id: uuid.UUID,
    ) -> FactExtractionRun | None:
        """Check for existing active extraction run."""
        stmt = select(FactExtractionRun).where(
            FactExtractionRun.version_id == version_id,
            FactExtractionRun.profile_id == profile_id,
            FactExtractionRun.process_context == process_context,
            FactExtractionRun.level_id == level_id,
            FactExtractionRun.status.in_([
                ExtractionRunStatus.QUEUED,
                ExtractionRunStatus.RUNNING,
            ]),
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_previous_extraction(
        self,
        session: AsyncSession,
        version_id: uuid.UUID,
        profile_id: uuid.UUID,
        level: int,
    ) -> dict[str, Any] | None:
        """Get results from previous level extraction for incremental extraction."""
        level_record = await self._get_or_create_level(session, level)

        stmt = select(FactExtractionRun).where(
            FactExtractionRun.version_id == version_id,
            FactExtractionRun.profile_id == profile_id,
            FactExtractionRun.level_id == level_record.id,
            FactExtractionRun.status == ExtractionRunStatus.SUCCEEDED,
        ).order_by(FactExtractionRun.finished_at.desc()).limit(1)

        result = await session.execute(stmt)
        run = result.scalar_one_or_none()

        if not run:
            return None

        # Load facts from previous run
        claims_stmt = select(FactClaim).where(FactClaim.extraction_run_id == run.id)
        metrics_stmt = select(FactMetric).where(FactMetric.extraction_run_id == run.id)

        claims_result = await session.execute(claims_stmt)
        metrics_result = await session.execute(metrics_stmt)

        return {
            "claims": [
                {
                    "subject": c.subject,
                    "predicate": c.predicate,
                    "object": c.object,
                    "claim_type": c.claim_type,
                }
                for c in claims_result.scalars()
            ],
            "metrics": [
                {
                    "metric_name": m.metric_name,
                    "value_numeric": m.value_numeric,
                    "value_raw": m.value_raw,
                    "period_type": m.period_type,
                }
                for m in metrics_result.scalars()
            ],
        }

    async def _call_llm(
        self, system_prompt: str, user_prompt: str
    ) -> MultiLevelExtractionResult:
        """Call LLM for extraction."""
        import asyncio

        # Run in executor since OpenAI client is sync
        def _sync_call():
            response = self.openai_client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
            )
            return response.choices[0].message.content

        loop = asyncio.get_event_loop()
        response_text = await loop.run_in_executor(None, _sync_call)

        # Parse response
        try:
            data = json.loads(response_text)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response: {e}")
            raise ValueError(f"Invalid JSON response from LLM: {e}")

        return MultiLevelExtractionResult(
            profile_code=data.get("profile_code", "general"),
            level=data.get("level", 2),
            claims=[ExtractedFactClaim(**c) for c in data.get("claims", [])],
            metrics=[ExtractedFactMetric(**m) for m in data.get("metrics", [])],
            constraints=[ExtractedFactConstraint(**c) for c in data.get("constraints", [])],
            risks=[ExtractedFactRisk(**r) for r in data.get("risks", [])],
            conflicts=[ExtractedQualityConflict(**c) for c in data.get("conflicts", [])],
            open_questions=[ExtractedQualityQuestion(**q) for q in data.get("open_questions", [])],
        )

    async def _persist_results(
        self,
        session: AsyncSession,
        run: FactExtractionRun,
        result: MultiLevelExtractionResult,
    ) -> None:
        """Persist extraction results to database."""
        # Persist claims
        for claim in result.claims:
            fact_claim = FactClaim(
                document_id=run.document_id,
                version_id=run.version_id,
                profile_id=run.profile_id,
                process_context=run.process_context,
                level_id=run.level_id,
                extraction_run_id=run.id,
                subject=claim.subject,
                predicate=claim.predicate,
                object=claim.object,
                claim_type=claim.claim_type,
                time_scope=claim.time_scope,
                certainty=self._map_certainty(claim.certainty),
                source_reliability=self._map_reliability(claim.source_reliability),
                extraction_confidence=claim.extraction_confidence,
                span_refs=claim.span_refs,
                evidence_quote=claim.evidence_quote,
            )
            session.add(fact_claim)

        # Persist metrics
        for metric in result.metrics:
            fact_metric = FactMetric(
                document_id=run.document_id,
                version_id=run.version_id,
                profile_id=run.profile_id,
                process_context=run.process_context,
                level_id=run.level_id,
                extraction_run_id=run.id,
                entity_id=metric.entity_id,
                entity_type=metric.entity_type,
                metric_name=metric.metric_name,
                metric_category=metric.metric_category,
                value_numeric=metric.value_numeric,
                value_raw=metric.value_raw,
                unit=metric.unit,
                currency=metric.currency,
                period_start=metric.period_start,
                period_end=metric.period_end,
                as_of=metric.as_of,
                period_type=metric.period_type,
                method=metric.method,
                certainty=self._map_certainty(metric.certainty),
                source_reliability=self._map_reliability(metric.source_reliability),
                extraction_confidence=metric.extraction_confidence,
                quality_flags=metric.quality_flags,
                span_refs=metric.span_refs,
                evidence_quote=metric.evidence_quote,
            )
            session.add(fact_metric)

        # Persist constraints
        for constraint in result.constraints:
            fact_constraint = FactConstraint(
                document_id=run.document_id,
                version_id=run.version_id,
                profile_id=run.profile_id,
                process_context=run.process_context,
                level_id=run.level_id,
                extraction_run_id=run.id,
                constraint_type=self._map_constraint_type(constraint.constraint_type),
                applies_to=constraint.applies_to,
                statement=constraint.statement,
                certainty=self._map_certainty(constraint.certainty),
                extraction_confidence=constraint.extraction_confidence,
                span_refs=constraint.span_refs,
            )
            session.add(fact_constraint)

        # Persist risks
        for risk in result.risks:
            fact_risk = FactRisk(
                document_id=run.document_id,
                version_id=run.version_id,
                profile_id=run.profile_id,
                process_context=run.process_context,
                level_id=run.level_id,
                extraction_run_id=run.id,
                risk_type=risk.risk_type,
                risk_category=risk.risk_category,
                severity=self._map_severity(risk.severity),
                statement=risk.statement,
                rationale=risk.rationale,
                related_claims=risk.related_claims,
                related_metrics=risk.related_metrics,
                extraction_confidence=risk.extraction_confidence,
                span_refs=risk.span_refs,
            )
            session.add(fact_risk)

        # Persist conflicts
        for conflict in result.conflicts:
            quality_conflict = QualityConflict(
                document_id=run.document_id,
                version_id=run.version_id,
                profile_id=run.profile_id,
                process_context=run.process_context,
                level_id=run.level_id,
                extraction_run_id=run.id,
                topic=conflict.topic,
                severity=self._map_conflict_severity(conflict.severity),
                claim_ids=conflict.claim_ids,
                metric_ids=conflict.metric_ids,
                reason=conflict.reason,
            )
            session.add(quality_conflict)

        # Persist open questions
        for question in result.open_questions:
            quality_question = QualityOpenQuestion(
                document_id=run.document_id,
                version_id=run.version_id,
                profile_id=run.profile_id,
                process_context=run.process_context,
                level_id=run.level_id,
                extraction_run_id=run.id,
                question=question.question,
                category=self._map_question_category(question.category),
                context=question.context,
                related_claim_ids=question.related_claim_ids,
                related_metric_ids=question.related_metric_ids,
            )
            session.add(quality_question)

        await session.flush()

    def _map_certainty(self, value: str) -> FactCertainty:
        """Map certainty string to enum."""
        mapping = {
            "definite": FactCertainty.DEFINITE,
            "probable": FactCertainty.PROBABLE,
            "possible": FactCertainty.POSSIBLE,
            "speculative": FactCertainty.SPECULATIVE,
        }
        return mapping.get(value.lower(), FactCertainty.PROBABLE)

    def _map_reliability(self, value: str) -> SourceReliability:
        """Map reliability string to enum."""
        mapping = {
            "audited": SourceReliability.AUDITED,
            "official": SourceReliability.OFFICIAL,
            "internal": SourceReliability.INTERNAL,
            "third_party": SourceReliability.THIRD_PARTY,
            "unknown": SourceReliability.UNKNOWN,
        }
        return mapping.get(value.lower(), SourceReliability.UNKNOWN)

    def _map_constraint_type(self, value: str) -> ConstraintType:
        """Map constraint type string to enum."""
        mapping = {
            "definition": ConstraintType.DEFINITION,
            "dependency": ConstraintType.DEPENDENCY,
            "exclusion": ConstraintType.EXCLUSION,
            "eligibility": ConstraintType.ELIGIBILITY,
            "covenant": ConstraintType.COVENANT,
            "assumption": ConstraintType.ASSUMPTION,
        }
        return mapping.get(value.lower(), ConstraintType.DEFINITION)

    def _map_severity(self, value: str) -> RiskSeverity:
        """Map severity string to enum."""
        mapping = {
            "critical": RiskSeverity.CRITICAL,
            "high": RiskSeverity.HIGH,
            "medium": RiskSeverity.MEDIUM,
            "low": RiskSeverity.LOW,
            "informational": RiskSeverity.INFORMATIONAL,
        }
        return mapping.get(value.lower(), RiskSeverity.MEDIUM)

    def _map_conflict_severity(self, value: str) -> ConflictSeverity:
        """Map conflict severity string to enum."""
        mapping = {
            "critical": ConflictSeverity.CRITICAL,
            "high": ConflictSeverity.HIGH,
            "medium": ConflictSeverity.MEDIUM,
            "low": ConflictSeverity.LOW,
            "informational": ConflictSeverity.INFORMATIONAL,
        }
        return mapping.get(value.lower(), ConflictSeverity.MEDIUM)

    def _map_question_category(self, value: str) -> QuestionCategory:
        """Map question category string to enum."""
        mapping = {
            "missing_data": QuestionCategory.MISSING_DATA,
            "ambiguous": QuestionCategory.AMBIGUOUS,
            "verification": QuestionCategory.VERIFICATION,
            "clarification": QuestionCategory.CLARIFICATION,
            "methodology": QuestionCategory.METHODOLOGY,
            "temporal": QuestionCategory.TEMPORAL,
        }
        return mapping.get(value.lower(), QuestionCategory.MISSING_DATA)
