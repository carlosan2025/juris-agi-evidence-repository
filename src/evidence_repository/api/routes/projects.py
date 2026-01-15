"""Project management endpoints."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from evidence_repository.api.dependencies import User, get_current_user
from evidence_repository.db.session import get_db_session
from evidence_repository.models.document import Document, DocumentVersion
from evidence_repository.models.evidence import (
    Claim,
    EvidencePack,
    EvidencePackItem,
    Metric,
    Span,
)
from evidence_repository.models.project import Project, ProjectDocument
from evidence_repository.schemas.common import PaginatedResponse
from evidence_repository.schemas.evidence import (
    JurisClaimSummary,
    JurisConflictSummary,
    JurisDocumentSummary,
    JurisEvidencePackCreate,
    JurisEvidencePackResponse,
    JurisMetricSummary,
    JurisOpenQuestionSummary,
    JurisQualitySummary,
    JurisSpanSummary,
)
from evidence_repository.schemas.project import (
    AttachDocumentRequest,
    ProjectCreate,
    ProjectDocumentResponse,
    ProjectResponse,
    ProjectUpdate,
)
from evidence_repository.services.quality_analysis import QualityAnalysisService

router = APIRouter()


@router.post(
    "",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Project",
    description="Create a new project (evaluation context).",
)
async def create_project(
    project_in: ProjectCreate,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> ProjectResponse:
    """Create a new project."""
    project = Project(
        name=project_in.name,
        description=project_in.description,
        case_ref=project_in.case_ref,
        metadata_=project_in.metadata,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)

    return ProjectResponse(
        **project.__dict__,
        document_count=0,
        claim_count=0,
        metric_count=0,
    )


@router.get(
    "",
    response_model=PaginatedResponse[ProjectResponse],
    summary="List Projects",
    description="List all projects with pagination.",
)
async def list_projects(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    include_deleted: bool = Query(default=False),
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> PaginatedResponse[ProjectResponse]:
    """List projects with pagination."""
    query = select(Project).options(
        selectinload(Project.project_documents),
        selectinload(Project.claims),
        selectinload(Project.metrics),
    )

    if not include_deleted:
        query = query.where(Project.deleted_at.is_(None))

    # Count total
    count_query = select(func.count()).select_from(Project)
    if not include_deleted:
        count_query = count_query.where(Project.deleted_at.is_(None))
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Paginate
    query = query.order_by(Project.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    projects = result.scalars().all()

    items = []
    for p in projects:
        items.append(
            ProjectResponse(
                id=p.id,
                name=p.name,
                description=p.description,
                case_ref=p.case_ref,
                created_at=p.created_at,
                updated_at=p.updated_at,
                deleted_at=p.deleted_at,
                metadata_=p.metadata_,
                document_count=len(p.project_documents),
                claim_count=len(p.claims),
                metric_count=len(p.metrics),
            )
        )

    return PaginatedResponse.create(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
    summary="Get Project",
    description="Get project details by ID.",
)
async def get_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> ProjectResponse:
    """Get a project by ID."""
    result = await db.execute(
        select(Project)
        .options(
            selectinload(Project.project_documents),
            selectinload(Project.claims),
            selectinload(Project.metrics),
        )
        .where(Project.id == project_id)
    )
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )

    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        case_ref=project.case_ref,
        created_at=project.created_at,
        updated_at=project.updated_at,
        deleted_at=project.deleted_at,
        metadata_=project.metadata_,
        document_count=len(project.project_documents),
        claim_count=len(project.claims),
        metric_count=len(project.metrics),
    )


@router.patch(
    "/{project_id}",
    response_model=ProjectResponse,
    summary="Update Project",
    description="Update project details.",
)
async def update_project(
    project_id: uuid.UUID,
    project_in: ProjectUpdate,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> ProjectResponse:
    """Update a project."""
    result = await db.execute(
        select(Project)
        .options(
            selectinload(Project.project_documents),
            selectinload(Project.claims),
            selectinload(Project.metrics),
        )
        .where(Project.id == project_id)
    )
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )

    # Update fields
    if project_in.name is not None:
        project.name = project_in.name
    if project_in.description is not None:
        project.description = project_in.description
    if project_in.case_ref is not None:
        project.case_ref = project_in.case_ref
    if project_in.metadata is not None:
        project.metadata_ = project_in.metadata

    await db.commit()
    await db.refresh(project)

    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        case_ref=project.case_ref,
        created_at=project.created_at,
        updated_at=project.updated_at,
        deleted_at=project.deleted_at,
        metadata_=project.metadata_,
        document_count=len(project.project_documents),
        claim_count=len(project.claims),
        metric_count=len(project.metrics),
    )


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Project",
    description="Soft delete a project.",
)
async def delete_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> None:
    """Soft delete a project."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )

    project.deleted_at = datetime.utcnow()
    await db.commit()


