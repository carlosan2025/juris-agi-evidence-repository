"""Span generation module.

Provides span generators for various document types:
- TextSpanGenerator: PDF/text documents with character offsets
- CsvSpanGenerator: CSV files with row/column ranges
- ExcelSpanGenerator: Excel workbooks with sheet/cell ranges
- ImageSpanGenerator: Images with OCR text if available
"""

from evidence_repository.spans.base import (
    BaseSpanGenerator,
    CsvLocator,
    ExcelLocator,
    ImageLocator,
    SpanData,
    TextLocator,
)
from evidence_repository.spans.csv_span_generator import CsvSpanGenerator
from evidence_repository.spans.excel_span_generator import ExcelSpanGenerator
from evidence_repository.spans.image_span_generator import ImageSpanGenerator
from evidence_repository.spans.service import SpanGenerationService
from evidence_repository.spans.text_span_generator import TextSpanGenerator

__all__ = [
    # Base classes
    "BaseSpanGenerator",
    "SpanData",
    # Locators
    "TextLocator",
    "CsvLocator",
    "ExcelLocator",
    "ImageLocator",
    # Generators
    "TextSpanGenerator",
    "CsvSpanGenerator",
    "ExcelSpanGenerator",
    "ImageSpanGenerator",
    # Service
    "SpanGenerationService",
]
