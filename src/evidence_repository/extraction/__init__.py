"""Document extraction module.

Provides extractors for various document types:
- PdfExtractor: PDF documents via LovePDF or pypdf
- TextExtractor: Plain text and markdown files
- CsvExtractor: CSV files with auto-delimiter detection
- ExcelExtractor: Excel workbooks (.xlsx, .xls)
- ImageExtractor: Images with optional OCR
"""

from evidence_repository.extraction.base import (
    BaseExtractor,
    ExtractionArtifact,
    ExtractedImage,
    ExtractionStatus,
    NoOpOCRProvider,
    OCRProvider,
    TableData,
)
from evidence_repository.extraction.csv_extractor import CsvExtractor
from evidence_repository.extraction.excel_extractor import ExcelExtractor
from evidence_repository.extraction.extractor_service import ExtractorService
from evidence_repository.extraction.image_extractor import ImageExtractor, TesseractOCRProvider
from evidence_repository.extraction.lovepdf import LovePDFClient, LovePDFError
from evidence_repository.extraction.pdf_extractor import PdfExtractor
from evidence_repository.extraction.service import ExtractionService as LegacyExtractionService
from evidence_repository.extraction.text_extractor import TextExtractor

__all__ = [
    # Base classes
    "BaseExtractor",
    "ExtractionArtifact",
    "ExtractedImage",
    "ExtractionStatus",
    "TableData",
    # OCR providers
    "OCRProvider",
    "NoOpOCRProvider",
    "TesseractOCRProvider",
    # Extractors
    "PdfExtractor",
    "TextExtractor",
    "CsvExtractor",
    "ExcelExtractor",
    "ImageExtractor",
    # Services
    "ExtractorService",
    "LegacyExtractionService",
    # LovePDF
    "LovePDFClient",
    "LovePDFError",
]