# =============================================================================
# Project Document Attachment
# =============================================================================


@router.post(
    "/{project_id}/documents",
    response_model=ProjectDocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Attach Document",
    description="Attach a document to a project.",
)
async def attach_document(
    project_id: uuid.UUID,
    request: AttachDocumentRequest,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> ProjectDocumentResponse:
    """Attach a document to a project."""
    # Verify project exists
    project_result = await db.execute(select(Project).where(Project.id == project_id))
    project = project_result.scalar_one_or_none()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )

    # Verify document exists
    doc_result = await db.execute(
        select(Document)
        .options(selectinload(Document.versions))
        .where(Document.id == request.document_id)
    )
    document = doc_result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {request.document_id} not found",
        )

    # Check if already attached
    existing = await db.execute(
        select(ProjectDocument).where(
            ProjectDocument.project_id == project_id,
            ProjectDocument.document_id == request.document_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document already attached to this project",
        )

    # Validate folder if specified
    if request.folder_id:
        from evidence_repository.models.folder import Folder

        folder_result = await db.execute(
            select(Folder).where(
                Folder.id == request.folder_id,
                Folder.project_id == project_id,
                Folder.deleted_at.is_(None),
            )
        )
        if not folder_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Folder not found or does not belong to this project",
            )

    # Create attachment
    project_document = ProjectDocument(
        project_id=project_id,
        document_id=request.document_id,
        pinned_version_id=request.pinned_version_id,
        folder_id=request.folder_id,
        attached_by=user.id,
        notes=request.notes,
    )
    db.add(project_document)
    await db.commit()
    await db.refresh(project_document)

    return ProjectDocumentResponse.model_validate(project_document)


