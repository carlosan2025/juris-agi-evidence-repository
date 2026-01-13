"""Unit tests for LocalFilesystemStorage."""

import json
import os
import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio

from evidence_repository.storage.local import LocalFilesystemStorage
from evidence_repository.storage.base import (
    StorageDeleteError,
    StorageDownloadError,
    StorageMetadata,
    StorageUploadError,
)


@pytest.fixture
def temp_storage_dir():
    """Create a temporary directory for storage tests."""
    temp_dir = tempfile.mkdtemp(prefix="test_storage_")
    yield temp_dir
    # Cleanup after test
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def local_storage(temp_storage_dir) -> LocalFilesystemStorage:
    """Create a LocalFilesystemStorage instance with temp directory."""
    return LocalFilesystemStorage(base_path=temp_storage_dir)


@pytest.fixture
def sample_document_id() -> str:
    """Generate a sample document ID."""
    return str(uuid4())


@pytest.fixture
def sample_version_id() -> str:
    """Generate a sample version ID."""
    return "v1"


class TestLocalFilesystemStorageInit:
    """Tests for LocalFilesystemStorage initialization."""

    def test_creates_base_path_if_not_exists(self, temp_storage_dir):
        """Should create the base directory if it doesn't exist."""
        new_path = os.path.join(temp_storage_dir, "new_subdir")
        storage = LocalFilesystemStorage(base_path=new_path)
        assert os.path.exists(new_path)
        assert storage.base_path == Path(new_path).resolve()

    def test_works_with_existing_path(self, temp_storage_dir):
        """Should work with an existing directory."""
        storage = LocalFilesystemStorage(base_path=temp_storage_dir)
        assert storage.base_path == Path(temp_storage_dir).resolve()

    def test_resolves_relative_path(self):
        """Should resolve relative paths to absolute."""
        storage = LocalFilesystemStorage(base_path="./data/files")
        assert storage.base_path.is_absolute()


class TestGeneratePathKey:
    """Tests for the generate_path_key method."""

    def test_generates_correct_path_key(self, local_storage, sample_document_id, sample_version_id):
        """Should generate path key in expected format."""
        path_key = local_storage.generate_path_key(sample_document_id, sample_version_id, "pdf")
        assert path_key == f"{sample_document_id}/{sample_version_id}/original.pdf"

    def test_strips_leading_dot_from_extension(self, local_storage, sample_document_id, sample_version_id):
        """Should handle extensions with or without leading dot."""
        path_key1 = local_storage.generate_path_key(sample_document_id, sample_version_id, ".pdf")
        path_key2 = local_storage.generate_path_key(sample_document_id, sample_version_id, "pdf")
        assert path_key1 == path_key2


class TestPutBytes:
    """Tests for the put_bytes method."""

    @pytest.mark.asyncio
    async def test_uploads_bytes_successfully(self, local_storage, sample_document_id):
        """Should upload bytes and return a file:// URI."""
        path_key = f"{sample_document_id}/v1/original.txt"
        data = b"Hello, World!"
        content_type = "text/plain"

        file_uri = await local_storage.put_bytes(path_key, data, content_type)

        assert file_uri.startswith("file://")
        assert sample_document_id in file_uri

    @pytest.mark.asyncio
    async def test_creates_parent_directories(self, local_storage, sample_document_id):
        """Should create nested directories as needed."""
        path_key = f"{sample_document_id}/v1/subdir/deep/original.txt"
        data = b"Nested content"

        file_uri = await local_storage.put_bytes(path_key, data, "text/plain")

        # Verify file exists
        assert await local_storage.exists(file_uri)

    @pytest.mark.asyncio
    async def test_stores_metadata_in_sidecar(self, local_storage, sample_document_id):
        """Should store content type and size in metadata sidecar file."""
        path_key = f"{sample_document_id}/v1/original.txt"
        data = b"Test content"
        content_type = "text/plain"
        custom_metadata = {"author": "test_user"}

        file_uri = await local_storage.put_bytes(path_key, data, content_type, custom_metadata)

        # Verify metadata file exists
        path = local_storage._uri_to_path(file_uri)
        meta_path = path.parent / f".{path.name}.meta"
        assert meta_path.exists()

        # Verify metadata contents
        with open(meta_path) as f:
            meta = json.load(f)
        assert meta["content_type"] == content_type
        assert meta["size"] == len(data)
        assert meta["author"] == "test_user"
        assert "uploaded_at" in meta

    @pytest.mark.asyncio
    async def test_overwrites_existing_file(self, local_storage, sample_document_id):
        """Should overwrite existing file with same path key."""
        path_key = f"{sample_document_id}/v1/original.txt"

        # First upload
        await local_storage.put_bytes(path_key, b"Original", "text/plain")

        # Second upload
        file_uri = await local_storage.put_bytes(path_key, b"Updated", "text/plain")

        # Verify new content
        content = await local_storage.get_bytes(file_uri)
        assert content == b"Updated"


