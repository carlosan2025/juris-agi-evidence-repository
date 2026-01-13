"""LovePDF API client for PDF text extraction."""

import asyncio
import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)


@dataclass
class ExtractionResult:
    """Result of text extraction from a PDF."""

    text: str
    page_count: int
    metadata: dict


class LovePDFError(Exception):
    """Error from LovePDF API."""

    pass


class LovePDFClient:
    """Client for LovePDF API to extract text from PDFs.

    LovePDF provides high-quality PDF text extraction as a service.
    This is the canonical PDF-to-text stage for the Evidence Repository.

    API Documentation: https://developer.ilovepdf.com/docs/api-reference

    Usage:
        client = LovePDFClient(public_key="...", secret_key="...")
        result = await client.extract_text(pdf_bytes)
        print(result.text)
    """

    BASE_URL = "https://api.ilovepdf.com/v1"

    def __init__(self, public_key: str, secret_key: str):
        """Initialize LovePDF client.

        Args:
            public_key: LovePDF API public key.
            secret_key: LovePDF API secret key.
        """
        self.public_key = public_key
        self.secret_key = secret_key
        self._token: str | None = None

    async def _get_auth_token(self) -> str:
        """Get authentication token from LovePDF.

        Returns:
            JWT token for API requests.
        """
        if not self.public_key or not self.secret_key:
            raise LovePDFError(
                "LovePDF credentials not configured. "
                "Set LOVEPDF_PUBLIC_KEY and LOVEPDF_SECRET_KEY environment variables."
            )

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.BASE_URL}/auth",
                json={"public_key": self.public_key},
            )

            if response.status_code != 200:
                raise LovePDFError(f"Authentication failed: {response.text}")

            data = response.json()
            self._token = data["token"]
            return self._token

    async def _ensure_token(self) -> str:
        """Ensure we have a valid auth token."""
        if not self._token:
            return await self._get_auth_token()
        return self._token

    async def extract_text(self, pdf_data: bytes) -> ExtractionResult:
        """Extract text from a PDF file.

        Uses LovePDF's PDF to text conversion API.

        Args:
            pdf_data: PDF file content as bytes.

        Returns:
            ExtractionResult with extracted text and metadata.

        Raises:
            LovePDFError: If extraction fails.
        """
        token = await self._ensure_token()

        async with httpx.AsyncClient(timeout=120.0) as client:
            # Step 1: Start a new task
            headers = {"Authorization": f"Bearer {token}"}

            start_response = await client.get(
                f"{self.BASE_URL}/start/pdftotxt",
                headers=headers,
            )

            if start_response.status_code != 200:
                raise LovePDFError(f"Failed to start task: {start_response.text}")

            task_data = start_response.json()
            server = task_data["server"]
            task_id = task_data["task"]

            # Step 2: Upload the PDF
            upload_url = f"https://{server}/v1/upload"
            files = {"file": ("document.pdf", pdf_data, "application/pdf")}

            upload_response = await client.post(
                upload_url,
                headers=headers,
                files=files,
                data={"task": task_id},
            )

            if upload_response.status_code != 200:
                raise LovePDFError(f"Failed to upload file: {upload_response.text}")

            upload_data = upload_response.json()
            server_filename = upload_data["server_filename"]

            # Step 3: Process the PDF
            process_url = f"https://{server}/v1/process"
            process_response = await client.post(
                process_url,
                headers=headers,
                json={
                    "task": task_id,
                    "tool": "pdftotxt",
                    "files": [{"server_filename": server_filename, "filename": "document.pdf"}],
                },
            )

            if process_response.status_code != 200:
                raise LovePDFError(f"Failed to process file: {process_response.text}")

            # Step 4: Download the result
            download_url = f"https://{server}/v1/download/{task_id}"
            download_response = await client.get(download_url, headers=headers)

            if download_response.status_code != 200:
                raise LovePDFError(f"Failed to download result: {download_response.text}")

            # The response is a text file
            text = download_response.text

            return ExtractionResult(
                text=text,
                page_count=0,  # LovePDF doesn't return page count in this flow
                metadata={"tool": "lovepdf", "task_id": task_id},
            )

    async def extract_text_fallback(self, pdf_data: bytes) -> ExtractionResult:
        """Fallback text extraction using pypdf.

        Used when LovePDF is not configured or unavailable.

        Args:
            pdf_data: PDF file content.

        Returns:
            ExtractionResult with extracted text.
        """
        try:
            import pypdf
        except ImportError:
            logger.warning("pypdf not installed, cannot perform fallback extraction")
            return ExtractionResult(
                text="",
                page_count=0,
                metadata={"error": "pypdf not installed"},
            )

        def extract() -> ExtractionResult:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
                f.write(pdf_data)
                temp_path = Path(f.name)

            try:
                reader = pypdf.PdfReader(temp_path)
                text_parts = []

                for page in reader.pages:
                    text_parts.append(page.extract_text() or "")

                return ExtractionResult(
                    text="\n\n".join(text_parts),
                    page_count=len(reader.pages),
                    metadata={"tool": "pypdf"},
                )
            finally:
                temp_path.unlink(missing_ok=True)

        return await asyncio.to_thread(extract)