@router.get(
    "/{project_id}/documents",
    response_model=list[ProjectDocumentResponse],
    summary="List Project Documents",
    description="List all documents attached to a project, optionally filtered by folder.",
)
async def list_project_documents(
    project_id: uuid.UUID,
    folder_id: uuid.UUID | None = Query(
        default=None,
        description="Filter by folder ID. Use 'root' for documents at project root (no folder).",
    ),
    root_only: bool = Query(
        default=False,
        description="If true, return only documents at project root (no folder)",
    ),
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> list[ProjectDocumentResponse]:
    """List documents attached to a project."""
    query = (
        select(ProjectDocument)
        .options(
            selectinload(ProjectDocument.document).selectinload(Document.versions),
            selectinload(ProjectDocument.pinned_version),
            selectinload(ProjectDocument.folder),
        )
        .where(ProjectDocument.project_id == project_id)
    )

    # Filter by folder
    if folder_id is not None:
        query = query.where(ProjectDocument.folder_id == folder_id)
    elif root_only:
        query = query.where(ProjectDocument.folder_id.is_(None))

    query = query.order_by(ProjectDocument.attached_at.desc())

    result = await db.execute(query)
    project_documents = result.scalars().all()

    return [ProjectDocumentResponse.model_validate(pd) for pd in project_documents]


@router.delete(
    "/{project_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Detach Document",
    description="Detach a document from a project.",
)
async def detach_document(
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> None:
    """Detach a document from a project."""
    result = await db.execute(
        select(ProjectDocument).where(
            ProjectDocument.project_id == project_id,
            ProjectDocument.document_id == document_id,
        )
    )
    project_document = result.scalar_one_or_none()

    if not project_document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not attached to this project",
        )

    await db.delete(project_document)
    await db.commit()


# =============================================================================
# Juris-AGI Evidence Packs (Primary Integration Point)
# =============================================================================


@router.post(
    "/{project_id}/evidence-packs",
    response_model=JurisEvidencePackResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Evidence Pack (Juris-AGI)",
    description="""
Create a comprehensive evidence pack for Juris-AGI integration.

This is the **primary integration point** between Evidence Repository and Juris-AGI.

The response includes:
- **documents**: All documents referenced by included spans
- **spans**: Evidence spans with text and locators
- **claims**: Claims extracted from spans
- **metrics**: Metrics extracted from spans
- **conflicts**: Detected conflicts (metric/claim contradictions)
- **open_questions**: Questions requiring human attention

Use this endpoint to bundle evidence for legal analysis and reporting.
    """,
)
async def create_juris_evidence_pack(
    project_id: uuid.UUID,
    pack_in: JurisEvidencePackCreate,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> JurisEvidencePackResponse:
    """Create a comprehensive evidence pack for Juris-AGI."""
    # Verify project exists
    project_result = await db.execute(select(Project).where(Project.id == project_id))
    if not project_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )

    # Create the evidence pack
    pack = EvidencePack(
        project_id=project_id,
        name=pack_in.name,
        description=pack_in.description,
        created_by=user.id,
        metadata_=pack_in.metadata,
    )
    db.add(pack)
    await db.flush()

    # Add items from specified IDs
    order_index = 0

    # Add spans
    for span_id in pack_in.span_ids:
        span_result = await db.execute(select(Span).where(Span.id == span_id))
        if span_result.scalar_one_or_none():
            item = EvidencePackItem(
                evidence_pack_id=pack.id,
                span_id=span_id,
                order_index=order_index,
            )
            db.add(item)
            order_index += 1

    # Add claims (link to their spans)
    for claim_id in pack_in.claim_ids:
        claim_result = await db.execute(select(Claim).where(Claim.id == claim_id))
        claim = claim_result.scalar_one_or_none()
        if claim:
            item = EvidencePackItem(
                evidence_pack_id=pack.id,
                span_id=claim.span_id,
                claim_id=claim_id,
                order_index=order_index,
            )
            db.add(item)
            order_index += 1

    # Add metrics (link to their spans)
    for metric_id in pack_in.metric_ids:
        metric_result = await db.execute(select(Metric).where(Metric.id == metric_id))
        metric = metric_result.scalar_one_or_none()
        if metric:
            item = EvidencePackItem(
                evidence_pack_id=pack.id,
                span_id=metric.span_id,
                metric_id=metric_id,
                order_index=order_index,
            )
            db.add(item)
            order_index += 1

    await db.commit()
    await db.refresh(pack)

    # Return the comprehensive pack response
    return await _build_juris_evidence_pack_response(
        db, pack, pack_in.include_quality_analysis
    )


@router.get(
    "/{project_id}/evidence-packs/{pack_id}",
    response_model=JurisEvidencePackResponse,
    summary="Get Evidence Pack (Juris-AGI)",
    description="""
Get a comprehensive evidence pack for Juris-AGI integration.

This is the **primary integration point** between Evidence Repository and Juris-AGI.

The response includes:
- **documents**: All documents referenced by included spans
- **spans**: Evidence spans with text and locators
- **claims**: Claims extracted from spans
- **metrics**: Metrics extracted from spans
- **conflicts**: Detected conflicts (metric/claim contradictions)
- **open_questions**: Questions requiring human attention

Quality analysis is always included to ensure data integrity awareness.
    """,
)
async def get_juris_evidence_pack(
    project_id: uuid.UUID,
    pack_id: uuid.UUID,
    include_quality_analysis: bool = Query(
        default=True, description="Include conflicts and open questions"
    ),
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> JurisEvidencePackResponse:
    """Get a comprehensive evidence pack for Juris-AGI."""
    # Verify project exists
    project_result = await db.execute(select(Project).where(Project.id == project_id))
    if not project_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )

    # Get the evidence pack
    result = await db.execute(
        select(EvidencePack).where(
            EvidencePack.id == pack_id,
            EvidencePack.project_id == project_id,
        )
    )
    pack = result.scalar_one_or_none()

    if not pack:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evidence pack {pack_id} not found in project {project_id}",
        )

    return await _build_juris_evidence_pack_response(db, pack, include_quality_analysis)


