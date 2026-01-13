"""AWS S3 storage backend (stubbed for future implementation)."""

from typing import AsyncIterator

from evidence_repository.storage.base import StorageBackend, StorageMetadata


class S3Storage(StorageBackend):
    """Storage backend using AWS S3.

    This is a stubbed implementation with configuration placeholders.
    Actual S3 integration will be implemented when migrating from local storage.

    File URI Format: s3://bucket-name/key/path

    Path Key Layout: {document_id}/{version_id}/original.{ext}

    Configuration:
        - AWS_ACCESS_KEY_ID: AWS access key
        - AWS_SECRET_ACCESS_KEY: AWS secret key
        - AWS_REGION: AWS region (default: us-east-1)
        - S3_BUCKET_NAME: Target S3 bucket
        - S3_PREFIX: Optional key prefix for all objects
        - S3_ENDPOINT_URL: Optional custom endpoint (for S3-compatible services)
    """

    URI_SCHEME = "s3://"

    def __init__(
        self,
        bucket_name: str,
        aws_access_key_id: str = "",
        aws_secret_access_key: str = "",
        region: str = "us-east-1",
        prefix: str = "",
        endpoint_url: str | None = None,
    ):
        """Initialize S3 storage backend.

        Args:
            bucket_name: S3 bucket name.
            aws_access_key_id: AWS access key ID.
            aws_secret_access_key: AWS secret access key.
            region: AWS region.
            prefix: Optional key prefix for all objects.
            endpoint_url: Optional custom S3 endpoint URL.
        """
        self.bucket_name = bucket_name
        self.aws_access_key_id = aws_access_key_id
        self.aws_secret_access_key = aws_secret_access_key
        self.region = region
        self.prefix = prefix.strip("/")
        self.endpoint_url = endpoint_url

        # TODO: Initialize boto3 client when implementing
        # import boto3
        # self._client = boto3.client(
        #     's3',
        #     aws_access_key_id=aws_access_key_id,
        #     aws_secret_access_key=aws_secret_access_key,
        #     region_name=region,
        #     endpoint_url=endpoint_url,
        # )

    def _get_full_key(self, path_key: str) -> str:
        """Get the full S3 key including prefix.

        Args:
            path_key: Storage path key.

        Returns:
            Full S3 key with prefix.
        """
        path_key = path_key.lstrip("/")
        if self.prefix:
            return f"{self.prefix}/{path_key}"
        return path_key

    def _key_to_uri(self, key: str) -> str:
        """Convert a storage key to an S3 URI."""
        full_key = self._get_full_key(key)
        return f"{self.URI_SCHEME}{self.bucket_name}/{full_key}"

    def _uri_to_key(self, file_uri: str) -> str:
        """Convert an S3 URI to a key.

        Args:
            file_uri: S3 URI (e.g., "s3://bucket/key").

        Returns:
            S3 object key.

        Raises:
            ValueError: If URI is invalid.
        """
        if not file_uri.startswith(self.URI_SCHEME):
            raise ValueError(f"Invalid S3 URI: {file_uri} (expected s3:// scheme)")

        # Remove scheme and parse bucket/key
        remainder = file_uri[len(self.URI_SCHEME):]
        parts = remainder.split("/", 1)
        if len(parts) < 2:
            raise ValueError(f"Invalid S3 URI: {file_uri} (missing key)")

        bucket, key = parts
        if bucket != self.bucket_name:
            raise ValueError(f"Invalid S3 URI: {file_uri} (wrong bucket)")

        return key

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
        """Upload bytes to S3.

        Args:
            path_key: Path key (e.g., "{doc_id}/{version_id}/original.pdf").
            data: File content as bytes.
            content_type: MIME type of the file.
            metadata: Optional S3 object metadata.

        Returns:
            S3 URI (e.g., "s3://bucket/key").

        Raises:
            NotImplementedError: S3 storage is not yet implemented.
        """
        raise NotImplementedError(
            "S3 storage is not yet implemented. "
            "Use STORAGE_BACKEND=local for now. "
            "S3 support will be added in a future release."
        )

        # TODO: Implement when ready to migrate to S3
        # import asyncio
        # full_key = self._get_full_key(path_key)
        # await asyncio.to_thread(
        #     self._client.put_object,
        #     Bucket=self.bucket_name,
        #     Key=full_key,
        #     Body=data,
        #     ContentType=content_type,
        #     Metadata=metadata or {},
        # )
        # return f"{self.URI_SCHEME}{self.bucket_name}/{full_key}"

    async def put_file(
        self,
        path_key: str,
        local_path: str,
        content_type: str,
        metadata: dict[str, str] | None = None,
    ) -> str:
        """Upload a local file to S3.

        Uses multipart upload for large files.

        Args:
            path_key: Path key (e.g., "{doc_id}/{version_id}/original.pdf").
            local_path: Path to local file to upload.
            content_type: MIME type of the file.
            metadata: Optional S3 object metadata.

        Returns:
            S3 URI (e.g., "s3://bucket/key").

        Raises:
            NotImplementedError: S3 storage is not yet implemented.
        """
        raise NotImplementedError(
            "S3 storage is not yet implemented. "
            "Use STORAGE_BACKEND=local for now."
        )

        # TODO: Implement when ready to migrate to S3
        # import asyncio
        # from boto3.s3.transfer import TransferConfig
        #
        # full_key = self._get_full_key(path_key)
        # config = TransferConfig(
        #     multipart_threshold=8 * 1024 * 1024,  # 8MB
        #     max_concurrency=10,
        # )
        # extra_args = {
        #     'ContentType': content_type,
        #     'Metadata': metadata or {},
        # }
        # await asyncio.to_thread(
        #     self._client.upload_file,
        #     local_path,
        #     self.bucket_name,
        #     full_key,
        #     ExtraArgs=extra_args,
        #     Config=config,
        # )
        # return f"{self.URI_SCHEME}{self.bucket_name}/{full_key}"

    # =========================================================================
    # Core Read Operations
    # =========================================================================

    async def get_bytes(self, file_uri: str) -> bytes:
        """Download file content from S3 as bytes.

        Args:
            file_uri: S3 URI (e.g., "s3://bucket/key").

        Returns:
            File content as bytes.

        Raises:
            NotImplementedError: S3 storage is not yet implemented.
        """
        raise NotImplementedError(
            "S3 storage is not yet implemented. "
            "Use STORAGE_BACKEND=local for now."
        )

        # TODO: Implement when ready to migrate to S3
        # import asyncio
        # key = self._uri_to_key(file_uri)
        # response = await asyncio.to_thread(
        #     self._client.get_object,
        #     Bucket=self.bucket_name,
        #     Key=key,
        # )
        # return response['Body'].read()

    async def get_stream(
        self, file_uri: str, chunk_size: int = 8192
    ) -> AsyncIterator[bytes]:
        """Stream file content from S3 in chunks.

        Args:
            file_uri: S3 URI (e.g., "s3://bucket/key").
            chunk_size: Size of each chunk in bytes.

        Yields:
            Chunks of file content.

        Raises:
            NotImplementedError: S3 storage is not yet implemented.
        """
        raise NotImplementedError(
            "S3 storage is not yet implemented. "
            "Use STORAGE_BACKEND=local for now."
        )
        # Make this a generator to satisfy type checker
        yield b""  # pragma: no cover

        # TODO: Implement when ready to migrate to S3
        # import asyncio
        # key = self._uri_to_key(file_uri)
        # response = await asyncio.to_thread(
        #     self._client.get_object,
        #     Bucket=self.bucket_name,
        #     Key=key,
        # )
        # body = response['Body']
        # while True:
        #     chunk = await asyncio.to_thread(body.read, chunk_size)
        #     if not chunk:
        #         break
        #     yield chunk

    # =========================================================================
    # File Management Operations
    # =========================================================================

    async def delete(self, file_uri: str) -> bool:
        """Delete a file from S3.

        Args:
            file_uri: S3 URI to delete.

        Returns:
            True if deleted.

        Raises:
            NotImplementedError: S3 storage is not yet implemented.
        """
        raise NotImplementedError(
            "S3 storage is not yet implemented. "
            "Use STORAGE_BACKEND=local for now."
        )

        # TODO: Implement when ready to migrate to S3
        # import asyncio
        # key = self._uri_to_key(file_uri)
        # await asyncio.to_thread(
        #     self._client.delete_object,
        #     Bucket=self.bucket_name,
        #     Key=key,
        # )
        # return True

    async def exists(self, file_uri: str) -> bool:
        """Check if an object exists in S3.

        Args:
            file_uri: S3 URI to check.

        Returns:
            True if exists.

        Raises:
            NotImplementedError: S3 storage is not yet implemented.
        """
        raise NotImplementedError(
            "S3 storage is not yet implemented. "
            "Use STORAGE_BACKEND=local for now."
        )

        # TODO: Implement when ready to migrate to S3
        # import asyncio
        # from botocore.exceptions import ClientError
        # key = self._uri_to_key(file_uri)
        # try:
        #     await asyncio.to_thread(
        #         self._client.head_object,
        #         Bucket=self.bucket_name,
        #         Key=key,
        #     )
        #     return True
        # except ClientError:
        #     return False

    # =========================================================================
    # URL/Access Operations
    # =========================================================================

    async def sign_download_url(self, file_uri: str, ttl_seconds: int = 3600) -> str:
        """Generate a pre-signed URL for S3 object download.

        Args:
            file_uri: S3 URI to sign.
            ttl_seconds: URL expiration in seconds.

        Returns:
            Pre-signed URL.

        Raises:
            NotImplementedError: S3 storage is not yet implemented.
        """
        raise NotImplementedError(
            "S3 storage is not yet implemented. "
            "Use STORAGE_BACKEND=local for now."
        )

        # TODO: Implement when ready to migrate to S3
        # key = self._uri_to_key(file_uri)
        # return self._client.generate_presigned_url(
        #     'get_object',
        #     Params={'Bucket': self.bucket_name, 'Key': key},
        #     ExpiresIn=ttl_seconds,
        # )

    # =========================================================================
    # Metadata Operations
    # =========================================================================

    async def get_metadata(self, file_uri: str) -> StorageMetadata:
        """Get metadata for an S3 object.

        Args:
            file_uri: S3 URI to get metadata for.

        Returns:
            StorageMetadata object.

        Raises:
            NotImplementedError: S3 storage is not yet implemented.
        """
        raise NotImplementedError(
            "S3 storage is not yet implemented. "
            "Use STORAGE_BACKEND=local for now."
        )

        # TODO: Implement when ready to migrate to S3
        # import asyncio
        # key = self._uri_to_key(file_uri)
        # response = await asyncio.to_thread(
        #     self._client.head_object,
        #     Bucket=self.bucket_name,
        #     Key=key,
        # )
        # return StorageMetadata(
        #     key=key,
        #     size=response['ContentLength'],
        #     content_type=response['ContentType'],
        #     etag=response['ETag'].strip('"'),
        #     last_modified=response['LastModified'].isoformat(),
        # )

    # =========================================================================
    # Listing Operations
    # =========================================================================

    async def list_keys(self, prefix: str = "") -> list[str]:
        """List objects in S3 bucket with prefix.

        Args:
            prefix: Key prefix filter.

        Returns:
            List of object keys.

        Raises:
            NotImplementedError: S3 storage is not yet implemented.
        """
        raise NotImplementedError(
            "S3 storage is not yet implemented. "
            "Use STORAGE_BACKEND=local for now."
        )

        # TODO: Implement when ready to migrate to S3
        # import asyncio
        # full_prefix = self._get_full_key(prefix) if prefix else self.prefix
        # keys = []
        # paginator = self._client.get_paginator('list_objects_v2')
        # pages = paginator.paginate(Bucket=self.bucket_name, Prefix=full_prefix)
        # for page in pages:
        #     for obj in page.get('Contents', []):
        #         keys.append(obj['Key'])
        # return keys

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def generate_path_key(
        self,
        document_id: str,
        version_id: str,
        extension: str,
    ) -> str:
        """Generate a storage path key for a document version.

        Args:
            document_id: Document UUID.
            version_id: Version identifier (e.g., "v1" or UUID).
            extension: File extension (e.g., "pdf", "txt").

        Returns:
            Path key (e.g., "{doc_id}/{version_id}/original.pdf").
        """
        ext = extension.lstrip(".")
        return f"{document_id}/{version_id}/original.{ext}"

    def get_bucket_name(self) -> str:
        """Get the S3 bucket name."""
        return self.bucket_name

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
        await self.put_bytes(key, data, content_type, metadata)
        return key

    async def download(self, key: str) -> bytes:
        """Download a file (legacy method - use get_bytes instead)."""
        if key.startswith(self.URI_SCHEME):
            return await self.get_bytes(key)
        return await self.get_bytes(self._key_to_uri(key))

    async def get_url(self, key: str, expires_in: int = 3600) -> str:
        """Get URL for file (legacy method - use sign_download_url instead)."""
        if key.startswith(self.URI_SCHEME):
            return await self.sign_download_url(key, expires_in)
        return await self.sign_download_url(self._key_to_uri(key), expires_in)
