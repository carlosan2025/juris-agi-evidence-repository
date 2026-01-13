"""Image extractor with pluggable OCR support."""

import asyncio
import logging
import time
from pathlib import Path
from typing import Any

from evidence_repository.extraction.base import (
    BaseExtractor,
    ExtractionArtifact,
    ExtractedImage,
    NoOpOCRProvider,
    OCRProvider,
)

logger = logging.getLogger(__name__)


class ImageExtractor(BaseExtractor):
    """Extractor for image files.

    Stores image metadata and optionally extracts text via OCR.
    Supports pluggable OCR providers:
    - NoOpOCRProvider (default): No OCR, just stores image
    - TesseractOCRProvider: Local Tesseract OCR
    - CloudOCRProvider: Cloud-based OCR services

    Supported formats:
    - PNG, JPEG, GIF, WebP, TIFF, BMP
    """

    # Image format metadata
    FORMAT_INFO = {
        "image/png": {"extension": ".png", "format": "PNG"},
        "image/jpeg": {"extension": ".jpg", "format": "JPEG"},
        "image/gif": {"extension": ".gif", "format": "GIF"},
        "image/webp": {"extension": ".webp", "format": "WebP"},
        "image/tiff": {"extension": ".tiff", "format": "TIFF"},
        "image/bmp": {"extension": ".bmp", "format": "BMP"},
    }

    def __init__(self, ocr_provider: OCRProvider | None = None):
        """Initialize image extractor.

        Args:
            ocr_provider: OCR provider for text extraction. Defaults to NoOpOCRProvider.
        """
        self._ocr = ocr_provider or NoOpOCRProvider()

    @property
    def name(self) -> str:
        return "image"

    @property
    def supported_content_types(self) -> list[str]:
        return list(self.FORMAT_INFO.keys())

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
        """Extract content from an image file.

        Args:
            data: Raw image bytes.
            filename: Original filename.
            content_type: MIME type.
            output_dir: Directory to store the image copy.

        Returns:
            ExtractionArtifact with image info and optional OCR text.
        """
        start_time = time.time()
        artifact = self._create_artifact()

        # Get image dimensions
        width, height = await self._get_image_dimensions(data, content_type)

        # Store image if output directory provided
        storage_path: str | None = None
        if output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)
            format_info = self.FORMAT_INFO.get(content_type, {"extension": ".bin"})
            image_filename = f"image_0{format_info.get('extension', '.bin')}"
            image_path = output_dir / image_filename
            with open(image_path, "wb") as f:
                f.write(data)
            storage_path = str(image_path)

        # Run OCR if provider is configured
        ocr_text = ""
        if not isinstance(self._ocr, NoOpOCRProvider):
            try:
                ocr_text = await self._ocr.extract_text(data, content_type)
            except Exception as e:
                logger.warning(f"OCR extraction failed: {e}")
                artifact.warnings.append(f"OCR failed: {str(e)}")

        # Create image record
        extracted_image = ExtractedImage(
            image_index=0,
            content_type=content_type,
            width=width,
            height=height,
            storage_path=storage_path,
            ocr_text=ocr_text if ocr_text else None,
            metadata={
                "filename": filename,
                "format": self.FORMAT_INFO.get(content_type, {}).get("format", "Unknown"),
                "file_size": len(data),
            },
        )

        # Calculate processing time
        processing_time_ms = int((time.time() - start_time) * 1000)

        # Build artifact
        artifact.text = ocr_text if ocr_text else None
        artifact.images = [extracted_image]
        artifact.metadata = {
            "filename": filename,
            "content_type": content_type,
            "width": width,
            "height": height,
            "file_size": len(data),
            "ocr_provider": self._ocr.name,
            "has_ocr_text": bool(ocr_text),
        }
        artifact.processing_time_ms = processing_time_ms

        return artifact

    async def _get_image_dimensions(
        self,
        data: bytes,
        content_type: str,
    ) -> tuple[int | None, int | None]:
        """Get image dimensions.

        Args:
            data: Raw image bytes.
            content_type: MIME type.

        Returns:
            Tuple of (width, height) or (None, None) if unable to determine.
        """
        try:
            from PIL import Image
            import io

            def get_dims() -> tuple[int, int]:
                img = Image.open(io.BytesIO(data))
                return img.size

            return await asyncio.to_thread(get_dims)
        except ImportError:
            logger.debug("PIL not installed, cannot get image dimensions")
            return None, None
        except Exception as e:
            logger.warning(f"Failed to get image dimensions: {e}")
            return None, None


class TesseractOCRProvider(OCRProvider):
    """OCR provider using Tesseract.

    Requires tesseract to be installed on the system.
    """

    def __init__(self, tesseract_cmd: str | None = None):
        """Initialize Tesseract OCR provider.

        Args:
            tesseract_cmd: Path to tesseract executable. Auto-detected if not provided.
        """
        self._tesseract_cmd = tesseract_cmd

    @property
    def name(self) -> str:
        return "tesseract"

    async def extract_text(
        self,
        image_data: bytes,
        content_type: str,
        language: str = "eng",
    ) -> str:
        """Extract text from image using Tesseract.

        Args:
            image_data: Raw image bytes.
            content_type: MIME type.
            language: Language code for OCR.

        Returns:
            Extracted text.
        """
        try:
            import pytesseract
            from PIL import Image
            import io

            if self._tesseract_cmd:
                pytesseract.pytesseract.tesseract_cmd = self._tesseract_cmd

            def run_ocr() -> str:
                img = Image.open(io.BytesIO(image_data))
                return pytesseract.image_to_string(img, lang=language)

            return await asyncio.to_thread(run_ocr)

        except ImportError as e:
            raise RuntimeError(f"Tesseract dependencies not installed: {e}")
        except Exception as e:
            raise RuntimeError(f"Tesseract OCR failed: {e}")