@router.get(
    "/{project_id}/evidence-packs",
    response_model=list[JurisEvidencePackResponse],
    summary="List Evidence Packs (Juris-AGI)",
    description="List all evidence packs for a project.",
)
async def list_juris_evidence_packs(
    project_id: uuid.UUID,
    include_quality_analysis: bool = Query(
        default=False, description="Include conflicts and open questions (slower)"
    ),
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> list[JurisEvidencePackResponse]:
    """List all evidence packs for a project."""
    # Verify project exists
    project_result = await db.execute(select(Project).where(Project.id == project_id))
    if not project_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )

    # Get all evidence packs for the project
    result = await db.execute(
        select(EvidencePack)
        .where(EvidencePack.project_id == project_id)
        .order_by(EvidencePack.created_at.desc())
    )
    packs = result.scalars().all()

    responses = []
    for pack in packs:
        response = await _build_juris_evidence_pack_response(
            db, pack, include_quality_analysis
        )
        responses.append(response)

    return responses


# =============================================================================
# Helper Functions for Juris-AGI Evidence Packs
# =============================================================================


async def _build_juris_evidence_pack_response(
    db: AsyncSession,
    pack: EvidencePack,
    include_quality_analysis: bool = True,
) -> JurisEvidencePackResponse:
    """Build comprehensive Juris-AGI evidence pack response."""
    # Load pack items with relationships
    items_result = await db.execute(
        select(EvidencePackItem)
        .options(
            selectinload(EvidencePackItem.span)
            .selectinload(Span.document_version)
            .selectinload(DocumentVersion.document),
            selectinload(EvidencePackItem.claim),
            selectinload(EvidencePackItem.metric),
        )
        .where(EvidencePackItem.evidence_pack_id == pack.id)
        .order_by(EvidencePackItem.order_index)
    )
    items = items_result.scalars().all()

    # Collect unique documents, spans, claims, metrics
    documents_map: dict[uuid.UUID, JurisDocumentSummary] = {}
    spans_map: dict[uuid.UUID, JurisSpanSummary] = {}
    claims_list: list[JurisClaimSummary] = []
    metrics_list: list[JurisMetricSummary] = []

    for item in items:
        span = item.span
        if not span:
            continue

        # Add span
        if span.id not in spans_map:
            doc_version = span.document_version
            document = doc_version.document if doc_version else None
            filename = document.filename if document else "unknown"

            spans_map[span.id] = JurisSpanSummary(
                id=span.id,
                document_version_id=span.document_version_id,
                document_filename=filename,
                span_type=span.span_type.value if hasattr(span.span_type, "value") else str(span.span_type),
                text_content=span.text_content,
                locator=span.start_locator,
            )

            # Add document
            if doc_version and doc_version.document_id not in documents_map:
                documents_map[doc_version.document_id] = JurisDocumentSummary(
                    id=doc_version.document_id,
                    filename=filename,
                    content_type=document.content_type if document else None,
                    version_id=doc_version.id,
                    version_number=doc_version.version_number,
                    extraction_status=doc_version.extraction_status.value
                    if hasattr(doc_version.extraction_status, "value")
                    else str(doc_version.extraction_status)
                    if doc_version.extraction_status
                    else None,
                )

        # Add claim
        if item.claim:
            claim = item.claim
            claims_list.append(
                JurisClaimSummary(
                    id=claim.id,
                    span_id=claim.span_id,
                    claim_text=claim.claim_text,
                    claim_type=claim.claim_type.value if hasattr(claim.claim_type, "value") else str(claim.claim_type),
                    certainty=claim.certainty.value if hasattr(claim.certainty, "value") else str(claim.certainty),
                    reliability=claim.reliability.value if hasattr(claim.reliability, "value") else str(claim.reliability),
                    time_scope=claim.time_scope,
                    extraction_confidence=claim.extraction_confidence,
                )
            )

        # Add metric
        if item.metric:
            metric = item.metric
            metrics_list.append(
                JurisMetricSummary(
                    id=metric.id,
                    span_id=metric.span_id,
                    metric_name=metric.metric_name,
                    metric_type=metric.metric_type.value if hasattr(metric.metric_type, "value") else str(metric.metric_type),
                    metric_value=metric.metric_value,
                    numeric_value=metric.numeric_value,
                    unit=metric.unit,
                    time_scope=metric.time_scope,
                    certainty=metric.certainty.value if hasattr(metric.certainty, "value") else str(metric.certainty),
                    reliability=metric.reliability.value if hasattr(metric.reliability, "value") else str(metric.reliability),
                )
            )

    # Quality analysis
    conflicts: list[JurisConflictSummary] = []
    open_questions: list[JurisOpenQuestionSummary] = []
    quality_summary: JurisQualitySummary | None = None

    if include_quality_analysis and documents_map:
        quality_service = QualityAnalysisService(db)

        # Run quality analysis for each document
        all_metric_conflicts = []
        all_claim_conflicts = []
        all_open_questions = []

        for doc_id, doc_summary in documents_map.items():
            try:
                analysis_result = await quality_service.analyze_document(
                    document_id=doc_id,
                    version_id=doc_summary.version_id,
                )

                # Collect metric conflicts
                for conflict in analysis_result.metric_conflicts:
                    all_metric_conflicts.append(
                        JurisConflictSummary(
                            conflict_type="metric",
                            severity=conflict.severity.value,
                            reason=conflict.reason,
                            affected_ids=[str(mid) for mid in conflict.metric_ids],
                            details={
                                "metric_name": conflict.metric_name,
                                "entity_id": conflict.entity_id,
                                "values": conflict.values,
                            },
                        )
                    )

                # Collect claim conflicts
                for conflict in analysis_result.claim_conflicts:
                    all_claim_conflicts.append(
                        JurisConflictSummary(
                            conflict_type="claim",
                            severity=conflict.severity.value,
                            reason=conflict.reason,
                            affected_ids=[str(cid) for cid in conflict.claim_ids],
                            details={
                                "predicate": conflict.predicate,
                                "subject": conflict.subject,
                                "values": conflict.values,
                            },
                        )
                    )

                # Collect open questions
                for question in analysis_result.open_questions:
                    all_open_questions.append(
                        JurisOpenQuestionSummary(
                            category=question.category.value,
                            question=question.question,
                            context=question.context,
                            related_ids=[
                                str(mid) for mid in question.related_metric_ids
                            ] + [str(cid) for cid in question.related_claim_ids],
                        )
                    )
            except Exception:
                # Quality analysis failure shouldn't break the pack retrieval
                pass

        conflicts = all_metric_conflicts + all_claim_conflicts
        open_questions = all_open_questions

        # Build quality summary
        critical_count = sum(1 for c in conflicts if c.severity == "critical")
        high_count = sum(1 for c in conflicts if c.severity == "high")

        quality_summary = JurisQualitySummary(
            total_conflicts=len(conflicts),
            critical_conflicts=critical_count,
            high_conflicts=high_count,
            total_open_questions=len(open_questions),
        )

    return JurisEvidencePackResponse(
        id=pack.id,
        project_id=pack.project_id,
        name=pack.name,
        description=pack.description,
        created_by=pack.created_by,
        created_at=pack.created_at,
        updated_at=pack.updated_at,
        documents=list(documents_map.values()),
        spans=list(spans_map.values()),
        claims=claims_list,
        metrics=metrics_list,
        conflicts=conflicts,
        open_questions=open_questions,
        quality_summary=quality_summary,
        document_count=len(documents_map),
        span_count=len(spans_map),
        claim_count=len(claims_list),
        metric_count=len(metrics_list),
        metadata=pack.metadata_,
    )
