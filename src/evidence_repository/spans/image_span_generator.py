"""Image span generator for image files."""

from typing import Any

from evidence_repository.spans.base import BaseSpanGenerator, SpanData


class ImageSpanGenerator(BaseSpanGenerator):
    """Span generator for image files.

    Generates a single span per image with:
    - Image metadata (filename, dimensions)
    - OCR text if available
    - Storage path reference

    Rules:
    - Each image produces exactly one span
    - Span type is "figure"
    - OCR text is included if extracted
    - Locator contains image identification info
    """

    @property
    def name(self) -> str:
        return "image"

    @property
    def supported_content_types(self) -> list[str]:
        return [
            "image/png",
            "image/jpeg",
            "image/gif",
            "image/webp",
            "image/tiff",
            "image/bmp",
        ]

    def generate_spans(
        self,
        text: str | None,
        tables: list[dict[str, Any]] | None,
        images: list[dict[str, Any]] | None,
        metadata: dict[str, Any],
    ) -> list[SpanData]:
        """Generate spans from image data.

        For standalone images, creates a single span.
        For embedded images (from PDF extraction), creates one span per image.

        Args:
            text: OCR text from standalone image (if any).
            tables: Not used for image spans.
            images: List of image data dicts from extraction.
            metadata: Extraction metadata including filename.

        Returns:
            List of SpanData objects.
        """
        spans: list[SpanData] = []

        # Handle standalone image (no images list, just text from OCR)
        if not images and text is not None:
            span = self._create_standalone_image_span(text, metadata)
            if span:
                spans.append(span)
            return spans

        # Handle extracted images (from PDF or other documents)
        if images:
            for image in images:
                span = self._create_embedded_image_span(image, metadata)
                if span:
                    spans.append(span)

        return spans

    def _create_standalone_image_span(
        self,
        text: str | None,
        metadata: dict[str, Any],
    ) -> SpanData | None:
        """Create a span for a standalone image file.

        Args:
            text: OCR text (if any).
            metadata: Extraction metadata.

        Returns:
            SpanData or None if no content.
        """
        filename = metadata.get("filename", "image")
        width = metadata.get("width")
        height = metadata.get("height")
        content_type = metadata.get("content_type", "image/unknown")

        # Build text content
        text_content = self._build_text_content(
            filename=filename,
            ocr_text=text,
            width=width,
            height=height,
        )

        # Create locator
        locator: dict[str, Any] = {
            "type": "image",
            "filename": filename,
            "image_index": 0,
        }
        if width is not None:
            locator["width"] = width
        if height is not None:
            locator["height"] = height

        return SpanData(
            text_content=text_content,
            locator=locator,
            span_type="figure",
            metadata={
                "filename": filename,
                "content_type": content_type,
                "width": width,
                "height": height,
                "has_ocr": bool(text),
            },
        )

    def _create_embedded_image_span(
        self,
        image: dict[str, Any],
        metadata: dict[str, Any],
    ) -> SpanData | None:
        """Create a span for an embedded/extracted image.

        Args:
            image: Image data dict from extraction.
            metadata: Document metadata.

        Returns:
            SpanData or None if no content.
        """
        image_index = image.get("image_index", 0)
        content_type = image.get("content_type", "image/unknown")
        width = image.get("width")
        height = image.get("height")
        page_number = image.get("page_number")
        storage_path = image.get("storage_path")
        ocr_text = image.get("ocr_text")

        # Generate filename from storage path or index
        if storage_path:
            from pathlib import Path
            filename = Path(storage_path).name
        else:
            filename = f"image_{image_index}"

        # Build text content
        text_content = self._build_text_content(
            filename=filename,
            ocr_text=ocr_text,
            width=width,
            height=height,
            page_number=page_number,
        )

        # Create locator
        locator: dict[str, Any] = {
            "type": "image",
            "filename": filename,
            "image_index": image_index,
        }
        if width is not None:
            locator["width"] = width
        if height is not None:
            locator["height"] = height
        if page_number is not None:
            locator["page_number"] = page_number

        return SpanData(
            text_content=text_content,
            locator=locator,
            span_type="figure",
            metadata={
                "filename": filename,
                "content_type": content_type,
                "width": width,
                "height": height,
                "page_number": page_number,
                "storage_path": storage_path,
                "has_ocr": bool(ocr_text),
            },
        )

    def _build_text_content(
        self,
        filename: str,
        ocr_text: str | None = None,
        width: int | None = None,
        height: int | None = None,
        page_number: int | None = None,
    ) -> str:
        """Build text representation of an image span.

        Args:
            filename: Image filename.
            ocr_text: OCR-extracted text (if any).
            width: Image width in pixels.
            height: Image height in pixels.
            page_number: Source page number (for embedded images).

        Returns:
            Text representation.
        """
        parts: list[str] = []

        # Image identifier
        parts.append(f"[Image: {filename}]")

        # Dimensions
        if width and height:
            parts.append(f"Dimensions: {width}x{height}")

        # Source page
        if page_number:
            parts.append(f"Source page: {page_number}")

        # OCR text
        if ocr_text:
            parts.append("")
            parts.append("OCR Text:")
            parts.append(ocr_text)

        return "\n".join(parts)
