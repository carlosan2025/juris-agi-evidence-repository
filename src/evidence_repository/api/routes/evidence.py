"""Evidence endpoints (Spans, Claims, Metrics, Evidence Packs)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from evidence_repository.api.dependencies import User, get_current_user
from evidence_repository.db.session import get_db_session
from evidence_repository.models.document import DocumentVersion
from evidence_repository.models.evidence import (
    Claim,
    EvidencePack,
    EvidencePackItem,
    Metric,
    Span,
    SpanType,
)
from evidence_repository.models.project import Project
from evidence_repository.schemas.evidence import (
    ClaimCreate,
    ClaimResponse,
    EvidencePackCreate,
    EvidencePackItemCreate,
    EvidencePackItemResponse,
    EvidencePackResponse,
    MetricCreate,
    MetricResponse,
    SpanCreate,
    SpanResponse,
)

router = APIRouter()


# =============================================================================
# Spans
# =============================================================================


@router.post(
    "/spans",
    response_model=SpanResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Span",
    description="Create an evidence span pointing to a document location.",
)
async def create_span(
    span_in: SpanCreate,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> SpanResponse:
    """Create an evidence span."""
    # Verify document version exists
    version_result = await db.execute(
        select(DocumentVersion).where(DocumentVersion.id == span_in.document_version_id)
    )
    if not version_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document version {span_in.document_version_id} not found",
        )

    span = Span(
        document_version_id=span_in.document_version_id,
        start_locator=span_in.start_locator,
        end_locator=span_in.end_locator,
        text_content=span_in.text_content,
        span_type=SpanType(span_in.span_type),
        metadata_=span_in.metadata,
    )
    db.add(span)
    await db.commit()
    await db.refresh(span)

    return SpanResponse.model_validate(span)


@router.get(
    "/spans/{span_id}",
    response_model=SpanResponse,
    summary="Get Span",
    description="Get span details by ID.",
)
async def get_span(
    span_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> SpanResponse:
    """Get a span by ID."""
    result = await db.execute(select(Span).where(Span.id == span_id))
    span = result.scalar_one_or_none()

    if not span:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Span {span_id} not found",
        )

    return SpanResponse.model_validate(span)


@router.delete(
    "/spans/{span_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Span",
    description="Delete a span (cascades to claims and metrics).",
)
async def delete_span(
    span_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> None:
    """Delete a span."""
    result = await db.execute(select(Span).where(Span.id == span_id))
    span = result.scalar_one_or_none()

    if not span:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Span {span_id} not found",
        )

    await db.delete(span)
    await db.commit()


# =============================================================================
# Claims
# =============================================================================


@router.post(
    "/claims",
    response_model=ClaimResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Claim",
    description="Create a claim citing an evidence span.",
)
async def create_claim(
    claim_in: ClaimCreate,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> ClaimResponse:
    """Create a claim."""
    # Verify project exists
    project_result = await db.execute(
        select(Project).where(Project.id == claim_in.project_id)
    )
    if not project_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {claim_in.project_id} not found",
        )

    # Verify span exists
    span_result = await db.execute(select(Span).where(Span.id == claim_in.span_id))
    if not span_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Span {claim_in.span_id} not found",
        )

    claim = Claim(
        project_id=claim_in.project_id,
        span_id=claim_in.span_id,
        claim_text=claim_in.claim_text,
        claim_type=claim_in.claim_type,
        confidence=claim_in.confidence,
        metadata_=claim_in.metadata,
    )
    db.add(claim)
    await db.commit()
    await db.refresh(claim)

    # Load span for response
    await db.refresh(claim, ["span"])

    return ClaimResponse.model_validate(claim)


@router.get(
    "/claims/{claim_id}",
    response_model=ClaimResponse,
    summary="Get Claim",
    description="Get claim details by ID.",
)
async def get_claim(
    claim_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> ClaimResponse:
    """Get a claim by ID."""
    result = await db.execute(
        select(Claim).options(selectinload(Claim.span)).where(Claim.id == claim_id)
    )
    claim = result.scalar_one_or_none()

    if not claim:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Claim {claim_id} not found",
        )

    return ClaimResponse.model_validate(claim)


@router.delete(
    "/claims/{claim_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Claim",
    description="Delete a claim.",
)
async def delete_claim(
    claim_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> None:
    """Delete a claim."""
    result = await db.execute(select(Claim).where(Claim.id == claim_id))
    claim = result.scalar_one_or_none()

    if not claim:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Claim {claim_id} not found",
        )

    await db.delete(claim)
    await db.commit()


# =============================================================================
# Metrics
# =============================================================================


@router.post(
    "/metrics",
    response_model=MetricResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Metric",
    description="Create a metric citing an evidence span.",
)
async def create_metric(
    metric_in: MetricCreate,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> MetricResponse:
    """Create a metric."""
    # Verify project exists
    project_result = await db.execute(
        select(Project).where(Project.id == metric_in.project_id)
    )
    if not project_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {metric_in.project_id} not found",
        )

    # Verify span exists
    span_result = await db.execute(select(Span).where(Span.id == metric_in.span_id))
    if not span_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Span {metric_in.span_id} not found",
        )

    metric = Metric(
        project_id=metric_in.project_id,
        span_id=metric_in.span_id,
        metric_name=metric_in.metric_name,
        metric_value=metric_in.metric_value,
        unit=metric_in.unit,
        metadata_=metric_in.metadata,
    )
    db.add(metric)
    await db.commit()
    await db.refresh(metric)

    # Load span for response
    await db.refresh(metric, ["span"])

    return MetricResponse.model_validate(metric)


@router.get(
    "/metrics/{metric_id}",
    response_model=MetricResponse,
    summary="Get Metric",
    description="Get metric details by ID.",
)
async def get_metric(
    metric_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> MetricResponse:
    """Get a metric by ID."""
    result = await db.execute(
        select(Metric).options(selectinload(Metric.span)).where(Metric.id == metric_id)
    )
    metric = result.scalar_one_or_none()

    if not metric:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Metric {metric_id} not found",
        )

    return MetricResponse.model_validate(metric)


@router.delete(
    "/metrics/{metric_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Metric",
    description="Delete a metric.",
)
async def delete_metric(
    metric_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> None:
    """Delete a metric."""
    result = await db.execute(select(Metric).where(Metric.id == metric_id))
    metric = result.scalar_one_or_none()

    if not metric:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Metric {metric_id} not found",
        )

    await db.delete(metric)
    await db.commit()


# =============================================================================
# Evidence Packs
# =============================================================================


@router.post(
    "/evidence-packs",
    response_model=EvidencePackResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Evidence Pack",
    description="Create a new evidence pack for bundling evidence items.",
)
async def create_evidence_pack(
    pack_in: EvidencePackCreate,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> EvidencePackResponse:
    """Create an evidence pack."""
    # Verify project exists
    project_result = await db.execute(
        select(Project).where(Project.id == pack_in.project_id)
    )
    if not project_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {pack_in.project_id} not found",
        )

    pack = EvidencePack(
        project_id=pack_in.project_id,
        name=pack_in.name,
        description=pack_in.description,
        created_by=user.id,
        metadata_=pack_in.metadata,
    )
    db.add(pack)
    await db.commit()
    await db.refresh(pack)

    return EvidencePackResponse(
        **pack.__dict__,
        items=[],
        item_count=0,
    )


@router.get(
    "/evidence-packs/{pack_id}",
    response_model=EvidencePackResponse,
    summary="Get Evidence Pack",
    description="Get evidence pack details with items.",
)
async def get_evidence_pack(
    pack_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> EvidencePackResponse:
    """Get an evidence pack with items."""
    result = await db.execute(
        select(EvidencePack)
        .options(
            selectinload(EvidencePack.items)
            .selectinload(EvidencePackItem.span),
            selectinload(EvidencePack.items)
            .selectinload(EvidencePackItem.claim),
            selectinload(EvidencePack.items)
            .selectinload(EvidencePackItem.metric),
        )
        .where(EvidencePack.id == pack_id)
    )
    pack = result.scalar_one_or_none()

    if not pack:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evidence pack {pack_id} not found",
        )

    return EvidencePackResponse(
        id=pack.id,
        project_id=pack.project_id,
        name=pack.name,
        description=pack.description,
        created_by=pack.created_by,
        created_at=pack.created_at,
        updated_at=pack.updated_at,
        metadata_=pack.metadata_,
        items=[EvidencePackItemResponse.model_validate(item) for item in pack.items],
        item_count=len(pack.items),
    )


@router.post(
    "/evidence-packs/{pack_id}/items",
    response_model=EvidencePackItemResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add Item to Evidence Pack",
    description="Add an evidence item to a pack.",
)
async def add_evidence_pack_item(
    pack_id: uuid.UUID,
    item_in: EvidencePackItemCreate,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> EvidencePackItemResponse:
    """Add an item to an evidence pack."""
    # Verify pack exists
    pack_result = await db.execute(
        select(EvidencePack).where(EvidencePack.id == pack_id)
    )
    if not pack_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evidence pack {pack_id} not found",
        )

    # Verify span exists
    span_result = await db.execute(select(Span).where(Span.id == item_in.span_id))
    if not span_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Span {item_in.span_id} not found",
        )

    # Verify claim if provided
    if item_in.claim_id:
        claim_result = await db.execute(
            select(Claim).where(Claim.id == item_in.claim_id)
        )
        if not claim_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Claim {item_in.claim_id} not found",
            )

    # Verify metric if provided
    if item_in.metric_id:
        metric_result = await db.execute(
            select(Metric).where(Metric.id == item_in.metric_id)
        )
        if not metric_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Metric {item_in.metric_id} not found",
            )

    item = EvidencePackItem(
        evidence_pack_id=pack_id,
        span_id=item_in.span_id,
        claim_id=item_in.claim_id,
        metric_id=item_in.metric_id,
        order_index=item_in.order_index,
        notes=item_in.notes,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)

    # Load relationships for response
    await db.refresh(item, ["span", "claim", "metric"])

    return EvidencePackItemResponse.model_validate(item)


@router.get(
    "/evidence-packs/{pack_id}/export",
    summary="Export Evidence Pack",
    description="Export evidence pack as structured JSON.",
)
async def export_evidence_pack(
    pack_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> dict:
    """Export evidence pack with full details."""
    result = await db.execute(
        select(EvidencePack)
        .options(
            selectinload(EvidencePack.items)
            .selectinload(EvidencePackItem.span)
            .selectinload(Span.document_version),
            selectinload(EvidencePack.items)
            .selectinload(EvidencePackItem.claim),
            selectinload(EvidencePack.items)
            .selectinload(EvidencePackItem.metric),
        )
        .where(EvidencePack.id == pack_id)
    )
    pack = result.scalar_one_or_none()

    if not pack:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evidence pack {pack_id} not found",
        )

    # Build export structure
    export_items = []
    for item in pack.items:
        export_item = {
            "order": item.order_index,
            "notes": item.notes,
            "span": {
                "id": str(item.span.id),
                "text": item.span.text_content,
                "type": item.span.span_type.value,
                "locator": item.span.start_locator,
                "document_version_id": str(item.span.document_version_id),
            },
        }

        if item.claim:
            export_item["claim"] = {
                "id": str(item.claim.id),
                "text": item.claim.claim_text,
                "type": item.claim.claim_type,
                "confidence": item.claim.confidence,
            }

        if item.metric:
            export_item["metric"] = {
                "id": str(item.metric.id),
                "name": item.metric.metric_name,
                "value": item.metric.metric_value,
                "unit": item.metric.unit,
            }

        export_items.append(export_item)

    return {
        "evidence_pack": {
            "id": str(pack.id),
            "name": pack.name,
            "description": pack.description,
            "project_id": str(pack.project_id),
            "created_at": pack.created_at.isoformat(),
            "created_by": pack.created_by,
        },
        "items": export_items,
        "item_count": len(export_items),
        "exported_at": datetime.utcnow().isoformat(),
    }


@router.delete(
    "/evidence-packs/{pack_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Evidence Pack",
    description="Delete an evidence pack and all its items.",
)
async def delete_evidence_pack(
    pack_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> None:
    """Delete an evidence pack."""
    result = await db.execute(select(EvidencePack).where(EvidencePack.id == pack_id))
    pack = result.scalar_one_or_none()

    if not pack:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evidence pack {pack_id} not found",
        )

    await db.delete(pack)
    await db.commit()


# Import datetime for export endpoint
from datetime import datetime


# =============================================================================
# Evidence Pack with LOD Support
# =============================================================================


@router.get(
    "/evidence-packs/{pack_id}/with-facts",
    summary="Get Evidence Pack with Multi-Level Facts",
    description="Get evidence pack enriched with facts at specified profile/context/level.",
)
async def get_evidence_pack_with_facts(
    pack_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
    profile_code: str = Query("general", description="Extraction profile (general, vc, pharma, insurance)"),
    process_context: str = Query("unspecified", description="Business process context (e.g., vc.ic_decision, pharma.clinical_trial)"),
    level: int = Query(2, ge=1, le=4, description="Extraction level 1-4"),
) -> dict:
    """Get evidence pack enriched with multi-level extracted facts.

    This endpoint retrieves an evidence pack and enriches each item with
    relevant facts (claims, metrics, constraints, risks) extracted at the
    specified (profile, process_context, level) combination.

    Process contexts allow domain-specific extractions:
    - VC: vc.ic_decision, vc.due_diligence, vc.portfolio_review
    - Pharma: pharma.clinical_trial, pharma.regulatory, pharma.safety
    - Insurance: insurance.underwriting, insurance.claims, insurance.compliance
    - General: general.research, general.compliance, general.audit
    """
    from evidence_repository.models.extraction_level import (
        ExtractionLevel,
        ExtractionLevelCode,
        ExtractionProfile,
        ExtractionProfileCode,
        ProcessContext,
    )
    from evidence_repository.models.facts import (
        FactClaim,
        FactMetric,
        FactConstraint,
        FactRisk,
    )

    # Get the evidence pack
    result = await db.execute(
        select(EvidencePack)
        .options(
            selectinload(EvidencePack.items)
            .selectinload(EvidencePackItem.span)
            .selectinload(Span.document_version),
            selectinload(EvidencePack.items)
            .selectinload(EvidencePackItem.claim),
            selectinload(EvidencePack.items)
            .selectinload(EvidencePackItem.metric),
        )
        .where(EvidencePack.id == pack_id)
    )
    pack = result.scalar_one_or_none()

    if not pack:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evidence pack {pack_id} not found",
        )

    # Parse profile code
    try:
        pc = ExtractionProfileCode(profile_code)
    except ValueError:
        pc = ExtractionProfileCode.GENERAL

    # Parse process context
    try:
        proc_ctx = ProcessContext(process_context)
    except ValueError:
        proc_ctx = ProcessContext.UNSPECIFIED

    profile_stmt = select(ExtractionProfile.id).where(ExtractionProfile.code == pc)
    profile_result = await db.execute(profile_stmt)
    profile_id = profile_result.scalar_one_or_none()

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

    # Build export structure with facts
    export_items = []
    for item in pack.items:
        version_id = item.span.document_version_id

        # Get facts for this version at specified profile/process_context/level
        fact_claims = []
        fact_metrics = []
        fact_constraints = []
        fact_risks = []

        if profile_id and level_id:
            # Query facts with process_context filter
            claims_stmt = select(FactClaim).where(
                FactClaim.version_id == version_id,
                FactClaim.profile_id == profile_id,
                FactClaim.process_context == proc_ctx,
                FactClaim.level_id == level_id,
            ).limit(50)
            claims_result = await db.execute(claims_stmt)
            for claim in claims_result.scalars():
                fact_claims.append({
                    "id": str(claim.id),
                    "subject": claim.subject,
                    "predicate": claim.predicate,
                    "object": claim.object,
                    "claim_type": claim.claim_type,
                    "certainty": claim.certainty.value,
                    "evidence_quote": claim.evidence_quote,
                    "process_context": claim.process_context.value,
                })

            metrics_stmt = select(FactMetric).where(
                FactMetric.version_id == version_id,
                FactMetric.profile_id == profile_id,
                FactMetric.process_context == proc_ctx,
                FactMetric.level_id == level_id,
            ).limit(50)
            metrics_result = await db.execute(metrics_stmt)
            for metric in metrics_result.scalars():
                fact_metrics.append({
                    "id": str(metric.id),
                    "metric_name": metric.metric_name,
                    "value_numeric": metric.value_numeric,
                    "value_raw": metric.value_raw,
                    "unit": metric.unit,
                    "currency": metric.currency,
                    "certainty": metric.certainty.value,
                    "process_context": metric.process_context.value,
                })

            constraints_stmt = select(FactConstraint).where(
                FactConstraint.version_id == version_id,
                FactConstraint.profile_id == profile_id,
                FactConstraint.process_context == proc_ctx,
                FactConstraint.level_id == level_id,
            ).limit(20)
            constraints_result = await db.execute(constraints_stmt)
            for constraint in constraints_result.scalars():
                fact_constraints.append({
                    "id": str(constraint.id),
                    "constraint_type": constraint.constraint_type.value,
                    "statement": constraint.statement,
                    "applies_to": constraint.applies_to,
                    "process_context": constraint.process_context.value,
                })

            risks_stmt = select(FactRisk).where(
                FactRisk.version_id == version_id,
                FactRisk.profile_id == profile_id,
                FactRisk.process_context == proc_ctx,
                FactRisk.level_id == level_id,
            ).limit(20)
            risks_result = await db.execute(risks_stmt)
            for risk in risks_result.scalars():
                fact_risks.append({
                    "id": str(risk.id),
                    "risk_type": risk.risk_type,
                    "severity": risk.severity.value,
                    "statement": risk.statement,
                    "rationale": risk.rationale,
                    "process_context": risk.process_context.value,
                })

        export_item = {
            "order": item.order_index,
            "notes": item.notes,
            "span": {
                "id": str(item.span.id),
                "text": item.span.text_content,
                "type": item.span.span_type.value,
                "locator": item.span.start_locator,
                "document_version_id": str(item.span.document_version_id),
            },
            "facts": {
                "claims": fact_claims,
                "metrics": fact_metrics,
                "constraints": fact_constraints,
                "risks": fact_risks,
            },
        }

        if item.claim:
            export_item["legacy_claim"] = {
                "id": str(item.claim.id),
                "text": item.claim.claim_text,
                "type": item.claim.claim_type.value if hasattr(item.claim.claim_type, "value") else str(item.claim.claim_type),
                "confidence": item.claim.confidence,
            }

        if item.metric:
            export_item["legacy_metric"] = {
                "id": str(item.metric.id),
                "name": item.metric.metric_name,
                "value": item.metric.metric_value,
                "unit": item.metric.unit,
            }

        export_items.append(export_item)

    return {
        "evidence_pack": {
            "id": str(pack.id),
            "name": pack.name,
            "description": pack.description,
            "project_id": str(pack.project_id),
            "created_at": pack.created_at.isoformat(),
            "created_by": pack.created_by,
        },
        "extraction_context": {
            "profile_code": profile_code,
            "process_context": process_context,
            "level": level,
            "profile_id": str(profile_id) if profile_id else None,
            "level_id": str(level_id) if level_id else None,
        },
        "items": export_items,
        "item_count": len(export_items),
        "retrieved_at": datetime.utcnow().isoformat(),
    }


# =============================================================================
# Evidence Pack Extraction Request (Juris API)
# =============================================================================


@router.post(
    "/evidence-packs/{pack_id}/request-extraction",
    summary="Request Extraction for Evidence Pack",
    description="Request extraction at specific (profile, process_context, level) for all documents in an evidence pack.",
)
async def request_evidence_pack_extraction(
    pack_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
    profile_code: str = Query("general", description="Extraction profile"),
    process_context: str = Query("unspecified", description="Business process context"),
    level: int = Query(2, ge=1, le=4, description="Extraction level 1-4"),
    compute_mode: str = Query("exact_only", description="Compute mode: exact_only or all_up_to"),
) -> dict:
    """Request extraction for all documents in an evidence pack.

    This endpoint allows Juris or other callers to request extractions at
    specific (profile, process_context, level) combinations for all documents
    referenced in the evidence pack.

    Compute modes:
    - exact_only: Only compute the exact level requested
    - all_up_to: Compute all levels from L1 up to the requested level

    Returns extraction run IDs and job queue status for each document.
    """
    from starlette.background import BackgroundTasks
    from evidence_repository.models.extraction_level import (
        ExtractionProfile,
        ExtractionProfileCode,
        ExtractionRunStatus,
        FactExtractionRun,
        ProcessContext,
    )
    from evidence_repository.queue.tasks import task_multilevel_extract

    # Get the evidence pack with document references
    result = await db.execute(
        select(EvidencePack)
        .options(
            selectinload(EvidencePack.items)
            .selectinload(EvidencePackItem.span)
        )
        .where(EvidencePack.id == pack_id)
    )
    pack = result.scalar_one_or_none()

    if not pack:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evidence pack {pack_id} not found",
        )

    # Parse process context
    try:
        proc_ctx = ProcessContext(process_context)
    except ValueError:
        proc_ctx = ProcessContext.UNSPECIFIED

    # Collect unique document version IDs
    version_ids = set()
    for item in pack.items:
        if item.span:
            version_ids.add(item.span.document_version_id)

    # Check existing extraction runs
    extraction_requests = []
    for version_id in version_ids:
        # Check if extraction already exists at this level
        try:
            pc = ExtractionProfileCode(profile_code)
        except ValueError:
            pc = ExtractionProfileCode.GENERAL

        profile_stmt = select(ExtractionProfile).where(ExtractionProfile.code == pc)
        profile_result = await db.execute(profile_stmt)
        profile = profile_result.scalar_one_or_none()

        existing_run = None
        if profile:
            run_stmt = select(FactExtractionRun).where(
                FactExtractionRun.version_id == version_id,
                FactExtractionRun.profile_id == profile.id,
                FactExtractionRun.process_context == proc_ctx,
                FactExtractionRun.status == ExtractionRunStatus.SUCCEEDED,
            )
            run_result = await db.execute(run_stmt)
            existing_run = run_result.scalar_one_or_none()

        if existing_run:
            extraction_requests.append({
                "version_id": str(version_id),
                "status": "exists",
                "run_id": str(existing_run.id),
                "message": f"Extraction already exists at L{level}",
            })
        else:
            # Queue new extraction
            extraction_requests.append({
                "version_id": str(version_id),
                "status": "queued",
                "profile_code": profile_code,
                "process_context": process_context,
                "level": level,
                "compute_mode": compute_mode,
            })

    return {
        "evidence_pack_id": str(pack_id),
        "extraction_request": {
            "profile_code": profile_code,
            "process_context": process_context,
            "level": level,
            "compute_mode": compute_mode,
        },
        "versions_requested": len(version_ids),
        "requests": extraction_requests,
        "message": f"Extraction request submitted for {len(version_ids)} document versions",
    }


@router.get(
    "/evidence-packs/{pack_id}/extraction-status",
    summary="Get Extraction Status for Evidence Pack",
    description="Check extraction status for all documents in an evidence pack.",
)
async def get_evidence_pack_extraction_status(
    pack_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
    profile_code: str = Query("general", description="Extraction profile"),
    process_context: str = Query("unspecified", description="Business process context"),
) -> dict:
    """Get extraction status for all documents in an evidence pack.

    Returns the current extraction status for each document at each level,
    allowing Juris to determine what extractions are available and which
    need to be requested.
    """
    from evidence_repository.models.extraction_level import (
        ExtractionLevel,
        ExtractionLevelCode,
        ExtractionProfile,
        ExtractionProfileCode,
        ExtractionRunStatus,
        FactExtractionRun,
        ProcessContext,
    )

    # Get the evidence pack with document references
    result = await db.execute(
        select(EvidencePack)
        .options(
            selectinload(EvidencePack.items)
            .selectinload(EvidencePackItem.span)
        )
        .where(EvidencePack.id == pack_id)
    )
    pack = result.scalar_one_or_none()

    if not pack:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evidence pack {pack_id} not found",
        )

    # Parse process context
    try:
        proc_ctx = ProcessContext(process_context)
    except ValueError:
        proc_ctx = ProcessContext.UNSPECIFIED

    # Get profile
    try:
        pc = ExtractionProfileCode(profile_code)
    except ValueError:
        pc = ExtractionProfileCode.GENERAL

    profile_stmt = select(ExtractionProfile).where(ExtractionProfile.code == pc)
    profile_result = await db.execute(profile_stmt)
    profile = profile_result.scalar_one_or_none()

    # Get level records
    levels_stmt = select(ExtractionLevel).order_by(ExtractionLevel.rank)
    levels_result = await db.execute(levels_stmt)
    levels = {level.id: level for level in levels_result.scalars()}

    # Collect unique document version IDs
    version_ids = set()
    for item in pack.items:
        if item.span:
            version_ids.add(item.span.document_version_id)

    # Check extraction status for each version
    version_statuses = []
    for version_id in version_ids:
        level_status = {}

        if profile:
            runs_stmt = select(FactExtractionRun).where(
                FactExtractionRun.version_id == version_id,
                FactExtractionRun.profile_id == profile.id,
                FactExtractionRun.process_context == proc_ctx,
            )
            runs_result = await db.execute(runs_stmt)

            for run in runs_result.scalars():
                level = levels.get(run.level_id)
                if level:
                    level_status[level.code.value] = {
                        "status": run.status.value,
                        "run_id": str(run.id),
                        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
                        "metadata": run.metadata_,
                    }

        version_statuses.append({
            "version_id": str(version_id),
            "levels": level_status,
            "available_levels": [k for k, v in level_status.items() if v["status"] == "succeeded"],
        })

    return {
        "evidence_pack_id": str(pack_id),
        "profile_code": profile_code,
        "process_context": process_context,
        "versions_count": len(version_ids),
        "versions": version_statuses,
    }
