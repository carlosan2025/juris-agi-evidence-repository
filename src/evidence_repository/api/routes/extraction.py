"""API routes for multi-level extraction configuration and execution."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from evidence_repository.api.dependencies import get_db
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
from evidence_repository.models.facts import (
    FactClaim,
    FactMetric,
    FactConstraint,
    FactRisk,
)
from evidence_repository.models.quality import QualityConflict, QualityOpenQuestion

router = APIRouter(prefix="/extraction", tags=["extraction"])


# =============================================================================
# Pydantic Schemas
# =============================================================================


class ExtractionProfileResponse(BaseModel):
    """Extraction profile response."""

    id: uuid.UUID
    name: str
    code: str
    description: str | None
    is_active: bool

    class Config:
        from_attributes = True


class ExtractionLevelResponse(BaseModel):
    """Extraction level response."""

    id: uuid.UUID
    code: str
    rank: int
    name: str
    description: str | None
    is_active: bool

    class Config:
        from_attributes = True


class ExtractionSettingCreate(BaseModel):
    """Create extraction setting request."""

    scope_type: str = Field(..., description="project or document_version")
    scope_id: uuid.UUID
    profile_code: str = Field("general", description="Profile code")
    process_context: str = Field("unspecified", description="Process context (e.g., vc.ic_decision)")
    level: int = Field(2, ge=1, le=4, description="Extraction level 1-4")
    compute_mode: str = Field("exact_only", description="exact_only or all_up_to")
    is_enabled: bool = True


class ExtractionSettingResponse(BaseModel):
    """Extraction setting response."""

    id: uuid.UUID
    scope_type: str
    scope_id: uuid.UUID
    profile_id: uuid.UUID
    profile_code: str
    process_context: str
    level_id: uuid.UUID
    level_rank: int
    compute_mode: str
    is_enabled: bool

    class Config:
        from_attributes = True


class EffectiveExtractionSettingResponse(BaseModel):
    """Effective extraction setting (resolved from project + document overrides)."""

    profile_code: str
    process_context: str
    level_rank: int
    compute_mode: str
    is_enabled: bool
    source: str = Field(..., description="Where this setting came from: project, document_version, or default")
    project_setting_id: uuid.UUID | None = None
    document_setting_id: uuid.UUID | None = None


class ExtractionRunResponse(BaseModel):
    """Extraction run response."""

    id: uuid.UUID
    document_id: uuid.UUID
    version_id: uuid.UUID
    profile_code: str
    process_context: str
    level_rank: int
    status: str
    schema_version: str
    vocab_version: str
    started_at: str | None
    finished_at: str | None
    error: str | None
    metadata: dict

    class Config:
        from_attributes = True


class TriggerExtractionRequest(BaseModel):
    """Trigger extraction request."""

    version_id: uuid.UUID
    profile_code: str = Field("general")
    process_context: str = Field("unspecified", description="Process context (e.g., vc.ic_decision)")
    level: int = Field(2, ge=1, le=4)
    compute_missing_levels: bool = Field(
        False, description="Compute all missing levels up to requested"
    )


class ExtractionResultsResponse(BaseModel):
    """Extraction results summary."""

    run_id: uuid.UUID
    profile_code: str
    process_context: str
    level: int
    claims_count: int
    metrics_count: int
    constraints_count: int
    risks_count: int
    conflicts_count: int
    questions_count: int


class FactClaimResponse(BaseModel):
    """Fact claim response."""

    id: uuid.UUID
    subject: dict
    predicate: str
    object: dict
    claim_type: str
    time_scope: dict | None
    certainty: str
    source_reliability: str
    extraction_confidence: float | None
    evidence_quote: str | None
    span_refs: list

    class Config:
        from_attributes = True


class FactMetricResponse(BaseModel):
    """Fact metric response."""

    id: uuid.UUID
    entity_id: str | None
    entity_type: str | None
    metric_name: str
    metric_category: str | None
    value_numeric: float | None
    value_raw: str | None
    unit: str | None
    currency: str | None
    period_type: str | None
    certainty: str
    source_reliability: str
    extraction_confidence: float | None
    quality_flags: list | None
    evidence_quote: str | None
    span_refs: list

    class Config:
        from_attributes = True


# =============================================================================
# Profile and Level Endpoints
# =============================================================================


@router.get("/profiles", response_model=list[ExtractionProfileResponse])
async def list_profiles(
    db: Annotated[AsyncSession, Depends(get_db)],
    active_only: bool = Query(True),
):
    """List available extraction profiles."""
    stmt = select(ExtractionProfile)
    if active_only:
        stmt = stmt.where(ExtractionProfile.is_active == True)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/levels", response_model=list[ExtractionLevelResponse])
async def list_levels(
    db: Annotated[AsyncSession, Depends(get_db)],
    active_only: bool = Query(True),
):
    """List available extraction levels."""
    stmt = select(ExtractionLevel).order_by(ExtractionLevel.rank)
    if active_only:
        stmt = stmt.where(ExtractionLevel.is_active == True)
    result = await db.execute(stmt)
    return result.scalars().all()


# =============================================================================
# Extraction Settings Endpoints
# =============================================================================


@router.post("/settings", response_model=ExtractionSettingResponse)
async def create_or_update_setting(
    request: ExtractionSettingCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Create or update extraction settings for a scope."""
    # Validate scope type
    try:
        scope_type = ScopeType(request.scope_type)
    except ValueError:
        raise HTTPException(400, f"Invalid scope_type: {request.scope_type}")

    # Get or create profile
    try:
        profile_code = ExtractionProfileCode(request.profile_code)
    except ValueError:
        profile_code = ExtractionProfileCode.GENERAL

    profile_stmt = select(ExtractionProfile).where(ExtractionProfile.code == profile_code)
    profile_result = await db.execute(profile_stmt)
    profile = profile_result.scalar_one_or_none()

    if not profile:
        from evidence_repository.extraction.vocabularies import get_vocabulary

        vocabulary = get_vocabulary(request.profile_code)
        profile = ExtractionProfile(
            name=vocabulary.profile_name,
            code=profile_code,
            description=f"Profile for {vocabulary.profile_name}",
            is_active=True,
        )
        db.add(profile)
        await db.flush()

    # Get or create level
    level_mapping = {
        1: ExtractionLevelCode.L1_BASIC,
        2: ExtractionLevelCode.L2_STANDARD,
        3: ExtractionLevelCode.L3_DEEP,
        4: ExtractionLevelCode.L4_FORENSIC,
    }
    level_code = level_mapping.get(request.level, ExtractionLevelCode.L2_STANDARD)

    level_stmt = select(ExtractionLevel).where(ExtractionLevel.code == level_code)
    level_result = await db.execute(level_stmt)
    level = level_result.scalar_one_or_none()

    if not level:
        level_names = {1: "Basic", 2: "Standard", 3: "Deep", 4: "Forensic"}
        level = ExtractionLevel(
            code=level_code,
            rank=request.level,
            name=level_names.get(request.level, "Standard"),
            is_active=True,
        )
        db.add(level)
        await db.flush()

    # Check for existing setting
    existing_stmt = select(ExtractionSetting).where(
        ExtractionSetting.scope_type == scope_type,
        ExtractionSetting.scope_id == request.scope_id,
    )
    existing_result = await db.execute(existing_stmt)
    setting = existing_result.scalar_one_or_none()

    compute_mode = (
        ComputeMode.ALL_UP_TO
        if request.compute_mode == "all_up_to"
        else ComputeMode.EXACT_ONLY
    )

    if setting:
        # Update existing
        setting.profile_id = profile.id
        setting.level_id = level.id
        setting.compute_mode = compute_mode
        setting.is_enabled = request.is_enabled
    else:
        # Create new
        setting = ExtractionSetting(
            scope_type=scope_type,
            scope_id=request.scope_id,
            profile_id=profile.id,
            level_id=level.id,
            compute_mode=compute_mode,
            is_enabled=request.is_enabled,
        )
        db.add(setting)

    await db.commit()
    await db.refresh(setting)

    return ExtractionSettingResponse(
        id=setting.id,
        scope_type=setting.scope_type.value,
        scope_id=setting.scope_id,
        profile_id=profile.id,
        profile_code=profile.code.value,
        level_id=level.id,
        level_rank=level.rank,
        compute_mode=setting.compute_mode.value,
        is_enabled=setting.is_enabled,
    )


