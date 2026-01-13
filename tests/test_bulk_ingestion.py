"""Unit tests for bulk ingestion functionality."""

import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from evidence_repository.models.ingestion import (
    IngestionBatch,
    IngestionBatchStatus,
    IngestionItem,
    IngestionItemStatus,
    IngestionSource,
)
from evidence_repository.utils.security import (
    SSRFProtectionError,
    is_private_ip,
    sanitize_filename,
    validate_url_for_ssrf,
)


# =============================================================================
# SSRF Protection Tests
# =============================================================================


class TestSSRFProtection:
    """Tests for SSRF protection utilities."""

    def test_private_ipv4_addresses(self):
        """Should detect private IPv4 addresses."""
        private_ips = [
            "10.0.0.1",
            "10.255.255.255",
            "172.16.0.1",
            "172.31.255.255",
            "192.168.0.1",
            "192.168.255.255",
        ]
        for ip in private_ips:
            assert is_private_ip(ip) is True, f"{ip} should be private"

    def test_loopback_addresses(self):
        """Should detect loopback addresses."""
        loopback_ips = [
            "127.0.0.1",
            "127.0.0.255",
            "127.255.255.255",
        ]
        for ip in loopback_ips:
            assert is_private_ip(ip) is True, f"{ip} should be loopback"

    def test_public_ipv4_addresses(self):
        """Should allow public IPv4 addresses."""
        public_ips = [
            "8.8.8.8",
            "1.1.1.1",
            "93.184.216.34",  # example.com
        ]
        for ip in public_ips:
            assert is_private_ip(ip) is False, f"{ip} should be public"

    def test_link_local_addresses(self):
        """Should detect link-local addresses."""
        assert is_private_ip("169.254.0.1") is True
        assert is_private_ip("169.254.255.255") is True

    def test_ipv6_loopback(self):
        """Should detect IPv6 loopback."""
        assert is_private_ip("::1") is True

    def test_blocked_hostnames(self):
        """Should block dangerous hostnames."""
        blocked_urls = [
            "http://localhost/file.pdf",
            "http://127.0.0.1/file.pdf",
            "http://169.254.169.254/metadata",  # AWS metadata
            "http://metadata.google.internal/",
        ]
        for url in blocked_urls:
            with pytest.raises(SSRFProtectionError):
                validate_url_for_ssrf(url)

    def test_blocked_internal_domains(self):
        """Should block internal domain patterns."""
        blocked_urls = [
            "http://api.internal/resource",
            "http://db.local/",
            "http://server.localhost/",
            "http://intranet.corp/",
            "http://router.lan/",
        ]
        for url in blocked_urls:
            with pytest.raises(SSRFProtectionError):
                validate_url_for_ssrf(url)

    def test_invalid_scheme(self):
        """Should reject non-http(s) schemes."""
        invalid_urls = [
            "ftp://example.com/file.pdf",
            "file:///etc/passwd",
            "gopher://example.com/",
            "javascript:alert(1)",
        ]
        for url in invalid_urls:
            with pytest.raises(SSRFProtectionError):
                validate_url_for_ssrf(url)

    def test_valid_public_urls(self):
        """Should allow valid public URLs."""
        # These should not raise when DNS resolves to public IP
        # In tests, we mock the DNS resolution
        with patch("socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = [(None, None, None, None, ("93.184.216.34", 0))]
            result = validate_url_for_ssrf("https://example.com/document.pdf")
            assert result == "https://example.com/document.pdf"


class TestFilenameSanitization:
    """Tests for filename sanitization."""

    def test_removes_dangerous_characters(self):
        """Should remove dangerous characters."""
        assert sanitize_filename("file<script>.txt") == "file_script_.txt"
        assert sanitize_filename("file:name.pdf") == "file_name.pdf"
        assert sanitize_filename('file"test".doc') == "file_test_.doc"

    def test_removes_path_separators(self):
        """Should remove path separators."""
        assert sanitize_filename("../../../etc/passwd") == "_.._.._.._etc_passwd"
        assert sanitize_filename("folder\\file.txt") == "folder_file.txt"

    def test_handles_empty_result(self):
        """Should handle cases that result in empty filename."""
        assert sanitize_filename("...") == "unnamed_file"
        assert sanitize_filename("   ") == "unnamed_file"

    def test_preserves_valid_characters(self):
        """Should preserve valid filename characters."""
        assert sanitize_filename("my-file_2024.pdf") == "my-file_2024.pdf"
        assert sanitize_filename("document.final.v2.txt") == "document.final.v2.txt"

    def test_limits_length(self):
        """Should limit filename length."""
        long_name = "a" * 300 + ".pdf"
        result = sanitize_filename(long_name)
        assert len(result) <= 255


# =============================================================================
# Ingestion Request Schema Tests
# =============================================================================


class TestFolderIngestionRequest:
    """Tests for folder ingestion request schema."""

    def test_valid_request(self):
        """Should accept valid folder ingestion request."""
        from evidence_repository.schemas.ingestion import FolderIngestionRequest

        request = FolderIngestionRequest(
            path="/data/documents",
            recursive=True,
            allowed_types=["pdf", "txt"],
            auto_process=True,
        )

        assert request.path == "/data/documents"
        assert request.recursive is True
        assert request.allowed_types == ["pdf", "txt"]
        assert request.auto_process is True

    def test_normalizes_extensions(self):
        """Should normalize file extensions."""
        from evidence_repository.schemas.ingestion import FolderIngestionRequest

        request = FolderIngestionRequest(
            path="/data",
            allowed_types=[".PDF", ".TXT", "csv"],
        )

        assert request.allowed_types == ["pdf", "txt", "csv"]

    def test_default_values(self):
        """Should use correct default values."""
        from evidence_repository.schemas.ingestion import FolderIngestionRequest

        request = FolderIngestionRequest(path="/data")

        assert request.recursive is True
        assert request.auto_process is True
        assert request.project_id is None


class TestURLIngestionRequest:
    """Tests for URL ingestion request schema."""

    def test_valid_request(self):
        """Should accept valid URL ingestion request."""
        from evidence_repository.schemas.ingestion import URLIngestionRequest

        request = URLIngestionRequest(
            url="https://example.com/document.pdf",
            auto_process=True,
        )

        assert request.url == "https://example.com/document.pdf"
        assert request.auto_process is True

    def test_rejects_invalid_scheme(self):
        """Should reject URLs without http/https."""
        from evidence_repository.schemas.ingestion import URLIngestionRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            URLIngestionRequest(url="ftp://example.com/file.pdf")

    def test_optional_filename(self):
        """Should allow optional filename override."""
        from evidence_repository.schemas.ingestion import URLIngestionRequest

        request = URLIngestionRequest(
            url="https://example.com/download?id=123",
            filename="custom_name.pdf",
        )

        assert request.filename == "custom_name.pdf"


# =============================================================================
# Ingestion Response Schema Tests
# =============================================================================


class TestIngestionResponses:
    """Tests for ingestion response schemas."""

    def test_folder_ingestion_response(self):
        """Should create valid folder ingestion response."""
        from evidence_repository.schemas.ingestion import FolderIngestionResponse

        response = FolderIngestionResponse(
            batch_id=uuid.uuid4(),
            job_id="job-123",
            total_files=10,
            message="Found 10 files",
        )

        assert response.batch_id is not None
        assert response.job_id == "job-123"
        assert response.total_files == 10

    def test_url_ingestion_response(self):
        """Should create valid URL ingestion response."""
        from evidence_repository.schemas.ingestion import URLIngestionResponse

        response = URLIngestionResponse(
            batch_id=uuid.uuid4(),
            item_id=uuid.uuid4(),
            job_id="job-456",
            message="URL queued",
        )

        assert response.batch_id is not None
        assert response.item_id is not None
        assert response.job_id == "job-456"

    def test_batch_response(self):
        """Should create valid batch response."""
        from evidence_repository.schemas.ingestion import IngestionBatchResponse

        response = IngestionBatchResponse(
            id=uuid.uuid4(),
            name="Test batch",
            source_type="local_folder",
            status="processing",
            total_items=50,
            processed_items=25,
            successful_items=24,
            failed_items=1,
            skipped_items=0,
            progress_percent=50.0,
            created_at=datetime.now(timezone.utc),
        )

        assert response.progress_percent == 50.0
        assert response.successful_items == 24


# =============================================================================
# Ingestion Model Tests
# =============================================================================


class TestIngestionBatchModel:
    """Tests for IngestionBatch model."""

    def test_batch_status_values(self):
        """Should have expected status values."""
        assert IngestionBatchStatus.PENDING.value == "pending"
        assert IngestionBatchStatus.PROCESSING.value == "processing"
        assert IngestionBatchStatus.COMPLETED.value == "completed"
        assert IngestionBatchStatus.PARTIAL.value == "partial"
        assert IngestionBatchStatus.FAILED.value == "failed"
        assert IngestionBatchStatus.CANCELED.value == "canceled"

    def test_source_type_values(self):
        """Should have expected source type values."""
        assert IngestionSource.FILE_UPLOAD.value == "file_upload"
        assert IngestionSource.LOCAL_FOLDER.value == "local_folder"
        assert IngestionSource.URL.value == "url"
        assert IngestionSource.S3_BUCKET.value == "s3_bucket"

    def test_progress_calculation(self):
        """Should calculate progress percentage correctly."""
        batch = IngestionBatch(
            source_type=IngestionSource.LOCAL_FOLDER,
            total_items=100,
            processed_items=50,
        )

        assert batch.progress_percent == 50.0

    def test_progress_with_zero_total(self):
        """Should handle zero total items."""
        batch = IngestionBatch(
            source_type=IngestionSource.LOCAL_FOLDER,
            total_items=0,
            processed_items=0,
        )

        assert batch.progress_percent == 0.0


class TestIngestionItemModel:
    """Tests for IngestionItem model."""

    def test_item_status_values(self):
        """Should have expected item status values."""
        assert IngestionItemStatus.PENDING.value == "pending"
        assert IngestionItemStatus.DOWNLOADING.value == "downloading"
        assert IngestionItemStatus.PROCESSING.value == "processing"
        assert IngestionItemStatus.COMPLETED.value == "completed"
        assert IngestionItemStatus.FAILED.value == "failed"
        assert IngestionItemStatus.SKIPPED.value == "skipped"

    def test_is_terminal_property(self):
        """Should correctly identify terminal states."""
        item = IngestionItem(
            batch_id=uuid.uuid4(),
            source_path="/path/to/file.pdf",
            source_filename="file.pdf",
            status=IngestionItemStatus.PENDING,
        )

        assert item.is_terminal is False

        item.status = IngestionItemStatus.PROCESSING
        assert item.is_terminal is False

        item.status = IngestionItemStatus.COMPLETED
        assert item.is_terminal is True

        item.status = IngestionItemStatus.FAILED
        assert item.is_terminal is True

        item.status = IngestionItemStatus.SKIPPED
        assert item.is_terminal is True


# =============================================================================
# Bulk Ingestion Service Tests
# =============================================================================


class TestBulkIngestionService:
    """Tests for BulkIngestionService."""

    @pytest.fixture
    def mock_storage(self):
        """Create mock storage backend."""
        return AsyncMock()

    @pytest.fixture
    def mock_db_session(self):
        """Create mock async database session."""
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()
        session.execute = AsyncMock()
        return session

    def test_scan_folder_finds_supported_files(self, mock_storage, mock_db_session, tmp_path):
        """Should find files matching allowed types."""
        # Create test files
        (tmp_path / "doc1.pdf").write_bytes(b"test pdf")
        (tmp_path / "doc2.txt").write_bytes(b"test text")
        (tmp_path / "doc3.exe").write_bytes(b"test exe")  # Should be ignored

        from evidence_repository.services.bulk_ingestion_service import BulkIngestionService

        service = BulkIngestionService(storage=mock_storage, db=mock_db_session)

        import asyncio
        files = asyncio.get_event_loop().run_until_complete(
            service.scan_folder(
                folder_path=str(tmp_path),
                recursive=False,
                allowed_types=["pdf", "txt"],
            )
        )

        assert len(files) == 2
        filenames = {f["filename"] for f in files}
        assert "doc1.pdf" in filenames
        assert "doc2.txt" in filenames
        assert "doc3.exe" not in filenames

    def test_scan_folder_recursive(self, mock_storage, mock_db_session, tmp_path):
        """Should scan subfolders when recursive=True."""
        # Create nested structure
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (tmp_path / "top.pdf").write_bytes(b"top level")
        (subdir / "nested.pdf").write_bytes(b"nested")

        from evidence_repository.services.bulk_ingestion_service import BulkIngestionService

        service = BulkIngestionService(storage=mock_storage, db=mock_db_session)

        import asyncio

        # Recursive
        files_recursive = asyncio.get_event_loop().run_until_complete(
            service.scan_folder(str(tmp_path), recursive=True, allowed_types=["pdf"])
        )
        assert len(files_recursive) == 2

        # Non-recursive
        files_flat = asyncio.get_event_loop().run_until_complete(
            service.scan_folder(str(tmp_path), recursive=False, allowed_types=["pdf"])
        )
        assert len(files_flat) == 1


# =============================================================================
# Integration Tests
# =============================================================================


class TestBulkIngestionIntegration:
    """Integration tests for bulk ingestion flow."""

    def test_folder_ingestion_creates_batch_and_items(self):
        """Folder ingestion should create batch with item records."""
        # This would be an integration test with actual database
        pass

    def test_url_ingestion_validates_ssrf(self):
        """URL ingestion should validate URLs for SSRF."""
        # This would test the full endpoint flow
        pass

    def test_project_attachment_on_ingestion(self):
        """Documents should be attached to project when project_id provided."""
        pass

    def test_progress_tracking(self):
        """Batch progress should be updated as items are processed."""
        pass
