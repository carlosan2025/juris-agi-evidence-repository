"""Local filesystem storage backend."""

import hashlib
import json
import mimetypes
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator
from urllib.parse import quote, unquote

import aiofiles
import aiofiles.os

from evidence_repository.storage.base import (
    StorageBackend,
    StorageDeleteError,
    StorageDownloadError,
    StorageMetadata,
    StorageUploadError,
)


class LocalFilesystemStorage(StorageBackend):
    """Storage backend using the local filesystem.

    Files are stored in a directory structure under the configured base path.
    This is the default backend for local development and can be migrated
    to S3 later.

    File URI Format: file:///absolute/path/to/file

    Path Key Layout: {document_id}/{version_id}/original.{ext}

    Example:
        path_key: "550e8400-e29b-41d4-a716-446655440000/v1/original.pdf"
        file_uri: "file:///data/files/550e8400-e29b-41d4-a716-446655440000/v1/original.pdf"
    """

    URI_SCHEME = "file://"

    def __init__(self, base_path: str = "./data/files"):
        """Initialize local filesystem storage.

        Args:
            base_path: Base directory for file storage (FILE_STORAGE_ROOT).
        """
        self.base_path = Path(base_path).resolve()
        self._ensure_base_path()

    def _ensure_base_path(self) -> None:
        """Create base directory if it doesn't exist."""
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _get_full_path(self, path_key: str) -> Path:
        """Get the full filesystem path for a storage key.

        Args:
            path_key: Storage path key (e.g., "{doc_id}/{version_id}/original.pdf").

        Returns:
            Full path to the file.

        Raises:
            ValueError: If path traversal is detected.
        """
        # Normalize and validate the key to prevent directory traversal
        path_key = path_key.lstrip("/")
        full_path = (self.base_path / path_key).resolve()

        # Security check: ensure path is within base_path
        if not str(full_path).startswith(str(self.base_path)):
            raise ValueError(f"Invalid key: {path_key} (path traversal detected)")

        return full_path

    def _path_to_uri(self, path: Path) -> str:
        """Convert a filesystem path to a file:// URI.

        Args:
            path: Filesystem path.

        Returns:
            File URI (e.g., "file:///absolute/path").
        """
        # Use proper URI encoding for special characters
        return f"{self.URI_SCHEME}{quote(str(path))}"

    def _uri_to_path(self, file_uri: str) -> Path:
        """Convert a file:// URI to a filesystem path.

        Args:
            file_uri: File URI (e.g., "file:///path/to/file").

        Returns:
            Filesystem path.

        Raises:
            ValueError: If URI is invalid or doesn't use file:// scheme.
        """
        if not file_uri.startswith(self.URI_SCHEME):
            raise ValueError(f"Invalid file URI: {file_uri} (expected file:// scheme)")

        # Remove scheme and decode URI encoding
        path_str = unquote(file_uri[len(self.URI_SCHEME):])
        path = Path(path_str).resolve()

        # Security check: ensure path is within base_path
        if not str(path).startswith(str(self.base_path)):
            raise ValueError(f"Invalid file URI: {file_uri} (outside storage root)")

        return path

    def _key_to_uri(self, key: str) -> str:
        """Convert a storage key to a URI (for legacy compatibility)."""
        full_path = self._get_full_path(key)
        return self._path_to_uri(full_path)

    def _get_meta_path(self, file_path: Path) -> Path:
        """Get the metadata sidecar file path."""
        return file_path.parent / f".{file_path.name}.meta"

    async def _write_metadata(
        self,
        file_path: Path,
        content_type: str,
        size: int,
        metadata: dict[str, str] | None = None,
    ) -> None:
        """Write metadata to sidecar file."""
        meta = {
            "content_type": content_type,
            "size": size,
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
            **(metadata or {}),
        }
        meta_path = self._get_meta_path(file_path)
        async with aiofiles.open(meta_path, "w") as f:
            await f.write(json.dumps(meta, indent=2))

    async def _read_metadata(self, file_path: Path) -> dict:
        """Read metadata from sidecar file."""
        meta_path = self._get_meta_path(file_path)
        if meta_path.exists():
            try:
                async with aiofiles.open(meta_path, "r") as f:
                    return json.loads(await f.read())
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    # =========================================================================
    # Core Write Operations
    # =========================================================================

    async def put_bytes(
        self,
        path_key: str,
        data: bytes,
        content_type: str,
        metadata: dict[str, str] | None = None,
    ) -> str:
        """Upload bytes to local storage.

        Args:
            path_key: Path key (e.g., "{doc_id}/{version_id}/original.pdf").
            data: File content as bytes.
            content_type: MIME type of the file.
            metadata: Optional metadata to store in sidecar file.

        Returns:
            File URI (e.g., "file:///absolute/path/to/file").
        """
        try:
            full_path = self._get_full_path(path_key)

            # Create parent directories
            await aiofiles.os.makedirs(full_path.parent, exist_ok=True)

            # Write file content
            async with aiofiles.open(full_path, "wb") as f:
                await f.write(data)

            # Store metadata in sidecar file
            await self._write_metadata(full_path, content_type, len(data), metadata)

            return self._path_to_uri(full_path)

        except OSError as e:
            raise StorageUploadError(f"Failed to upload {path_key}: {e}") from e

    async def put_file(
        self,
        path_key: str,
        local_path: str,
        content_type: str,
        metadata: dict[str, str] | None = None,
    ) -> str:
        """Upload a local file to storage.

        More efficient than put_bytes for large files as it uses shutil.copy.

        Args:
            path_key: Path key (e.g., "{doc_id}/{version_id}/original.pdf").
            local_path: Path to local file to upload.
            content_type: MIME type of the file.
            metadata: Optional metadata to store in sidecar file.

        Returns:
            File URI (e.g., "file:///absolute/path/to/file").
        """
        source_path = Path(local_path)
        if not source_path.exists():
            raise FileNotFoundError(f"Local file not found: {local_path}")

        try:
            full_path = self._get_full_path(path_key)

            # Create parent directories
            await aiofiles.os.makedirs(full_path.parent, exist_ok=True)

            # Copy file (more efficient than read/write for large files)
            # Use sync copy in thread pool for efficiency
            import asyncio
            await asyncio.to_thread(shutil.copy2, source_path, full_path)

            # Get file size and store metadata
            file_size = full_path.stat().st_size
            await self._write_metadata(full_path, content_type, file_size, metadata)

            return self._path_to_uri(full_path)

        except OSError as e:
            raise StorageUploadError(f"Failed to upload {path_key}: {e}") from e

    # =========================================================================
    # Core Read Operations
    # =========================================================================

    async def get_bytes(self, file_uri: str) -> bytes:
        """Download file content as bytes.

        Args:
            file_uri: File URI (e.g., "file:///path/to/file").

        Returns:
            The file content as bytes.
        """
        full_path = self._uri_to_path(file_uri)

        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {file_uri}")

        try:
            async with aiofiles.open(full_path, "rb") as f:
                return await f.read()
        except OSError as e:
            raise StorageDownloadError(f"Failed to download {file_uri}: {e}") from e

    async def get_stream(
        self, file_uri: str, chunk_size: int = 8192
    ) -> AsyncIterator[bytes]:
        """Stream file content in chunks.

        Args:
            file_uri: File URI (e.g., "file:///path/to/file").
            chunk_size: Size of each chunk in bytes.

        Yields:
            Chunks of file content.
        """
        full_path = self._uri_to_path(file_uri)

        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {file_uri}")

        try:
            async with aiofiles.open(full_path, "rb") as f:
                while True:
                    chunk = await f.read(chunk_size)
                    if not chunk:
                        break
                    yield chunk
        except OSError as e:
            raise StorageDownloadError(f"Failed to stream {file_uri}: {e}") from e

    # =========================================================================
    # File Management Operations
    # =========================================================================

    async def delete(self, file_uri: str) -> bool:
        """Delete a file from local storage.

        Args:
            file_uri: File URI to delete.

        Returns:
            True if deleted, False if file didn't exist.
        """
        full_path = self._uri_to_path(file_uri)
        meta_path = self._get_meta_path(full_path)

        if not full_path.exists():
            return False

        try:
            await aiofiles.os.remove(full_path)
            if meta_path.exists():
                await aiofiles.os.remove(meta_path)
            return True
        except OSError as e:
            raise StorageDeleteError(f"Failed to delete {file_uri}: {e}") from e

    async def exists(self, file_uri: str) -> bool:
        """Check if a file exists in local storage.

        Args:
            file_uri: File URI to check.

        Returns:
            True if the file exists.
        """
        try:
            full_path = self._uri_to_path(file_uri)
            return full_path.exists()
        except ValueError:
            return False

    # =========================================================================
    # URL/Access Operations
    # =========================================================================

    async def sign_download_url(self, file_uri: str, ttl_seconds: int = 3600) -> str:
        """Generate a URL to download the file.

        For local storage, returns the file:// URI directly.
        The ttl_seconds parameter is ignored for local storage.

        Args:
            file_uri: File URI to generate URL for.
            ttl_seconds: Ignored for local storage.

        Returns:
            The file URI (same as input for local storage).
        """
        full_path = self._uri_to_path(file_uri)

        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {file_uri}")

        # For local storage, just return the file URI
        # In production, this would return a signed URL or API endpoint
        return file_uri

    # =========================================================================
    # Metadata Operations
    # =========================================================================

    async def get_metadata(self, file_uri: str) -> StorageMetadata:
        """Get metadata about a stored file.

        Args:
            file_uri: File URI to get metadata for.

        Returns:
            StorageMetadata with file information.
        """
        full_path = self._uri_to_path(file_uri)

        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {file_uri}")

        # Read sidecar metadata
        meta = await self._read_metadata(full_path)
        content_type = meta.get("content_type", "application/octet-stream")

        # Fall back to mime type guessing
        if content_type == "application/octet-stream":
            guessed_type, _ = mimetypes.guess_type(str(full_path))
            if guessed_type:
                content_type = guessed_type

        # Get file stats
        stat = full_path.stat()

        # Calculate ETag (MD5 hash)
        async with aiofiles.open(full_path, "rb") as f:
            content = await f.read()
            etag = hashlib.md5(content).hexdigest()

        # Derive key from path
        relative_path = full_path.relative_to(self.base_path)

        return StorageMetadata(
            key=str(relative_path),
            size=stat.st_size,
            content_type=content_type,
            etag=etag,
            last_modified=datetime.fromtimestamp(
                stat.st_mtime, tz=timezone.utc
            ).isoformat(),
        )

    # =========================================================================
    # Listing Operations
    # =========================================================================

    async def list_keys(self, prefix: str = "") -> list[str]:
        """List all keys with a given prefix.

        Args:
            prefix: Filter keys by this prefix.

        Returns:
            List of storage keys matching the prefix.
        """
        keys: list[str] = []
        prefix_path = self._get_full_path(prefix) if prefix else self.base_path

        if not prefix_path.exists():
            return keys

        # Walk directory tree
        search_path = prefix_path if prefix_path.is_dir() else prefix_path.parent
        for root, _, files in os.walk(search_path):
            for file in files:
                # Skip metadata sidecar files
                if file.startswith(".") and file.endswith(".meta"):
                    continue

                full_path = Path(root) / file
                relative_path = full_path.relative_to(self.base_path)
                key = str(relative_path)

                if key.startswith(prefix):
                    keys.append(key)

        return sorted(keys)

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def generate_path_key(
        self,
        document_id: str,
        version_number: int,
        filename: str,
    ) -> str:
        """Generate a storage path key for a document version.

        Path format: documents/{document_id}/v{version_number}/{filename}

        Args:
            document_id: Document UUID string.
            version_number: Version number (1, 2, 3...).
            filename: Original filename.

        Returns:
            Storage path key.
        """
        # Sanitize filename
        safe_filename = "".join(
            c for c in filename if c.isalnum() or c in "._-"
        ).strip()
        if not safe_filename:
            safe_filename = "document"

        return f"documents/{document_id}/v{version_number}/{safe_filename}"

    def get_storage_root(self) -> str:
        """Get the storage root directory path."""
        return str(self.base_path)

    # =========================================================================
    # Legacy Compatibility (deprecated)
    # =========================================================================

    async def upload(
        self,
        key: str,
        data: bytes,
        content_type: str,
        metadata: dict[str, str] | None = None,
    ) -> str:
        """Upload a file (legacy method - use put_bytes instead)."""
        file_uri = await self.put_bytes(key, data, content_type, metadata)
        # Return key for backwards compatibility
        return key

    async def download(self, key: str) -> bytes:
        """Download a file (legacy method - use get_bytes instead)."""
        # Handle both URI and raw key for backwards compatibility
        if key.startswith(self.URI_SCHEME):
            return await self.get_bytes(key)
        return await self.get_bytes(self._key_to_uri(key))

    async def get_url(self, key: str, expires_in: int = 3600) -> str:
        """Get URL for file (legacy method - use sign_download_url instead)."""
        if key.startswith(self.URI_SCHEME):
            return await self.sign_download_url(key, expires_in)
        return await self.sign_download_url(self._key_to_uri(key), expires_in)
