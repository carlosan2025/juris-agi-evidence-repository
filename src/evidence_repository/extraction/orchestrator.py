"""Extraction Orchestrator - Central component for planning and managing extractions.

The ExtractionOrchestrator provides:
1. plan_extraction() - Returns an extraction plan based on settings and existing data
2. Prompt selection with programmatic composition (BASE + PROFILE + PROCESS_CONTEXT + LOD overlays)
3. Vocabulary injection based on profile and process context
4. Idempotency checking - prevents duplicate extraction runs
"""

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from evidence_repository.models.document import DocumentVersion
from evidence_repository.models.extraction_level import (
    ComputeMode,
    ExtractionLevel,
    ExtractionLevelCode,
    ExtractionProfile,
    ExtractionProfileCode,
    ExtractionRunStatus,
    ExtractionSetting,
    FactExtractionRun,
    ProcessContext,
    ScopeType,
)
from evidence_repository.models.project import ProjectDocument

logger = logging.getLogger(__name__)


# =============================================================================
# Data Classes for Extraction Planning
# =============================================================================


@dataclass
class ExtractionJob:
    """A single extraction job to be executed."""

    version_id: uuid.UUID
    profile_code: str
    process_context: str
    level: int
    level_code: ExtractionLevelCode
    triggered_by: str | None = None
    parent_run_id: uuid.UUID | None = None
    schema_version: str = "1.0"
    vocab_version: str = "1.0"


@dataclass
class ExtractionPlan:
    """Plan for extraction operations.

    Contains the list of jobs to execute, accounting for:
    - Which levels are already completed
    - Which levels need to be computed based on compute_mode
    - Dependencies between levels (lower levels must complete first)
    """

    version_id: uuid.UUID
    profile_code: str
    process_context: str
    target_level: int
    compute_mode: str
    jobs: list[ExtractionJob] = field(default_factory=list)
    skipped_levels: list[int] = field(default_factory=list)
    existing_runs: dict[int, uuid.UUID] = field(default_factory=dict)
    is_empty: bool = True

    @property
    def total_jobs(self) -> int:
        return len(self.jobs)

    @property
    def levels_to_compute(self) -> list[int]:
        return [job.level for job in self.jobs]


@dataclass
class PromptComposition:
    """Composed prompt from multiple overlays."""

    base_prompt: str
    profile_overlay: str
    process_context_overlay: str
    lod_overlay: str
    vocabulary_terms: dict[str, Any]
    final_system_prompt: str
    final_user_prompt: str | None = None


# =============================================================================
# Extraction Orchestrator
# =============================================================================