class TestPutFile:
    """Tests for the put_file method."""

    @pytest.mark.asyncio
    async def test_uploads_local_file(self, local_storage, sample_document_id, temp_storage_dir):
        """Should copy a local file to storage."""
        # Create source file
        source_path = os.path.join(temp_storage_dir, "source.txt")
        with open(source_path, "wb") as f:
            f.write(b"File content from local file")

        path_key = f"{sample_document_id}/v1/original.txt"
        file_uri = await local_storage.put_file(path_key, source_path, "text/plain")

        assert file_uri.startswith("file://")
        content = await local_storage.get_bytes(file_uri)
        assert content == b"File content from local file"

    @pytest.mark.asyncio
    async def test_raises_error_for_missing_source(self, local_storage, sample_document_id):
        """Should raise FileNotFoundError for non-existent source file."""
        path_key = f"{sample_document_id}/v1/original.txt"

        with pytest.raises(FileNotFoundError):
            await local_storage.put_file(path_key, "/nonexistent/file.txt", "text/plain")


class TestGetBytes:
    """Tests for the get_bytes method."""

    @pytest.mark.asyncio
    async def test_downloads_bytes(self, local_storage, sample_document_id):
        """Should retrieve uploaded bytes."""
        path_key = f"{sample_document_id}/v1/original.txt"
        original_data = b"Test content for download"

        file_uri = await local_storage.put_bytes(path_key, original_data, "text/plain")
        downloaded_data = await local_storage.get_bytes(file_uri)

        assert downloaded_data == original_data

    @pytest.mark.asyncio
    async def test_raises_error_for_missing_file(self, local_storage, temp_storage_dir):
        """Should raise FileNotFoundError for non-existent file."""
        fake_uri = f"file://{temp_storage_dir}/nonexistent/file.txt"

        with pytest.raises(FileNotFoundError):
            await local_storage.get_bytes(fake_uri)

    @pytest.mark.asyncio
    async def test_raises_error_for_invalid_uri_scheme(self, local_storage):
        """Should raise ValueError for non-file:// URIs."""
        with pytest.raises(ValueError, match="expected file:// scheme"):
            await local_storage.get_bytes("s3://bucket/key")


class TestGetStream:
    """Tests for the get_stream method."""

    @pytest.mark.asyncio
    async def test_streams_file_content(self, local_storage, sample_document_id):
        """Should stream file content in chunks."""
        path_key = f"{sample_document_id}/v1/original.txt"
        original_data = b"A" * 10000  # 10KB of data

        file_uri = await local_storage.put_bytes(path_key, original_data, "text/plain")

        chunks = []
        async for chunk in local_storage.get_stream(file_uri, chunk_size=1000):
            chunks.append(chunk)

        assert b"".join(chunks) == original_data
        assert len(chunks) == 10  # Should be 10 chunks of 1000 bytes

    @pytest.mark.asyncio
    async def test_raises_error_for_missing_file(self, local_storage, temp_storage_dir):
        """Should raise FileNotFoundError for non-existent file."""
        fake_uri = f"file://{temp_storage_dir}/nonexistent/file.txt"

        with pytest.raises(FileNotFoundError):
            async for _ in local_storage.get_stream(fake_uri):
                pass


class TestDelete:
    """Tests for the delete method."""

    @pytest.mark.asyncio
    async def test_deletes_existing_file(self, local_storage, sample_document_id):
        """Should delete file and return True."""
        path_key = f"{sample_document_id}/v1/original.txt"
        file_uri = await local_storage.put_bytes(path_key, b"To be deleted", "text/plain")

        result = await local_storage.delete(file_uri)

        assert result is True
        assert not await local_storage.exists(file_uri)

    @pytest.mark.asyncio
    async def test_deletes_metadata_sidecar(self, local_storage, sample_document_id):
        """Should delete metadata sidecar file along with main file."""
        path_key = f"{sample_document_id}/v1/original.txt"
        file_uri = await local_storage.put_bytes(path_key, b"Content", "text/plain")

        path = local_storage._uri_to_path(file_uri)
        meta_path = path.parent / f".{path.name}.meta"
        assert meta_path.exists()

        await local_storage.delete(file_uri)

        assert not meta_path.exists()

    @pytest.mark.asyncio
    async def test_returns_false_for_nonexistent_file(self, local_storage, temp_storage_dir):
        """Should return False when file doesn't exist."""
        fake_uri = f"file://{temp_storage_dir}/nonexistent.txt"

        result = await local_storage.delete(fake_uri)

        assert result is False


