"""AWS S3 / Cloudflare R2 storage backend with presigned URL support."""

import asyncio
from typing import AsyncIterator

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from evidence_repository.storage.base import StorageBackend, StorageMetadata


class S3Storage(StorageBackend):
    """Storage backend using AWS S3 or S3-compatible services (Cloudflare R2).

    File URI Format: s3://bucket-name/key/path

    Path Key Layout: {document_id}/{version_id}/original.{ext}

    Configuration:
        - AWS_ACCESS_KEY_ID: AWS/R2 access key
        - AWS_SECRET_ACCESS_KEY: AWS/R2 secret key
        - AWS_REGION: AWS region (use "auto" for Cloudflare R2)
        - S3_BUCKET_NAME: Target S3/R2 bucket
        - S3_PREFIX: Optional key prefix for all objects
        - S3_ENDPOINT_URL: Custom endpoint for S3-compatible services (required for R2)
    """

    URI_SCHEME = "s3://"

    def __init__(
        self,
        bucket_name: str,
        aws_access_key_id: str = "",
        aws_secret_access_key: str = "",
        region: str = "auto",
        prefix: str = "",
        endpoint_url: str | None = None,
    ):
        """Initialize S3/R2 storage backend.

        Args:
            bucket_name: S3/R2 bucket name.
            aws_access_key_id: AWS/R2 access key ID.
            aws_secret_access_key: AWS/R2 secret access key.
            region: AWS region (use "auto" for Cloudflare R2).
            prefix: Optional key prefix for all objects.
            endpoint_url: Custom S3 endpoint URL (required for R2).
        """
        self.bucket_name = bucket_name
        self.aws_access_key_id = aws_access_key_id
        self.aws_secret_access_key = aws_secret_access_key
        self.region = region
        self.prefix = prefix.strip("/") if prefix else ""
        self.endpoint_url = endpoint_url

        # Configure boto3 for S3-compatible services
        config = Config(
            signature_version='s3v4',
            s3={'addressing_style': 'path'},
            retries={'max_attempts': 3, 'mode': 'standard'}
        )

        client_kwargs: dict = {
            'service_name': 's3',
            'config': config,
        }

        # Only set region if not "auto" (R2 uses auto)
        if region and region != "auto":
            client_kwargs['region_name'] = region

        if aws_access_key_id and aws_secret_access_key:
            client_kwargs['aws_access_key_id'] = aws_access_key_id
            client_kwargs['aws_secret_access_key'] = aws_secret_access_key

        if endpoint_url:
            client_kwargs['endpoint_url'] = endpoint_url

        self._client = boto3.client(**client_kwargs)

    def _get_full_key(self, path_key: str) -> str:
        """Get the full S3 key including prefix."""
        path_key = path_key.lstrip("/")
        if self.prefix:
            return f"{self.prefix}/{path_key}"
        return path_key

    def _key_to_uri(self, key: str) -> str:
        """Convert a storage key to an S3 URI."""
        full_key = self._get_full_key(key)
        return f"{self.URI_SCHEME}{self.bucket_name}/{full_key}"

    def _uri_to_key(self, file_uri: str) -> str:
        """Convert an S3 URI to a key."""
        if not file_uri.startswith(self.URI_SCHEME):
            raise ValueError(f"Invalid S3 URI: {file_uri} (expected s3:// scheme)")

        remainder = file_uri[len(self.URI_SCHEME):]
        parts = remainder.split("/", 1)
        if len(parts) < 2:
            raise ValueError(f"Invalid S3 URI: {file_uri} (missing key)")

        bucket, key = parts
        if bucket != self.bucket_name:
            raise ValueError(f"Invalid S3 URI: {file_uri} (wrong bucket)")

        return key

    # =========================================================================
    # Presigned URL Operations (for bypassing Vercel's 4.5MB limit)
    # =========================================================================

    async def generate_presigned_upload_url(
        self,
        path_key: str,
        content_type: str,
        ttl_seconds: int = 3600,
    ) -> dict:
        """Generate a presigned PUT URL for direct upload to S3/R2.

        This allows clients to upload directly to storage, bypassing
        the backend and Vercel's 4.5MB payload limit.

        Args:
            path_key: Path key for the object.
            content_type: Expected MIME type of the upload.
            ttl_seconds: URL expiration in seconds.

        Returns:
            Dict with upload URL and metadata.
        """
        full_key = self._get_full_key(path_key)

        presigned_url = await asyncio.to_thread(
            self._client.generate_presigned_url,
            'put_object',
            Params={
                'Bucket': self.bucket_name,
                'Key': full_key,
                'ContentType': content_type,
            },
            ExpiresIn=ttl_seconds,
        )

        return {
            "upload_url": presigned_url,
            "method": "PUT",
            "key": full_key,
            "file_uri": f"{self.URI_SCHEME}{self.bucket_name}/{full_key}",
            "content_type": content_type,
            "expires_in": ttl_seconds,
        }

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
        """Upload bytes to S3/R2."""
        full_key = self._get_full_key(path_key)
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self.bucket_name,
            Key=full_key,
            Body=data,
            ContentType=content_type,
            Metadata=metadata or {},
        )
        return f"{self.URI_SCHEME}{self.bucket_name}/{full_key}"

    async def put_file(
        self,
        path_key: str,
        local_path: str,
        content_type: str,
        metadata: dict[str, str] | None = None,
    ) -> str:
        """Upload a local file to S3/R2."""
        from boto3.s3.transfer import TransferConfig

        full_key = self._get_full_key(path_key)
        config = TransferConfig(
            multipart_threshold=8 * 1024 * 1024,  # 8MB
            max_concurrency=10,
        )
        extra_args: dict = {
            'ContentType': content_type,
        }
        if metadata:
            extra_args['Metadata'] = metadata

        await asyncio.to_thread(
            self._client.upload_file,
            local_path,
            self.bucket_name,
            full_key,
            ExtraArgs=extra_args,
            Config=config,
        )
        return f"{self.URI_SCHEME}{self.bucket_name}/{full_key}"

    # =========================================================================
    # Core Read Operations
    # =========================================================================

    async def get_bytes(self, file_uri: str) -> bytes:
        """Download file content from S3/R2 as bytes."""
        key = self._uri_to_key(file_uri)
        response = await asyncio.to_thread(
            self._client.get_object,
            Bucket=self.bucket_name,
            Key=key,
        )
        body = response['Body']
        data = await asyncio.to_thread(body.read)
        await asyncio.to_thread(body.close)
        return data

    async def get_stream(
        self, file_uri: str, chunk_size: int = 8192
    ) -> AsyncIterator[bytes]:
        """Stream file content from S3/R2 in chunks."""
        key = self._uri_to_key(file_uri)
        response = await asyncio.to_thread(
            self._client.get_object,
            Bucket=self.bucket_name,
            Key=key,
        )
        body = response['Body']
        try:
            while True:
                chunk = await asyncio.to_thread(body.read, chunk_size)
                if not chunk:
                    break
                yield chunk
        finally:
            await asyncio.to_thread(body.close)

    # =========================================================================
    # File Management Operations
    # =========================================================================

    async def delete(self, file_uri: str) -> bool:
        """Delete a file from S3/R2."""
        key = self._uri_to_key(file_uri)
        await asyncio.to_thread(
            self._client.delete_object,
            Bucket=self.bucket_name,
            Key=key,
        )
        return True

    async def exists(self, file_uri: str) -> bool:
        """Check if an object exists in S3/R2."""
        key = self._uri_to_key(file_uri)
        try:
            await asyncio.to_thread(
                self._client.head_object,
                Bucket=self.bucket_name,
                Key=key,
            )
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                return False
            raise

    # =========================================================================
    # URL/Access Operations
    # =========================================================================

    async def sign_download_url(self, file_uri: str, ttl_seconds: int = 3600) -> str:
        """Generate a pre-signed URL for S3/R2 object download."""
        key = self._uri_to_key(file_uri)
        return await asyncio.to_thread(
            self._client.generate_presigned_url,
            'get_object',
            Params={'Bucket': self.bucket_name, 'Key': key},
            ExpiresIn=ttl_seconds,
        )

    # =========================================================================
    # Metadata Operations
    # =========================================================================

    async def get_metadata(self, file_uri: str) -> StorageMetadata:
        """Get metadata for an S3/R2 object."""
        key = self._uri_to_key(file_uri)
        response = await asyncio.to_thread(
            self._client.head_object,
            Bucket=self.bucket_name,
            Key=key,
        )
        return StorageMetadata(
            key=key,
            size=response['ContentLength'],
            content_type=response.get('ContentType', 'application/octet-stream'),
            etag=response.get('ETag', '').strip('"'),
            last_modified=response['LastModified'].isoformat(),
        )

    # =========================================================================
    # Listing Operations
    # =========================================================================

    async def list_keys(self, prefix: str = "") -> list[str]:
        """List objects in S3/R2 bucket with prefix."""
        full_prefix = self._get_full_key(prefix) if prefix else (self.prefix or "")

        def _list_all():
            keys = []
            paginator = self._client.get_paginator('list_objects_v2')
            for page in paginator.paginate(Bucket=self.bucket_name, Prefix=full_prefix):
                for obj in page.get('Contents', []):
                    keys.append(obj['Key'])
            return keys

        return await asyncio.to_thread(_list_all)

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

    def get_bucket_name(self) -> str:
        """Get the S3/R2 bucket name."""
        return self.bucket_name

    # =========================================================================
    # Legacy Compatibility
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