class ExtractionOrchestrator:
    """Central orchestrator for extraction planning and management.

    Responsibilities:
    1. Determine effective extraction settings for a document
    2. Plan which extraction jobs need to run
    3. Compose prompts based on profile, process context, and level
    4. Create and manage extraction run records
    """

    LEVEL_MAPPING = {
        1: ExtractionLevelCode.L1_BASIC,
        2: ExtractionLevelCode.L2_STANDARD,
        3: ExtractionLevelCode.L3_DEEP,
        4: ExtractionLevelCode.L4_FORENSIC,
    }

    REVERSE_LEVEL_MAPPING = {v: k for k, v in LEVEL_MAPPING.items()}

    def __init__(self, schema_version: str = "1.0", vocab_version: str = "1.0"):
        """Initialize the orchestrator.

        Args:
            schema_version: Current schema version for extraction output
            vocab_version: Current vocabulary version
        """
        self.schema_version = schema_version
        self.vocab_version = vocab_version

    async def plan_extraction(
        self,
        session: AsyncSession,
        version_id: uuid.UUID,
        profile_code: str | None = None,
        process_context: str | None = None,
        level: int | None = None,
        compute_mode: str | None = None,
        triggered_by: str | None = None,
    ) -> ExtractionPlan:
        """Plan extraction operations for a document version.

        If no parameters are provided, uses effective settings from project/document
        configuration. Returns a plan that can be executed by the worker.

        Args:
            session: Database session
            version_id: Document version to extract
            profile_code: Override profile (uses effective settings if None)
            process_context: Override process context (uses effective settings if None)
            level: Override target level (uses effective settings if None)
            compute_mode: Override compute mode (uses effective settings if None)
            triggered_by: User/system that triggered the extraction

        Returns:
            ExtractionPlan with list of jobs to execute
        """
        # Get effective settings
        effective = await self._get_effective_settings(session, version_id)

        # Apply overrides
        final_profile = profile_code or effective["profile_code"]
        final_context = process_context or effective["process_context"]
        final_level = level or effective["level"]
        final_mode = compute_mode or effective["compute_mode"]

        # Parse process context
        try:
            process_ctx = ProcessContext(final_context)
        except ValueError:
            process_ctx = ProcessContext.UNSPECIFIED

        # Get profile and level records
        profile = await self._get_profile(session, final_profile)
        level_record = await self._get_level(session, final_level)

        if not profile or not level_record:
            raise ValueError(f"Invalid profile or level: {final_profile}, {final_level}")

        # Determine which levels need to be computed
        levels_to_compute = self._determine_levels_to_compute(
            final_level, final_mode
        )

        # Check existing runs for each level
        existing_runs: dict[int, uuid.UUID] = {}
        skipped_levels: list[int] = []
        jobs: list[ExtractionJob] = []

        for lvl in levels_to_compute:
            lvl_code = self.LEVEL_MAPPING.get(lvl)
            if not lvl_code:
                continue

            lvl_record = await self._get_level(session, lvl)
            if not lvl_record:
                continue

            # Check for completed run at this level
            existing = await self._get_completed_run(
                session, version_id, profile.id, process_ctx, lvl_record.id
            )

            if existing:
                existing_runs[lvl] = existing.id
                skipped_levels.append(lvl)
                logger.debug(
                    f"Skipping level {lvl} - already completed (run_id={existing.id})"
                )
                continue

            # Check for active run (queued/running)
            active = await self._get_active_run(
                session, version_id, profile.id, process_ctx, lvl_record.id
            )

            if active:
                existing_runs[lvl] = active.id
                skipped_levels.append(lvl)
                logger.debug(
                    f"Skipping level {lvl} - already active (run_id={active.id})"
                )
                continue

            # Need to create job for this level
            parent_run_id = existing_runs.get(lvl - 1) if lvl > 1 else None

            jobs.append(
                ExtractionJob(
                    version_id=version_id,
                    profile_code=final_profile,
                    process_context=final_context,
                    level=lvl,
                    level_code=lvl_code,
                    triggered_by=triggered_by,
                    parent_run_id=parent_run_id,
                    schema_version=self.schema_version,
                    vocab_version=self.vocab_version,
                )
            )

        return ExtractionPlan(
            version_id=version_id,
            profile_code=final_profile,
            process_context=final_context,
            target_level=final_level,
            compute_mode=final_mode,
            jobs=jobs,
            skipped_levels=skipped_levels,
            existing_runs=existing_runs,
            is_empty=len(jobs) == 0,
        )

    async def create_extraction_run(
        self,
        session: AsyncSession,
        job: ExtractionJob,
    ) -> FactExtractionRun:
        """Create an extraction run record from a job specification.

        Args:
            session: Database session
            job: Job specification from plan

        Returns:
            Created ExtractionRun record
        """
        # Get profile and level records
        profile = await self._get_profile(session, job.profile_code)
        level_record = await self._get_level(session, job.level)

        if not profile or not level_record:
            raise ValueError(f"Invalid profile or level: {job.profile_code}, {job.level}")

        # Get document info
        version = await session.get(DocumentVersion, job.version_id)
        if not version:
            raise ValueError(f"Document version {job.version_id} not found")

        # Parse process context
        try:
            process_ctx = ProcessContext(job.process_context)
        except ValueError:
            process_ctx = ProcessContext.UNSPECIFIED

        # Create run record
        run = FactExtractionRun(
            document_id=version.document_id,
            version_id=job.version_id,
            profile_id=profile.id,
            process_context=process_ctx,
            level_id=level_record.id,
            status=ExtractionRunStatus.QUEUED,
            triggered_by=job.triggered_by,
            parent_run_id=job.parent_run_id,
            schema_version=job.schema_version,
            vocab_version=job.vocab_version,
        )
        session.add(run)
        await session.flush()

        return run

    def compose_prompts(
        self,
        profile_code: str,
        process_context: str,
        level: int,
        document_text: str,
        previous_extraction: dict[str, Any] | None = None,
    ) -> PromptComposition:
        """Compose extraction prompts from multiple overlays.

        Implements programmatic prompt composition:
        FINAL_PROMPT = BASE_PROMPT + PROFILE_OVERLAY + PROCESS_CONTEXT_OVERLAY + LOD_OVERLAY

        Args:
            profile_code: Extraction profile (vc, pharma, insurance, general)
            process_context: Business process context
            level: Extraction level (1-4)
            document_text: Document text to extract from
            previous_extraction: Results from previous level (for incremental)

        Returns:
            PromptComposition with all components and final prompts
        """
        from evidence_repository.extraction.multilevel.prompts import (
            build_system_prompt,
            build_user_prompt,
        )
        from evidence_repository.extraction.vocabularies import get_vocabulary

        # Get vocabulary for profile
        vocabulary = get_vocabulary(profile_code)
        vocab_context = vocabulary.get_extraction_prompt_context(level)

        # Base prompt (core extraction instructions)
        base_prompt = self._get_base_prompt()

        # Profile overlay (domain-specific terminology and focus areas)
        profile_overlay = self._get_profile_overlay(profile_code, vocab_context)

        # Process context overlay (business process specific guidance)
        process_context_overlay = self._get_process_context_overlay(process_context)

        # Level of detail overlay (what to extract at this level)
        lod_overlay = self._get_lod_overlay(level)

        # Build final system prompt using existing infrastructure
        final_system_prompt = build_system_prompt(vocab_context, level)

        # Build user prompt
        final_user_prompt = build_user_prompt(
            document_text,
            spans=None,
            previous_extraction=previous_extraction,
        )

        return PromptComposition(
            base_prompt=base_prompt,
            profile_overlay=profile_overlay,
            process_context_overlay=process_context_overlay,
            lod_overlay=lod_overlay,
            vocabulary_terms=vocab_context,
            final_system_prompt=final_system_prompt,
            final_user_prompt=final_user_prompt,
        )

    # =========================================================================
    # Private Helper Methods
    # =========================================================================

    async def _get_effective_settings(
        self, session: AsyncSession, version_id: uuid.UUID
    ) -> dict[str, Any]:
        """Get effective extraction settings for a document version.

        Resolution order:
        1. Document-version specific override (highest priority)
        2. Project default
        3. System default
        """
        # Get document version
        version = await session.get(DocumentVersion, version_id)
        if not version:
            raise ValueError(f"Document version {version_id} not found")

        # Find project for this document
        project_doc_stmt = select(ProjectDocument).where(
            ProjectDocument.document_id == version.document_id
        )
        project_doc_result = await session.execute(project_doc_stmt)
        project_doc = project_doc_result.scalar_one_or_none()
        project_id = project_doc.project_id if project_doc else None

        # Check for document-version specific setting
        doc_setting = await self._get_setting(
            session, ScopeType.DOCUMENT_VERSION, version_id
        )
        if doc_setting:
            return {
                "profile_code": doc_setting.profile.code.value,
                "process_context": "unspecified",  # Will be stored in setting
                "level": doc_setting.level.rank,
                "compute_mode": doc_setting.compute_mode.value,
                "source": "document_version",
            }

        # Check for project default
        if project_id:
            project_setting = await self._get_setting(
                session, ScopeType.PROJECT, project_id
            )
            if project_setting:
                return {
                    "profile_code": project_setting.profile.code.value,
                    "process_context": "unspecified",
                    "level": project_setting.level.rank,
                    "compute_mode": project_setting.compute_mode.value,
                    "source": "project",
                }

        # System default
        return {
            "profile_code": "general",
            "process_context": "unspecified",
            "level": 2,
            "compute_mode": "exact_only",
            "source": "default",
        }

    async def _get_setting(
        self, session: AsyncSession, scope_type: ScopeType, scope_id: uuid.UUID
    ) -> ExtractionSetting | None:
        """Get extraction setting for a scope."""
        stmt = (
            select(ExtractionSetting)
            .where(
                ExtractionSetting.scope_type == scope_type,
                ExtractionSetting.scope_id == scope_id,
            )
            .options(
                selectinload(ExtractionSetting.profile),
                selectinload(ExtractionSetting.level),
            )
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_profile(
        self, session: AsyncSession, profile_code: str
    ) -> ExtractionProfile | None:
        """Get extraction profile by code."""
        try:
            code_enum = ExtractionProfileCode(profile_code)
        except ValueError:
            code_enum = ExtractionProfileCode.GENERAL

        stmt = select(ExtractionProfile).where(ExtractionProfile.code == code_enum)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_level(
        self, session: AsyncSession, level: int
    ) -> ExtractionLevel | None:
        """Get extraction level by rank."""
        level_code = self.LEVEL_MAPPING.get(level)
        if not level_code:
            return None

        stmt = select(ExtractionLevel).where(ExtractionLevel.code == level_code)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_completed_run(
        self,
        session: AsyncSession,
        version_id: uuid.UUID,
        profile_id: uuid.UUID,
        process_context: ProcessContext,
        level_id: uuid.UUID,
    ) -> FactExtractionRun | None:
        """Get completed extraction run for given parameters."""
        stmt = (
            select(FactExtractionRun)
            .where(
                FactExtractionRun.version_id == version_id,
                FactExtractionRun.profile_id == profile_id,
                FactExtractionRun.process_context == process_context,
                FactExtractionRun.level_id == level_id,
                FactExtractionRun.status == ExtractionRunStatus.SUCCEEDED,
            )
            .order_by(FactExtractionRun.finished_at.desc())
            .limit(1)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_active_run(
        self,
        session: AsyncSession,
        version_id: uuid.UUID,
        profile_id: uuid.UUID,
        process_context: ProcessContext,
        level_id: uuid.UUID,
    ) -> FactExtractionRun | None:
        """Get active (queued/running) extraction run for given parameters."""
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

    def _determine_levels_to_compute(
        self, target_level: int, compute_mode: str
    ) -> list[int]:
        """Determine which levels need to be computed.

        Args:
            target_level: Target extraction level (1-4)
            compute_mode: exact_only or all_up_to

        Returns:
            List of level numbers to compute, in order
        """
        if compute_mode == "all_up_to":
            return list(range(1, target_level + 1))
        else:  # exact_only
            return [target_level]

    def _get_base_prompt(self) -> str:
        """Get base extraction prompt (core instructions)."""
        return """You are an expert document analyst performing structured fact extraction.
Your task is to extract claims, metrics, constraints, and risks from the document.
All extractions must include evidence quotes and span references for traceability."""

    def _get_profile_overlay(
        self, profile_code: str, vocab_context: dict[str, Any]
    ) -> str:
        """Get profile-specific prompt overlay."""
        overlays = {
            "vc": """Focus on startup and investment due diligence facts:
- Funding rounds, valuation, cap table
- Revenue metrics, growth rates, burn rate
- Market size, competitive positioning
- Team composition, key hires""",
            "pharma": """Focus on pharmaceutical and clinical facts:
- Clinical trial results, phases, endpoints
- Regulatory approvals, FDA interactions
- Safety data, adverse events
- Patent status, exclusivity periods""",
            "insurance": """Focus on insurance and risk assessment facts:
- Coverage terms, limits, deductibles
- Claims history, loss ratios
- Underwriting criteria, risk factors
- Regulatory compliance status""",
            "general": """Focus on general business and financial facts:
- Revenue, profitability, cash flow
- Business model, key partnerships
- Risk factors, material issues
- Compliance and regulatory matters""",
        }
        return overlays.get(profile_code, overlays["general"])

    def _get_process_context_overlay(self, process_context: str) -> str:
        """Get process context specific prompt overlay."""
        overlays = {
            "vc.ic_decision": """This extraction is for an Investment Committee decision.
Prioritize: deal terms, valuation justification, key risks, competitive advantage.""",
            "vc.due_diligence": """This extraction is for due diligence analysis.
Be thorough: verify all claims, identify inconsistencies, flag missing data.""",
            "vc.portfolio_review": """This extraction is for portfolio monitoring.
Focus on: performance vs projections, updated metrics, emerging risks.""",
            "pharma.clinical_trial": """This extraction is for clinical trial analysis.
Focus on: efficacy endpoints, safety signals, patient demographics, protocol deviations.""",
            "pharma.regulatory": """This extraction is for regulatory submission.
Ensure: completeness, accuracy, all required data points captured.""",
            "insurance.underwriting": """This extraction is for underwriting decision.
Prioritize: risk factors, coverage needs, claims history, pricing inputs.""",
            "unspecified": """Perform general-purpose extraction with balanced coverage.""",
        }
        return overlays.get(process_context, overlays["unspecified"])

    def _get_lod_overlay(self, level: int) -> str:
        """Get level of detail prompt overlay."""
        overlays = {
            1: """L1 BASIC: Extract only key headline metrics and essential claims.
- Maximum 10 metrics, 15 claims
- Focus on most material facts only
- Skip detailed breakdowns and minor items""",
            2: """L2 STANDARD: Comprehensive extraction of all material facts.
- All significant metrics and claims
- Include compliance and risk items
- Extract definitions and constraints""",
            3: """L3 DEEP: Detailed extraction with entity resolution.
- All metrics including time-series data
- Resolve entities across document
- Extract table data systematically
- Include quality conflicts and questions""",
            4: """L4 FORENSIC: Maximum extraction for legal/audit use.
- Every extractable fact
- Full cross-reference and reconciliation
- Flag any inconsistencies or gaps
- Include methodology and assumptions""",
        }
        return overlays.get(level, overlays[2])