class TestExists:
    """Tests for the exists method."""

    @pytest.mark.asyncio
    async def test_returns_true_for_existing_file(self, local_storage, sample_document_id):
        """Should return True for existing file."""
        path_key = f"{sample_document_id}/v1/original.txt"
        file_uri = await local_storage.put_bytes(path_key, b"Content", "text/plain")

        assert await local_storage.exists(file_uri) is True

    @pytest.mark.asyncio
    async def test_returns_false_for_nonexistent_file(self, local_storage, temp_storage_dir):
        """Should return False for non-existent file."""
        fake_uri = f"file://{temp_storage_dir}/nonexistent.txt"

        assert await local_storage.exists(fake_uri) is False

    @pytest.mark.asyncio
    async def test_returns_false_for_invalid_uri(self, local_storage):
        """Should return False for invalid URI (not raise exception)."""
        assert await local_storage.exists("invalid://uri") is False


class TestSignDownloadUrl:
    """Tests for the sign_download_url method."""

    @pytest.mark.asyncio
    async def test_returns_same_uri_for_local_storage(self, local_storage, sample_document_id):
        """For local storage, should return the same file URI."""
        path_key = f"{sample_document_id}/v1/original.txt"
        file_uri = await local_storage.put_bytes(path_key, b"Content", "text/plain")

        signed_url = await local_storage.sign_download_url(file_uri, ttl_seconds=3600)

        assert signed_url == file_uri

    @pytest.mark.asyncio
    async def test_raises_error_for_missing_file(self, local_storage, temp_storage_dir):
        """Should raise FileNotFoundError for non-existent file."""
        fake_uri = f"file://{temp_storage_dir}/nonexistent.txt"

        with pytest.raises(FileNotFoundError):
            await local_storage.sign_download_url(fake_uri)


class TestGetMetadata:
    """Tests for the get_metadata method."""

    @pytest.mark.asyncio
    async def test_returns_metadata(self, local_storage, sample_document_id):
        """Should return StorageMetadata with file information."""
        path_key = f"{sample_document_id}/v1/original.txt"
        data = b"Test content"
        file_uri = await local_storage.put_bytes(path_key, data, "text/plain")

        metadata = await local_storage.get_metadata(file_uri)

        assert isinstance(metadata, StorageMetadata)
        assert metadata.size == len(data)
        assert metadata.content_type == "text/plain"
        assert metadata.etag  # Should have an ETag (MD5 hash)
        assert metadata.last_modified  # Should have timestamp
        assert metadata.key == path_key

    @pytest.mark.asyncio
    async def test_guesses_mime_type_if_not_stored(self, local_storage, temp_storage_dir):
        """Should guess MIME type from extension if not in sidecar."""
        # Create file directly without metadata sidecar
        path = Path(temp_storage_dir) / "direct.pdf"
        path.write_bytes(b"%PDF-1.4 fake pdf content")

        file_uri = f"file://{path}"
        metadata = await local_storage.get_metadata(file_uri)

        assert "pdf" in metadata.content_type.lower()

    @pytest.mark.asyncio
    async def test_raises_error_for_missing_file(self, local_storage, temp_storage_dir):
        """Should raise FileNotFoundError for non-existent file."""
        fake_uri = f"file://{temp_storage_dir}/nonexistent.txt"

        with pytest.raises(FileNotFoundError):
            await local_storage.get_metadata(fake_uri)