@router.get("/settings/{scope_type}/{scope_id}", response_model=ExtractionSettingResponse)
async def get_setting(
    scope_type: str,
    scope_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get extraction settings for a scope."""
    try:
        st = ScopeType(scope_type)
    except ValueError:
        raise HTTPException(400, f"Invalid scope_type: {scope_type}")

    stmt = (
        select(ExtractionSetting)
        .where(
            ExtractionSetting.scope_type == st,
            ExtractionSetting.scope_id == scope_id,
        )
        .options(
            selectinload(ExtractionSetting.profile),
            selectinload(ExtractionSetting.level),
        )
    )
    result = await db.execute(stmt)
    setting = result.scalar_one_or_none()

    if not setting:
        raise HTTPException(404, "Setting not found")

    return ExtractionSettingResponse(
        id=setting.id,
        scope_type=setting.scope_type.value,
        scope_id=setting.scope_id,
        profile_id=setting.profile_id,
        profile_code=setting.profile.code.value,
        process_context="unspecified",  # TODO: Add process_context to ExtractionSetting model
        level_id=setting.level_id,
        level_rank=setting.level.rank,
        compute_mode=setting.compute_mode.value,
        is_enabled=setting.is_enabled,
    )


@router.get(
    "/settings/effective/{version_id}",
    response_model=EffectiveExtractionSettingResponse,
)
async def get_effective_setting(
    version_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get effective extraction settings for a document version.

    Resolves settings by checking:
    1. Document-version specific override (highest priority)
    2. Project default
    3. System default (general profile, L2_STANDARD, exact_only)
    """
    # Get the document version to find its project
    version = await db.get(DocumentVersion, version_id)
    if not version:
        raise HTTPException(404, f"Version {version_id} not found")

    # Import here to avoid circular imports
    from evidence_repository.models.project import ProjectDocument

    # Find the project for this document
    project_doc_stmt = select(ProjectDocument).where(
        ProjectDocument.document_id == version.document_id
    )
    project_doc_result = await db.execute(project_doc_stmt)
    project_doc = project_doc_result.scalar_one_or_none()

    project_id = project_doc.project_id if project_doc else None

    # Check for document-version specific setting
    doc_setting_stmt = (
        select(ExtractionSetting)
        .where(
            ExtractionSetting.scope_type == ScopeType.DOCUMENT_VERSION,
            ExtractionSetting.scope_id == version_id,
        )
        .options(
            selectinload(ExtractionSetting.profile),
            selectinload(ExtractionSetting.level),
        )
    )
    doc_setting_result = await db.execute(doc_setting_stmt)
    doc_setting = doc_setting_result.scalar_one_or_none()

    if doc_setting:
        return EffectiveExtractionSettingResponse(
            profile_code=doc_setting.profile.code.value,
            process_context="unspecified",  # Will be stored in setting
            level_rank=doc_setting.level.rank,
            compute_mode=doc_setting.compute_mode.value,
            is_enabled=doc_setting.is_enabled,
            source="document_version",
            document_setting_id=doc_setting.id,
        )

    # Check for project default setting
    if project_id:
        project_setting_stmt = (
            select(ExtractionSetting)
            .where(
                ExtractionSetting.scope_type == ScopeType.PROJECT,
                ExtractionSetting.scope_id == project_id,
            )
            .options(
                selectinload(ExtractionSetting.profile),
                selectinload(ExtractionSetting.level),
            )
        )
        project_setting_result = await db.execute(project_setting_stmt)
        project_setting = project_setting_result.scalar_one_or_none()

        if project_setting:
            return EffectiveExtractionSettingResponse(
                profile_code=project_setting.profile.code.value,
                process_context="unspecified",
                level_rank=project_setting.level.rank,
                compute_mode=project_setting.compute_mode.value,
                is_enabled=project_setting.is_enabled,
                source="project",
                project_setting_id=project_setting.id,
            )

    # Return system default
    return EffectiveExtractionSettingResponse(
        profile_code="general",
        process_context="unspecified",
        level_rank=2,
        compute_mode="exact_only",
        is_enabled=True,
        source="default",
    )


# =============================================================================
# Extraction Execution Endpoints
# =============================================================================


@router.post("/trigger", response_model=ExtractionRunResponse)
async def trigger_extraction(
    request: TriggerExtractionRequest,
    background_tasks: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Trigger extraction for a document version.

    If compute_missing_levels is True, all levels up to the requested
    level will be computed if they don't exist.
    """
    # Validate version exists
    version = await db.get(DocumentVersion, request.version_id)
    if not version:
        raise HTTPException(404, f"Version {request.version_id} not found")

    # Get or create profile and level
    from evidence_repository.extraction.multilevel import MultiLevelExtractionService

    service = MultiLevelExtractionService()
    profile = await service._get_or_create_profile(db, request.profile_code)
    level = await service._get_or_create_level(db, request.level)

    # Validate and parse process_context
    try:
        process_ctx = ProcessContext(request.process_context)
    except ValueError:
        process_ctx = ProcessContext.UNSPECIFIED

    # Check for existing active run (now includes process_context)
    existing_stmt = select(FactExtractionRun).where(
        FactExtractionRun.version_id == request.version_id,
        FactExtractionRun.profile_id == profile.id,
        FactExtractionRun.process_context == process_ctx,
        FactExtractionRun.level_id == level.id,
        FactExtractionRun.status.in_([ExtractionRunStatus.QUEUED, ExtractionRunStatus.RUNNING]),
    )
    existing_result = await db.execute(existing_stmt)
    existing = existing_result.scalar_one_or_none()

    if existing:
        return ExtractionRunResponse(
            id=existing.id,
            document_id=existing.document_id,
            version_id=existing.version_id,
            profile_code=profile.code.value,
            process_context=existing.process_context.value,
            level_rank=level.rank,
            status=existing.status.value,
            schema_version=existing.schema_version,
            vocab_version=existing.vocab_version,
            started_at=existing.started_at.isoformat() if existing.started_at else None,
            finished_at=existing.finished_at.isoformat() if existing.finished_at else None,
            error=existing.error,
            metadata=existing.metadata_ or {},
        )

    # Create new run record
    run = FactExtractionRun(
        document_id=version.document_id,
        version_id=request.version_id,
        profile_id=profile.id,
        process_context=process_ctx,
        level_id=level.id,
        status=ExtractionRunStatus.QUEUED,
        schema_version="1.0",
        vocab_version="1.0",
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    # Queue background task
    from evidence_repository.queue.tasks import task_multilevel_extract

    background_tasks.add_task(
        task_multilevel_extract,
        version_id=str(request.version_id),
        profile_code=request.profile_code,
        process_context=request.process_context,
        level=request.level,
        compute_missing_levels=request.compute_missing_levels,
    )

    return ExtractionRunResponse(
        id=run.id,
        document_id=run.document_id,
        version_id=run.version_id,
        profile_code=profile.code.value,
        process_context=run.process_context.value,
        level_rank=level.rank,
        status=run.status.value,
        schema_version=run.schema_version,
        vocab_version=run.vocab_version,
        started_at=None,
        finished_at=None,
        error=None,
        metadata={},
    )


@router.get("/runs/{version_id}", response_model=list[ExtractionRunResponse])
async def list_runs(
    version_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    profile_code: str | None = Query(None),
    level: int | None = Query(None, ge=1, le=4),
    status: str | None = Query(None),
):
    """List extraction runs for a document version."""
    stmt = (
        select(FactExtractionRun)
        .where(FactExtractionRun.version_id == version_id)
        .options(
            selectinload(FactExtractionRun.profile),
            selectinload(FactExtractionRun.level),
        )
        .order_by(FactExtractionRun.created_at.desc())
    )

    if profile_code:
        try:
            pc = ExtractionProfileCode(profile_code)
            profile_stmt = select(ExtractionProfile.id).where(ExtractionProfile.code == pc)
            profile_result = await db.execute(profile_stmt)
            profile_id = profile_result.scalar_one_or_none()
            if profile_id:
                stmt = stmt.where(FactExtractionRun.profile_id == profile_id)
        except ValueError:
            pass

    if level:
        level_mapping = {
            1: ExtractionLevelCode.L1_BASIC,
            2: ExtractionLevelCode.L2_STANDARD,
            3: ExtractionLevelCode.L3_DEEP,
            4: ExtractionLevelCode.L4_FORENSIC,
        }
        level_code = level_mapping.get(level)
        if level_code:
            level_stmt = select(ExtractionLevel.id).where(ExtractionLevel.code == level_code)
            level_result = await db.execute(level_stmt)
            level_id = level_result.scalar_one_or_none()
            if level_id:
                stmt = stmt.where(FactExtractionRun.level_id == level_id)

    if status:
        try:
            st = ExtractionRunStatus(status)
            stmt = stmt.where(FactExtractionRun.status == st)
        except ValueError:
            pass

    result = await db.execute(stmt)
    runs = result.scalars().all()

    return [
        ExtractionRunResponse(
            id=run.id,
            document_id=run.document_id,
            version_id=run.version_id,
            profile_code=run.profile.code.value,
            process_context=run.process_context.value if run.process_context else "unspecified",
            level_rank=run.level.rank,
            status=run.status.value,
            schema_version=run.schema_version if hasattr(run, 'schema_version') and run.schema_version else "1.0",
            vocab_version=run.vocab_version if hasattr(run, 'vocab_version') and run.vocab_version else "1.0",
            started_at=run.started_at.isoformat() if run.started_at else None,
            finished_at=run.finished_at.isoformat() if run.finished_at else None,
            error=run.error,
            metadata=run.metadata_ or {},
        )
        for run in runs
    ]


@router.get("/runs/{version_id}/results", response_model=ExtractionResultsResponse)
async def get_run_results(
    version_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    profile_code: str = Query("general"),
    process_context: str = Query("unspecified"),
    level: int = Query(2, ge=1, le=4),
):
    """Get extraction results summary for a specific profile/process_context/level."""
    # Get profile and level
    try:
        pc = ExtractionProfileCode(profile_code)
    except ValueError:
        pc = ExtractionProfileCode.GENERAL

    profile_stmt = select(ExtractionProfile).where(ExtractionProfile.code == pc)
    profile_result = await db.execute(profile_stmt)
    profile = profile_result.scalar_one_or_none()

    if not profile:
        raise HTTPException(404, f"Profile {profile_code} not found")

    level_mapping = {
        1: ExtractionLevelCode.L1_BASIC,
        2: ExtractionLevelCode.L2_STANDARD,
        3: ExtractionLevelCode.L3_DEEP,
        4: ExtractionLevelCode.L4_FORENSIC,
    }
    level_code = level_mapping.get(level, ExtractionLevelCode.L2_STANDARD)

    level_stmt = select(ExtractionLevel).where(ExtractionLevel.code == level_code)
    level_result = await db.execute(level_stmt)
    level_record = level_result.scalar_one_or_none()

    if not level_record:
        raise HTTPException(404, f"Level {level} not found")

    # Parse process_context
    try:
        process_ctx = ProcessContext(process_context)
    except ValueError:
        process_ctx = ProcessContext.UNSPECIFIED

    # Get latest successful run
    run_stmt = (
        select(FactExtractionRun)
        .where(
            FactExtractionRun.version_id == version_id,
            FactExtractionRun.profile_id == profile.id,
            FactExtractionRun.process_context == process_ctx,
            FactExtractionRun.level_id == level_record.id,
            FactExtractionRun.status == ExtractionRunStatus.SUCCEEDED,
        )
        .order_by(FactExtractionRun.finished_at.desc())
        .limit(1)
    )
    run_result = await db.execute(run_stmt)
    run = run_result.scalar_one_or_none()

    if not run:
        raise HTTPException(404, "No completed extraction run found")

    # Count facts
    claims_count = (
        await db.execute(
            select(FactClaim.id).where(FactClaim.extraction_run_id == run.id)
        )
    ).fetchall()
    metrics_count = (
        await db.execute(
            select(FactMetric.id).where(FactMetric.extraction_run_id == run.id)
        )
    ).fetchall()
    constraints_count = (
        await db.execute(
            select(FactConstraint.id).where(FactConstraint.extraction_run_id == run.id)
        )
    ).fetchall()
    risks_count = (
        await db.execute(
            select(FactRisk.id).where(FactRisk.extraction_run_id == run.id)
        )
    ).fetchall()
    conflicts_count = (
        await db.execute(
            select(QualityConflict.id).where(QualityConflict.extraction_run_id == run.id)
        )
    ).fetchall()
    questions_count = (
        await db.execute(
            select(QualityOpenQuestion.id).where(
                QualityOpenQuestion.extraction_run_id == run.id
            )
        )
    ).fetchall()

    return ExtractionResultsResponse(
        run_id=run.id,
        profile_code=profile_code,
        process_context=process_context,
        level=level,
        claims_count=len(claims_count),
        metrics_count=len(metrics_count),
        constraints_count=len(constraints_count),
        risks_count=len(risks_count),
        conflicts_count=len(conflicts_count),
        questions_count=len(questions_count),
    )


# =============================================================================
# Facts Retrieval Endpoints
# =============================================================================


@router.get("/facts/{version_id}/claims", response_model=list[FactClaimResponse])
async def get_claims(
    version_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    profile_code: str = Query("general"),
    process_context: str = Query("unspecified"),
    level: int = Query(2, ge=1, le=4),
    claim_type: str | None = Query(None),
    predicate: str | None = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0),
):
    """Get extracted claims for a document version at specified profile/process_context/level."""
    # Get profile and level IDs
    try:
        pc = ExtractionProfileCode(profile_code)
    except ValueError:
        pc = ExtractionProfileCode.GENERAL

    profile_stmt = select(ExtractionProfile.id).where(ExtractionProfile.code == pc)
    profile_result = await db.execute(profile_stmt)
    profile_id = profile_result.scalar_one_or_none()

    if not profile_id:
        return []

    level_mapping = {
        1: ExtractionLevelCode.L1_BASIC,
        2: ExtractionLevelCode.L2_STANDARD,
        3: ExtractionLevelCode.L3_DEEP,
        4: ExtractionLevelCode.L4_FORENSIC,
    }
    level_code = level_mapping.get(level, ExtractionLevelCode.L2_STANDARD)

    level_stmt = select(ExtractionLevel.id).where(ExtractionLevel.code == level_code)
    level_result = await db.execute(level_stmt)
    level_id = level_result.scalar_one_or_none()

    if not level_id:
        return []

    # Parse process_context
    try:
        process_ctx = ProcessContext(process_context)
    except ValueError:
        process_ctx = ProcessContext.UNSPECIFIED

    # Query claims
    stmt = (
        select(FactClaim)
        .where(
            FactClaim.version_id == version_id,
            FactClaim.profile_id == profile_id,
            FactClaim.process_context == process_ctx,
            FactClaim.level_id == level_id,
        )
        .order_by(FactClaim.created_at.desc())
        .offset(offset)
        .limit(limit)
    )

    if claim_type:
        stmt = stmt.where(FactClaim.claim_type == claim_type)
    if predicate:
        stmt = stmt.where(FactClaim.predicate == predicate)

    result = await db.execute(stmt)
    claims = result.scalars().all()

    return [
        FactClaimResponse(
            id=c.id,
            subject=c.subject,
            predicate=c.predicate,
            object=c.object,
            claim_type=c.claim_type,
            time_scope=c.time_scope,
            certainty=c.certainty.value,
            source_reliability=c.source_reliability.value,
            extraction_confidence=c.extraction_confidence,
            evidence_quote=c.evidence_quote,
            span_refs=c.span_refs or [],
        )
        for c in claims
    ]


@router.get("/facts/{version_id}/metrics", response_model=list[FactMetricResponse])
async def get_metrics(
    version_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    profile_code: str = Query("general"),
    process_context: str = Query("unspecified"),
    level: int = Query(2, ge=1, le=4),
    metric_name: str | None = Query(None),
    metric_category: str | None = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0),
):
    """Get extracted metrics for a document version at specified profile/process_context/level."""
    # Get profile and level IDs
    try:
        pc = ExtractionProfileCode(profile_code)
    except ValueError:
        pc = ExtractionProfileCode.GENERAL

    profile_stmt = select(ExtractionProfile.id).where(ExtractionProfile.code == pc)
    profile_result = await db.execute(profile_stmt)
    profile_id = profile_result.scalar_one_or_none()

    if not profile_id:
        return []

    level_mapping = {
        1: ExtractionLevelCode.L1_BASIC,
        2: ExtractionLevelCode.L2_STANDARD,
        3: ExtractionLevelCode.L3_DEEP,
        4: ExtractionLevelCode.L4_FORENSIC,
    }
    level_code = level_mapping.get(level, ExtractionLevelCode.L2_STANDARD)

    level_stmt = select(ExtractionLevel.id).where(ExtractionLevel.code == level_code)
    level_result = await db.execute(level_stmt)
    level_id = level_result.scalar_one_or_none()

    if not level_id:
        return []

    # Parse process_context
    try:
        process_ctx = ProcessContext(process_context)
    except ValueError:
        process_ctx = ProcessContext.UNSPECIFIED

    # Query metrics
    stmt = (
        select(FactMetric)
        .where(
            FactMetric.version_id == version_id,
            FactMetric.profile_id == profile_id,
            FactMetric.process_context == process_ctx,
            FactMetric.level_id == level_id,
        )
        .order_by(FactMetric.created_at.desc())
        .offset(offset)
        .limit(limit)
    )

    if metric_name:
        stmt = stmt.where(FactMetric.metric_name == metric_name)
    if metric_category:
        stmt = stmt.where(FactMetric.metric_category == metric_category)

    result = await db.execute(stmt)
    metrics = result.scalars().all()

    return [
        FactMetricResponse(
            id=m.id,
            entity_id=m.entity_id,
            entity_type=m.entity_type,
            metric_name=m.metric_name,
            metric_category=m.metric_category,
            value_numeric=m.value_numeric,
            value_raw=m.value_raw,
            unit=m.unit,
            currency=m.currency,
            period_type=m.period_type,
            certainty=m.certainty.value,
            source_reliability=m.source_reliability.value,
            extraction_confidence=m.extraction_confidence,
            quality_flags=m.quality_flags,
            evidence_quote=m.evidence_quote,
            span_refs=m.span_refs or [],
        )
        for m in metrics
    ]
