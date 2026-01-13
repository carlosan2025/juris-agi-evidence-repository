"""Evidence-related schemas (Span, Claim, Metric, EvidencePack)."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from evidence_repository.schemas.common import BaseSchema


# =============================================================================
# Locator Schemas
# =============================================================================


class PDFBoundingBox(BaseModel):
    """Bounding box for PDF location."""

    x1: float = Field(..., description="Left coordinate")
    y1: float = Field(..., description="Top coordinate")
    x2: float = Field(..., description="Right coordinate")
    y2: float = Field(..., description="Bottom coordinate")


class PDFLocator(BaseModel):
    """Locator for PDF documents."""

    type: Literal["pdf"] = "pdf"
    page: int = Field(..., ge=1, description="Page number (1-indexed)")
    bbox: PDFBoundingBox | None = Field(
        default=None, description="Bounding box on page"
    )


class SpreadsheetLocator(BaseModel):
    """Locator for spreadsheet documents."""

    type: Literal["spreadsheet"] = "spreadsheet"
    sheet: str = Field(..., description="Sheet name")
    cell_range: str = Field(..., description="Cell range (e.g., 'A1:D10')")


class TextLocator(BaseModel):
    """Locator for plain text/PDF documents with character offsets."""

    type: Literal["text"] = "text"
    offset_start: int = Field(..., ge=0, description="Start character offset")
    offset_end: int = Field(..., ge=0, description="End character offset")
    page_hint: int | None = Field(default=None, ge=1, description="Page number hint")


class CsvLocator(BaseModel):
    """Locator for CSV files with row/column ranges."""

    type: Literal["csv"] = "csv"
    row_start: int = Field(..., ge=0, description="Start row index (0-based)")
    row_end: int = Field(..., ge=0, description="End row index (exclusive)")
    col_start: int = Field(default=0, ge=0, description="Start column index")
    col_end: int = Field(..., ge=0, description="End column index (exclusive)")
    table_index: int | None = Field(default=None, description="Table index if multiple")


class ExcelLocator(BaseModel):
    """Locator for Excel files with sheet and cell range."""

    type: Literal["excel"] = "excel"
    sheet: str = Field(..., description="Sheet name")
    cell_range: str = Field(..., description="Cell range (e.g., 'A2:D10')")


class ImageLocator(BaseModel):
    """Locator for image files."""

    type: Literal["image"] = "image"
    filename: str = Field(..., description="Image filename")
    image_index: int = Field(default=0, ge=0, description="Image index")
    width: int | None = Field(default=None, description="Image width in pixels")
    height: int | None = Field(default=None, description="Image height in pixels")
    page_number: int | None = Field(default=None, description="Source page number")


LocatorSchema = PDFLocator | SpreadsheetLocator | TextLocator | CsvLocator | ExcelLocator | ImageLocator


# =============================================================================
# Span Schemas
# =============================================================================


class SpanCreate(BaseModel):
    """Request schema for creating a span."""

    document_version_id: UUID = Field(..., description="Document version ID")
    start_locator: dict[str, Any] = Field(
        ..., description="Start position locator (JSON)"
    )
    end_locator: dict[str, Any] | None = Field(
        default=None, description="End position locator (JSON)"
    )
    text_content: str = Field(..., min_length=1, description="Text content of the span")
    span_type: str = Field(default="text", description="Type of span")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )

    @field_validator("span_type")
    @classmethod
    def validate_span_type(cls, v: str) -> str:
        """Validate span type."""
        valid_types = {"text", "table", "figure", "citation", "heading", "footnote", "other"}
        if v.lower() not in valid_types:
            raise ValueError(f"Invalid span type. Must be one of: {valid_types}")
        return v.lower()


class SpanResponse(BaseSchema):
    """Response schema for span."""

    id: UUID = Field(..., description="Span ID")
    document_version_id: UUID = Field(..., description="Document version ID")
    start_locator: dict[str, Any] = Field(..., description="Start position locator")
    end_locator: dict[str, Any] | None = Field(
        default=None, description="End position locator"
    )
    text_content: str = Field(..., description="Text content")
    span_type: str = Field(..., description="Type of span")
    created_at: datetime = Field(..., description="Creation timestamp")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata",
        alias="metadata_",
    )


# =============================================================================
# Claim Schemas
# =============================================================================


class ClaimCreate(BaseModel):
    """Request schema for creating a claim."""

    project_id: UUID = Field(..., description="Project ID")
    span_id: UUID = Field(..., description="Evidence span ID")
    claim_text: str = Field(..., min_length=1, description="The claim text")
    claim_type: str | None = Field(
        default=None, max_length=100, description="Type of claim"
    )
    confidence: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Confidence score (0-1)"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )


class ClaimResponse(BaseSchema):
    """Response schema for claim."""

    id: UUID = Field(..., description="Claim ID")
    project_id: UUID = Field(..., description="Project ID")
    span_id: UUID = Field(..., description="Evidence span ID")
    claim_text: str = Field(..., description="The claim text")
    claim_type: str | None = Field(default=None, description="Type of claim")
    confidence: float | None = Field(default=None, description="Confidence score")
    created_at: datetime = Field(..., description="Creation timestamp")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata",
        alias="metadata_",
    )

    # Include span details for context
    span: SpanResponse | None = Field(default=None, description="Evidence span")


# =============================================================================
# Metric Schemas
# =============================================================================


class MetricCreate(BaseModel):
    """Request schema for creating a metric."""

    project_id: UUID = Field(..., description="Project ID")
    span_id: UUID = Field(..., description="Evidence span ID")
    metric_name: str = Field(..., min_length=1, max_length=255, description="Metric name")
    metric_value: str = Field(..., max_length=255, description="Metric value")
    unit: str | None = Field(default=None, max_length=100, description="Unit of measure")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )


class MetricResponse(BaseSchema):
    """Response schema for metric."""

    id: UUID = Field(..., description="Metric ID")
    project_id: UUID = Field(..., description="Project ID")
    span_id: UUID = Field(..., description="Evidence span ID")
    metric_name: str = Field(..., description="Metric name")
    metric_value: str = Field(..., description="Metric value")
    unit: str | None = Field(default=None, description="Unit of measure")
    created_at: datetime = Field(..., description="Creation timestamp")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata",
        alias="metadata_",
    )

    # Include span details for context
    span: SpanResponse | None = Field(default=None, description="Evidence span")


# =============================================================================
# Evidence Pack Schemas
# =============================================================================


class EvidencePackCreate(BaseModel):
    """Request schema for creating an evidence pack."""

    project_id: UUID = Field(..., description="Project ID")
    name: str = Field(..., min_length=1, max_length=255, description="Pack name")
    description: str | None = Field(default=None, description="Pack description")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )


class EvidencePackItemCreate(BaseModel):
    """Request schema for adding item to evidence pack."""

    span_id: UUID = Field(..., description="Span ID (required)")
    claim_id: UUID | None = Field(default=None, description="Optional claim ID")
    metric_id: UUID | None = Field(default=None, description="Optional metric ID")
    order_index: int = Field(default=0, ge=0, description="Order in pack")
    notes: str | None = Field(default=None, description="Additional notes")


class EvidencePackItemResponse(BaseSchema):
    """Response schema for evidence pack item."""

    id: UUID = Field(..., description="Item ID")
    evidence_pack_id: UUID = Field(..., description="Parent pack ID")
    span_id: UUID = Field(..., description="Span ID")
    claim_id: UUID | None = Field(default=None, description="Claim ID")
    metric_id: UUID | None = Field(default=None, description="Metric ID")
    order_index: int = Field(..., description="Order in pack")
    notes: str | None = Field(default=None, description="Notes")
    created_at: datetime = Field(..., description="Creation timestamp")

    # Include referenced entities
    span: SpanResponse | None = Field(default=None, description="Span details")
    claim: ClaimResponse | None = Field(default=None, description="Claim details")
    metric: MetricResponse | None = Field(default=None, description="Metric details")


class EvidencePackResponse(BaseSchema):
    """Response schema for evidence pack."""

    id: UUID = Field(..., description="Pack ID")
    project_id: UUID = Field(..., description="Project ID")
    name: str = Field(..., description="Pack name")
    description: str | None = Field(default=None, description="Pack description")
    created_by: str | None = Field(default=None, description="Creator ID")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata",
        alias="metadata_",
    )

    # Include items
    items: list[EvidencePackItemResponse] = Field(
        default_factory=list, description="Pack items"
    )
    item_count: int = Field(default=0, description="Number of items in pack")
