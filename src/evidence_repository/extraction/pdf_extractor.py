"""PDF text extractor using LovePDF API."""

import asyncio
import logging
import tempfile
import time
from pathlib import Path
from typing import Any

from evidence_repository.config import get_settings
from evidence_repository.extraction.base import BaseExtractor, ExtractionArtifact, ExtractedImage
from evidence_repository.extraction.lovepdf import LovePDFClient, LovePDFError

logger = logging.getLogger(__name__)


class PdfExtractor(BaseExtractor):
    """Extractor for PDF documents.

    Uses LovePDF API as the primary extraction method with pypdf as fallback.
    Supports:
    - Text extraction from all pages
    - Page count detection
    - Image extraction (optional)
    - Metadata extraction
    """

    def __init__(self, lovepdf_client: LovePDFClient | None = None, extract_images: bool = False):
        """Initialize PDF extractor.

        Args:
            lovepdf_client: Optional LovePDF client instance.
            extract_images: Whether to extract embedded images.
        """
        if lovepdf_client:
            self._lovepdf = lovepdf_client
        else:
            settings = get_settings()
            self._lovepdf = LovePDFClient(
                public_key=settings.lovepdf_public_key,
                secret_key=settings.lovepdf_secret_key,
            )
        self._extract_images = extract_images

    @property
    def name(self) -> str:
        return "pdf"

    @property
    def supported_content_types(self) -> list[str]:
        return ["application/pdf"]

    @property
    def version(self) -> str:
        return "1.0.0"

    async def extract(
        self,
        data: bytes,
        filename: str,
        content_type: str,
        output_dir: Path | None = None,
    ) -> ExtractionArtifact:
        """Extract content from a PDF document.

        Args:
            data: Raw PDF bytes.
            filename: Original filename.
            content_type: MIME type (should be application/pdf).
            output_dir: Directory to store extracted images.

        Returns:
            ExtractionArtifact with text, images, and metadata.
        """
        start_time = time.time()
        artifact = self._create_artifact()

        settings = get_settings()
        text = ""
        page_count = 0
        images: list[ExtractedImage] = []
        metadata: dict[str, Any] = {"filename": filename}

        # Try LovePDF first if configured
        if settings.lovepdf_public_key and settings.lovepdf_secret_key:
            try:
                result = await self._lovepdf.extract_text(data)
                text = result.text
                page_count = result.page_count
                metadata.update(result.metadata)
                metadata["extraction_method"] = "lovepdf"
            except LovePDFError as e:
                logger.warning(f"LovePDF extraction failed, trying fallback: {e}")
                artifact.warnings.append(f"LovePDF failed: {str(e)}")

        # Fallback to pypdf if LovePDF failed or not configured
        if not text:
            text, page_count, images, pdf_metadata = await self._extract_with_pypdf(
                data, output_dir
            )
            metadata.update(pdf_metadata)
            metadata["extraction_method"] = "pypdf"

        # Calculate processing time
        processing_time_ms = int((time.time() - start_time) * 1000)

        # Build artifact
        artifact.text = text
        artifact.page_count = page_count
        artifact.images = images
        artifact.metadata = metadata
        artifact.processing_time_ms = processing_time_ms

        return artifact

    async def _extract_with_pypdf(
        self,
        data: bytes,
        output_dir: Path | None = None,
    ) -> tuple[str, int, list[ExtractedImage], dict[str, Any]]:
        """Extract text and images using pypdf.

        Args:
            data: PDF file content.
            output_dir: Directory to store extracted images.

        Returns:
            Tuple of (text, page_count, images, metadata).
        """
        try:
            import pypdf
        except ImportError:
            logger.warning("pypdf not installed, cannot extract PDF")
            return "", 0, [], {"error": "pypdf not installed"}

        def extract() -> tuple[str, int, list[ExtractedImage], dict[str, Any]]:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
                f.write(data)
                temp_path = Path(f.name)

            try:
                reader = pypdf.PdfReader(temp_path)
                text_parts: list[str] = []
                images: list[ExtractedImage] = []
                image_index = 0

                for page_num, page in enumerate(reader.pages):
                    # Extract text
                    page_text = page.extract_text() or ""
                    text_parts.append(page_text)

                    # Extract images if enabled
                    if self._extract_images and output_dir:
                        for image_obj in page.images:
                            try:
                                image_data = image_obj.data
                                image_name = f"page{page_num + 1}_img{image_index}.png"
                                image_path = output_dir / image_name

                                # Write image file
                                with open(image_path, "wb") as img_file:
                                    img_file.write(image_data)

                                images.append(ExtractedImage(
                                    image_index=image_index,
                                    content_type="image/png",
                                    page_number=page_num + 1,
                                    storage_path=str(image_path),
                                ))
                                image_index += 1
                            except Exception as e:
                                logger.warning(f"Failed to extract image: {e}")

                # Extract metadata
                pdf_metadata: dict[str, Any] = {}
                if reader.metadata:
                    pdf_metadata = {
                        "title": reader.metadata.title,
                        "author": reader.metadata.author,
                        "subject": reader.metadata.subject,
                        "creator": reader.metadata.creator,
                        "producer": reader.metadata.producer,
                    }
                    # Filter out None values
                    pdf_metadata = {k: v for k, v in pdf_metadata.items() if v}

                return (
                    "\n\n".join(text_parts),
                    len(reader.pages),
                    images,
                    pdf_metadata,
                )
            finally:
                temp_path.unlink(missing_ok=True)

        return await asyncio.to_thread(extract)
