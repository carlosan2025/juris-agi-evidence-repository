"""Storage abstraction layer for file management."""

from evidence_repository.storage.base import StorageBackend
from evidence_repository.storage.local import LocalFilesystemStorage
from evidence_repository.storage.s3 import S3Storage

__all__ = [
    "StorageBackend",
    "LocalFilesystemStorage",
    "S3Storage",
]


def get_storage_backend() -> StorageBackend:
    """Factory function to get the configured storage backend.

    Returns:
        StorageBackend: The configured storage backend instance.
    """
    from evidence_repository.config import get_settings

    settings = get_settings()

    if settings.storage_backend == "local":
        return LocalFilesystemStorage(base_path=settings.file_storage_root)
    elif settings.storage_backend == "s3":
        return S3Storage(
            bucket_name=settings.s3_bucket_name,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region=settings.aws_region,
            prefix=settings.s3_prefix,
            endpoint_url=settings.s3_endpoint_url,
        )
    else:
        raise ValueError(f"Unknown storage backend: {settings.storage_backend}")
