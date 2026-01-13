"""Abstract base class for storage backends."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator


@dataclass
class StorageMetadata:
    """Metadata about a stored file."""

    key: str
    size: int
    content_type: str
    etag: str | None = None
    last_modified: str | None = None


class StorageBackend(ABC):
    """Abstract base class for file storage backends.

    This abstraction allows switching between different storage implementations
    (local filesystem, AWS S3, etc.) without changing application code.

    All methods are async to support non-blocking I/O operations.

    File URI Formats:
    - Local: file:///absolute/path/to/file
    - S3: s3://bucket-name/key/path

    Path Key Format:
    - {document_id}/{version_id}/original.{ext}
    """

    # =========================================================================
    # Core Write Operations
    # =========================================================================

    @abstractmethod
    async def put_bytes(
        self,
        path_key: str,
        data: bytes,
        content_type: str,
        metadata: dict[str, str] | None = None,
    ) -> str:
        """Upload bytes to storage.

        Args:
            path_key: Path key (e.g., "{doc_id}/{version_id}/original.pdf").
            data: File content as bytes.
            content_type: MIME type of the file.
            metadata: Optional key-value metadata to store with the file.

        Returns:
            File URI (e.g., "file:///path/to/file" or "s3://bucket/key").

        Raises:
            StorageUploadError: If upload fails.
        """
        ...

    @abstractmethod
    async def put_file(
        self,
        path_key: str,
        local_path: str,
        content_type: str,
        metadata: dict[str, str] | None = None,
    ) -> str:
        """Upload a local file to storage.

        More efficient than put_bytes for large files as it can stream.

        Args:
            path_key: Path key (e.g., "{doc_id}/{version_id}/original.pdf").
            local_path: Path to local file to upload.
            content_type: MIME type of the file.
            metadata: Optional key-value metadata to store with the file.

        Returns:
            File URI (e.g., "file:///path/to/file" or "s3://bucket/key").

        Raises:
            StorageUploadError: If upload fails.
            FileNotFoundError: If local file doesn't exist.
        """
        ...

    # =========================================================================
    # Core Read Operations
    # =========================================================================

    @abstractmethod
    async def get_bytes(self, file_uri: str) -> bytes:
        """Download file content as bytes.

        Args:
            file_uri: File URI (e.g., "file:///path" or "s3://bucket/key").

        Returns:
            The file content as bytes.

        Raises:
            StorageDownloadError: If download fails.
            FileNotFoundError: If the file does not exist.
        """
        ...

    @abstractmethod
    async def get_stream(
        self, file_uri: str, chunk_size: int = 8192
    ) -> AsyncIterator[bytes]:
        """Stream file content in chunks.

        More memory-efficient for large files.

        Args:
            file_uri: File URI (e.g., "file:///path" or "s3://bucket/key").
            chunk_size: Size of each chunk in bytes.

        Yields:
            Chunks of file content.

        Raises:
            StorageDownloadError: If download fails.
            FileNotFoundError: If the file does not exist.
        """
        ...

    # =========================================================================
    # File Management Operations
    # =========================================================================

    @abstractmethod
    async def delete(self, file_uri: str) -> bool:
        """Delete a file from storage.

        Args:
            file_uri: File URI to delete.

        Returns:
            True if deleted successfully, False if file didn't exist.

        Raises:
            StorageDeleteError: If deletion fails for reasons other than missing file.
        """
        ...

    @abstractmethod
    async def exists(self, file_uri: str) -> bool:
        """Check if a file exists in storage.

        Args:
            file_uri: File URI to check.

        Returns:
            True if the file exists, False otherwise.
        """
        ...

    # =========================================================================
    # URL/Access Operations
    # =========================================================================

    @abstractmethod
    async def sign_download_url(self, file_uri: str, ttl_seconds: int = 3600) -> str:
        """Generate a signed/temporary URL to download the file.

        For local storage, returns a file:// URI or relative path.
        For S3, returns a pre-signed URL.

        Args:
            file_uri: File URI to generate URL for.
            ttl_seconds: URL expiration time in seconds (for pre-signed URLs).

        Returns:
            URL or path to access the file.

        Raises:
            FileNotFoundError: If the file does not exist.
        """
        ...

    # =========================================================================
    # Metadata Operations
    # =========================================================================

    @abstractmethod
    async def get_metadata(self, file_uri: str) -> StorageMetadata:
        """Get metadata about a stored file.

        Args:
            file_uri: File URI to get metadata for.

        Returns:
            StorageMetadata with file information.

        Raises:
            FileNotFoundError: If the file does not exist.
        """
        ...

    # =========================================================================
    # Listing Operations
    # =========================================================================

    @abstractmethod
    async def list_keys(self, prefix: str = "") -> list[str]:
        """List all keys with a given prefix.

        Args:
            prefix: Filter keys by this prefix.

        Returns:
            List of storage keys matching the prefix.
        """
        ...

    # =========================================================================
    # Helper Operations (with default implementations)
    # =========================================================================

    async def copy(self, source_uri: str, dest_path_key: str) -> str:
        """Copy a file within storage.

        Default implementation downloads and re-uploads.
        Override for more efficient backend-specific implementation.

        Args:
            source_uri: Source file URI.
            dest_path_key: Destination path key.

        Returns:
            The destination file URI.
        """
        data = await self.get_bytes(source_uri)
        metadata = await self.get_metadata(source_uri)
        return await self.put_bytes(dest_path_key, data, metadata.content_type)

    # =========================================================================
    # Legacy Compatibility Methods (deprecated, use new methods)
    # =========================================================================

    async def upload(
        self,
        key: str,
        data: bytes,
        content_type: str,
        metadata: dict[str, str] | None = None,
    ) -> str:
        """Upload a file to storage (legacy method).

        Deprecated: Use put_bytes() instead.
        """
        return await self.put_bytes(key, data, content_type, metadata)

    async def download(self, key: str) -> bytes:
        """Download a file from storage (legacy method).

        Deprecated: Use get_bytes() instead.
        """
        # Handle both URI and raw key for backwards compatibility
        if not key.startswith(("file://", "s3://")):
            key = self._key_to_uri(key)
        return await self.get_bytes(key)

    async def get_url(self, key: str, expires_in: int = 3600) -> str:
        """Generate URL to access file (legacy method).

        Deprecated: Use sign_download_url() instead.
        """
        if not key.startswith(("file://", "s3://")):
            key = self._key_to_uri(key)
        return await self.sign_download_url(key, expires_in)

    def _key_to_uri(self, key: str) -> str:
        """Convert a storage key to a URI. Override in subclasses."""
        raise NotImplementedError("Subclass must implement _key_to_uri")


class StorageError(Exception):
    """Base exception for storage operations."""

    pass


class StorageUploadError(StorageError):
    """Error during file upload."""

    pass


class StorageDownloadError(StorageError):
    """Error during file download."""

    pass


class StorageDeleteError(StorageError):
    """Error during file deletion."""

    pass