class TestListKeys:
    """Tests for the list_keys method."""

    @pytest.mark.asyncio
    async def test_lists_all_keys(self, local_storage, sample_document_id):
        """Should list all file keys in storage."""
        # Upload multiple files
        await local_storage.put_bytes(f"{sample_document_id}/v1/original.txt", b"v1", "text/plain")
        await local_storage.put_bytes(f"{sample_document_id}/v2/original.txt", b"v2", "text/plain")

        keys = await local_storage.list_keys()

        assert len(keys) == 2
        assert f"{sample_document_id}/v1/original.txt" in keys
        assert f"{sample_document_id}/v2/original.txt" in keys

    @pytest.mark.asyncio
    async def test_filters_by_prefix(self, local_storage):
        """Should filter keys by prefix."""
        doc1 = str(uuid4())
        doc2 = str(uuid4())

        await local_storage.put_bytes(f"{doc1}/v1/original.txt", b"doc1", "text/plain")
        await local_storage.put_bytes(f"{doc2}/v1/original.txt", b"doc2", "text/plain")

        keys = await local_storage.list_keys(prefix=doc1)

        assert len(keys) == 1
        assert doc1 in keys[0]

    @pytest.mark.asyncio
    async def test_excludes_metadata_files(self, local_storage, sample_document_id):
        """Should not include metadata sidecar files in listing."""
        await local_storage.put_bytes(f"{sample_document_id}/v1/original.txt", b"content", "text/plain")

        keys = await local_storage.list_keys()

        # Should only have the main file, not the .meta sidecar
        assert len(keys) == 1
        assert ".meta" not in keys[0]

    @pytest.mark.asyncio
    async def test_returns_empty_list_for_empty_storage(self, local_storage):
        """Should return empty list when no files exist."""
        keys = await local_storage.list_keys()
        assert keys == []


class TestPathTraversalSecurity:
    """Tests for path traversal attack prevention."""

    @pytest.mark.asyncio
    async def test_blocks_path_traversal_in_path_key(self, local_storage):
        """Should reject path keys with .. traversal."""
        with pytest.raises(ValueError, match="path traversal"):
            await local_storage.put_bytes("../../etc/passwd", b"malicious", "text/plain")

    @pytest.mark.asyncio
    async def test_blocks_path_traversal_in_uri(self, local_storage):
        """Should reject URIs pointing outside storage root."""
        with pytest.raises(ValueError, match="outside storage root"):
            await local_storage.get_bytes("file:///etc/passwd")


class TestLegacyMethods:
    """Tests for legacy compatibility methods."""

    @pytest.mark.asyncio
    async def test_upload_method(self, local_storage, sample_document_id):
        """Legacy upload method should work."""
        key = f"{sample_document_id}/v1/original.txt"
        result_key = await local_storage.upload(key, b"Legacy content", "text/plain")
        assert result_key == key

    @pytest.mark.asyncio
    async def test_download_method_with_key(self, local_storage, sample_document_id):
        """Legacy download method should accept raw key."""
        key = f"{sample_document_id}/v1/original.txt"
        await local_storage.put_bytes(key, b"Download test", "text/plain")

        content = await local_storage.download(key)
        assert content == b"Download test"

    @pytest.mark.asyncio
    async def test_download_method_with_uri(self, local_storage, sample_document_id):
        """Legacy download method should accept URI."""
        key = f"{sample_document_id}/v1/original.txt"
        file_uri = await local_storage.put_bytes(key, b"Download URI test", "text/plain")

        content = await local_storage.download(file_uri)
        assert content == b"Download URI test"

    @pytest.mark.asyncio
    async def test_get_url_method(self, local_storage, sample_document_id):
        """Legacy get_url method should work."""
        key = f"{sample_document_id}/v1/original.txt"
        await local_storage.put_bytes(key, b"URL test", "text/plain")

        url = await local_storage.get_url(key, expires_in=3600)
        assert url.startswith("file://")


class TestUriEncoding:
    """Tests for proper URI encoding/decoding."""

    @pytest.mark.asyncio
    async def test_handles_spaces_in_path(self, local_storage):
        """Should properly encode/decode paths with spaces."""
        doc_id = str(uuid4())
        path_key = f"{doc_id}/version 1/original file.txt"

        file_uri = await local_storage.put_bytes(path_key, b"Space test", "text/plain")
        content = await local_storage.get_bytes(file_uri)

        assert content == b"Space test"

    @pytest.mark.asyncio
    async def test_handles_special_characters(self, local_storage):
        """Should properly encode/decode paths with special characters."""
        doc_id = str(uuid4())
        # Note: some characters may still be invalid for filesystem
        path_key = f"{doc_id}/v1/file_name-123.txt"

        file_uri = await local_storage.put_bytes(path_key, b"Special chars", "text/plain")
        content = await local_storage.get_bytes(file_uri)

        assert content == b"Special chars"


class TestGetStorageRoot:
    """Tests for get_storage_root utility method."""

    def test_returns_base_path_string(self, local_storage, temp_storage_dir):
        """Should return the storage root directory as string."""
        root = local_storage.get_storage_root()
        assert root == str(Path(temp_storage_dir).resolve())
