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
