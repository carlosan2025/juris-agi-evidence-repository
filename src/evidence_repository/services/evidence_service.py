"""Evidence business service layer."""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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


@dataclass
class EvidencePackExport:
    """Exported evidence pack structure."""

    pack_id: uuid.UUID
    name: str
    description: str | None
    project_id: uuid.UUID
    items: list[dict]
    item_count: int


class EvidenceService:
    """High-level evidence operations."""

    def __init__(self, db: AsyncSession):
        """Initialize evidence service.

        Args:
            db: Database session.
        """
        self.db = db

    # =========================================================================
    # Spans
    # =========================================================================

    async def create_span(
        self,
        document_version: DocumentVersion,
        text_content: str,
        start_locator: dict,
        end_locator: dict | None = None,
        span_type: SpanType = SpanType.TEXT,
        metadata: dict | None = None,
    ) -> Span:
        """Create an evidence span.

        Args:
            document_version: Document version to reference.
            text_content: Text content of the span.
            start_locator: Start position locator.
            end_locator: Optional end position locator.
            span_type: Type of span.
            metadata: Optional metadata.

        Returns:
            Created span.
        """
        span = Span(
            document_version_id=document_version.id,
            text_content=text_content,
            start_locator=start_locator,
            end_locator=end_locator,
            span_type=span_type,
            metadata_=metadata or {},
        )
        self.db.add(span)
        await self.db.flush()
        return span

    async def get_span(self, span_id: uuid.UUID) -> Span | None:
        """Get a span by ID.

        Args:
            span_id: Span ID.

        Returns:
            Span or None.
        """
        result = await self.db.execute(
            select(Span)
            .options(selectinload(Span.document_version))
            .where(Span.id == span_id)
        )
        return result.scalar_one_or_none()

    async def get_spans_for_version(
        self, document_version_id: uuid.UUID
    ) -> list[Span]:
        """Get all spans for a document version.

        Args:
            document_version_id: Document version ID.

        Returns:
            List of spans.
        """
        result = await self.db.execute(
            select(Span)
            .where(Span.document_version_id == document_version_id)
            .order_by(Span.created_at)
        )
        return list(result.scalars().all())

    # =========================================================================
    # Claims
    # =========================================================================

    async def create_claim(
        self,
        project: Project,
        span: Span,
        claim_text: str,
        claim_type: str | None = None,
        confidence: float | None = None,
        metadata: dict | None = None,
    ) -> Claim:
        """Create a claim citing a span.

        Args:
            project: Project context.
            span: Evidence span.
            claim_text: The claim text.
            claim_type: Optional claim type.
            confidence: Optional confidence score.
            metadata: Optional metadata.

        Returns:
            Created claim.
        """
        claim = Claim(
            project_id=project.id,
            span_id=span.id,
            claim_text=claim_text,
            claim_type=claim_type,
            confidence=confidence,
            metadata_=metadata or {},
        )
        self.db.add(claim)
        await self.db.flush()
        return claim

    async def get_claims_for_project(self, project_id: uuid.UUID) -> list[Claim]:
        """Get all claims for a project.

        Args:
            project_id: Project ID.

        Returns:
            List of claims with spans loaded.
        """
        result = await self.db.execute(
            select(Claim)
            .options(selectinload(Claim.span))
            .where(Claim.project_id == project_id)
            .order_by(Claim.created_at)
        )
        return list(result.scalars().all())

    # =========================================================================
    # Metrics
    # =========================================================================

    async def create_metric(
        self,
        project: Project,
        span: Span,
        metric_name: str,
        metric_value: str,
        unit: str | None = None,
        metadata: dict | None = None,
    ) -> Metric:
        """Create a metric citing a span.

        Args:
            project: Project context.
            span: Evidence span.
            metric_name: Metric name.
            metric_value: Metric value.
            unit: Optional unit.
            metadata: Optional metadata.

        Returns:
            Created metric.
        """
        metric = Metric(
            project_id=project.id,
            span_id=span.id,
            metric_name=metric_name,
            metric_value=metric_value,
            unit=unit,
            metadata_=metadata or {},
        )
        self.db.add(metric)
        await self.db.flush()
        return metric

    async def get_metrics_for_project(self, project_id: uuid.UUID) -> list[Metric]:
        """Get all metrics for a project.

        Args:
            project_id: Project ID.

        Returns:
            List of metrics with spans loaded.
        """
        result = await self.db.execute(
            select(Metric)
            .options(selectinload(Metric.span))
            .where(Metric.project_id == project_id)
            .order_by(Metric.created_at)
        )
        return list(result.scalars().all())

    # =========================================================================
    # Evidence Packs
    # =========================================================================

    async def create_evidence_pack(
        self,
        project: Project,
        name: str,
        description: str | None = None,
        created_by: str | None = None,
        metadata: dict | None = None,
    ) -> EvidencePack:
        """Create an evidence pack.

        Args:
            project: Project context.
            name: Pack name.
            description: Optional description.
            created_by: Creator ID.
            metadata: Optional metadata.

        Returns:
            Created evidence pack.
        """
        pack = EvidencePack(
            project_id=project.id,
            name=name,
            description=description,
            created_by=created_by,
            metadata_=metadata or {},
        )
        self.db.add(pack)
        await self.db.flush()
        return pack

    async def add_item_to_pack(
        self,
        pack: EvidencePack,
        span: Span,
        claim: Claim | None = None,
        metric: Metric | None = None,
        order_index: int = 0,
        notes: str | None = None,
    ) -> EvidencePackItem:
        """Add an item to an evidence pack.

        Args:
            pack: Evidence pack.
            span: Required span.
            claim: Optional claim.
            metric: Optional metric.
            order_index: Position in pack.
            notes: Optional notes.

        Returns:
            Created evidence pack item.
        """
        item = EvidencePackItem(
            evidence_pack_id=pack.id,
            span_id=span.id,
            claim_id=claim.id if claim else None,
            metric_id=metric.id if metric else None,
            order_index=order_index,
            notes=notes,
        )
        self.db.add(item)
        await self.db.flush()
        return item

    async def get_evidence_pack(
        self, pack_id: uuid.UUID
    ) -> EvidencePack | None:
        """Get an evidence pack with all items.

        Args:
            pack_id: Pack ID.

        Returns:
            Evidence pack with items loaded.
        """
        result = await self.db.execute(
            select(EvidencePack)
            .options(
                selectinload(EvidencePack.items).selectinload(EvidencePackItem.span),
                selectinload(EvidencePack.items).selectinload(EvidencePackItem.claim),
                selectinload(EvidencePack.items).selectinload(EvidencePackItem.metric),
            )
            .where(EvidencePack.id == pack_id)
        )
        return result.scalar_one_or_none()

    async def export_evidence_pack(
        self, pack_id: uuid.UUID
    ) -> EvidencePackExport | None:
        """Export an evidence pack to a structured format.

        Args:
            pack_id: Pack ID.

        Returns:
            EvidencePackExport or None if not found.
        """
        pack = await self.get_evidence_pack(pack_id)
        if not pack:
            return None

        items = []
        for item in pack.items:
            export_item = {
                "order": item.order_index,
                "notes": item.notes,
                "span": {
                    "id": str(item.span.id),
                    "text": item.span.text_content,
                    "type": item.span.span_type.value,
                    "locator": item.span.start_locator,
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

            items.append(export_item)

        return EvidencePackExport(
            pack_id=pack.id,
            name=pack.name,
            description=pack.description,
            project_id=pack.project_id,
            items=items,
            item_count=len(items),
        )

    async def get_packs_for_project(
        self, project_id: uuid.UUID
    ) -> list[EvidencePack]:
        """Get all evidence packs for a project.

        Args:
            project_id: Project ID.

        Returns:
            List of evidence packs.
        """
        result = await self.db.execute(
            select(EvidencePack)
            .options(selectinload(EvidencePack.items))
            .where(EvidencePack.project_id == project_id)
            .order_by(EvidencePack.created_at.desc())
        )
        return list(result.scalars().all())
