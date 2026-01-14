"""Admin API routes for managing integrations and system configuration."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from evidence_repository.api.dependencies import User, get_current_user, get_db
from evidence_repository.models.integration_key import IntegrationProvider
from evidence_repository.schemas.integration_key import (
    IntegrationKeyCreate,
    IntegrationKeyListResponse,
    IntegrationKeyResponse,
    IntegrationKeyUpdate,
    IntegrationKeyWithValue,
    IntegrationStatusResponse,
    TestIntegrationRequest,
    TestIntegrationResponse,
)
from evidence_repository.services.integration_key_service import IntegrationKeyService

router = APIRouter()


# =============================================================================
# Integration Key Management
# =============================================================================


@router.get(
    "/integrations/status",
    response_model=IntegrationStatusResponse,
    summary="Get integration status",
    description="Get the configuration status of all third-party integrations.",
)
async def get_integration_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> IntegrationStatusResponse:
    """Get the status of all configured integrations."""
    service = IntegrationKeyService(db)
    return await service.get_integration_status()


@router.get(
    "/integrations/keys",
    response_model=IntegrationKeyListResponse,
    summary="List integration keys",
    description="List all configured integration API keys (values are masked).",
)
async def list_integration_keys(
    provider: IntegrationProvider | None = Query(
        None, description="Filter by provider"
    ),
    is_active: bool | None = Query(None, description="Filter by active status"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> IntegrationKeyListResponse:
    """List all integration keys."""
    service = IntegrationKeyService(db)
    keys = await service.list_keys(provider=provider, is_active=is_active)

    # Count by provider
    by_provider: dict[str, int] = {}
    for key in keys:
        provider_name = key.provider.value
        by_provider[provider_name] = by_provider.get(provider_name, 0) + 1

    return IntegrationKeyListResponse(
        items=keys,
        total=len(keys),
        by_provider=by_provider,
    )


@router.post(
    "/integrations/keys",
    response_model=IntegrationKeyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create integration key",
    description="Create a new integration API key. The value will be encrypted at rest.",
)
async def create_integration_key(
    data: IntegrationKeyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> IntegrationKeyResponse:
    """Create a new integration key."""
    service = IntegrationKeyService(db)
    return await service.create_key(data, actor_id=current_user.id)


@router.get(
    "/integrations/keys/{key_id}",
    response_model=IntegrationKeyResponse,
    summary="Get integration key",
    description="Get details of a specific integration key (value is masked).",
)
async def get_integration_key(
    key_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> IntegrationKeyResponse:
    """Get an integration key by ID."""
    service = IntegrationKeyService(db)
    key = await service.get_key(key_id, include_value=False)

    if key is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Integration key {key_id} not found",
        )

    return key


@router.get(
    "/integrations/keys/{key_id}/reveal",
    response_model=IntegrationKeyWithValue,
    summary="Reveal integration key value",
    description="Get the decrypted value of an integration key. Use with caution.",
)
async def reveal_integration_key(
    key_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> IntegrationKeyWithValue:
    """Reveal the decrypted value of an integration key."""
    service = IntegrationKeyService(db)
    key = await service.get_key(key_id, include_value=True)

    if key is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Integration key {key_id} not found",
        )

    return key


@router.patch(
    "/integrations/keys/{key_id}",
    response_model=IntegrationKeyResponse,
    summary="Update integration key",
    description="Update an integration key's name, description, status, or value.",
)
async def update_integration_key(
    key_id: UUID,
    data: IntegrationKeyUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> IntegrationKeyResponse:
    """Update an integration key."""
    service = IntegrationKeyService(db)
    key = await service.update_key(key_id, data, actor_id=current_user.id)

    if key is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Integration key {key_id} not found",
        )

    return key


@router.delete(
    "/integrations/keys/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete integration key",
    description="Permanently delete an integration key.",
)
async def delete_integration_key(
    key_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Delete an integration key."""
    service = IntegrationKeyService(db)
    deleted = await service.delete_key(key_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Integration key {key_id} not found",
        )


@router.post(
    "/integrations/test",
    response_model=TestIntegrationResponse,
    summary="Test integration",
    description="Test that an integration is properly configured and working.",
)
async def test_integration(
    data: TestIntegrationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TestIntegrationResponse:
    """Test an integration by making a real API call to verify connectivity."""
    service = IntegrationKeyService(db)

    if data.provider == IntegrationProvider.OPENAI:
        return await _test_openai_integration(service, data.provider)

    elif data.provider == IntegrationProvider.LOVEPDF:
        return await _test_lovepdf_integration(service, data.provider)

    elif data.provider == IntegrationProvider.AWS:
        return await _test_aws_integration(service, data.provider)

    return TestIntegrationResponse(
        provider=data.provider,
        success=False,
        message=f"Testing not implemented for provider: {data.provider.value}",
    )


async def _test_openai_integration(
    service: IntegrationKeyService,
    provider: IntegrationProvider,
) -> TestIntegrationResponse:
    """Test OpenAI integration by generating a test embedding.

    This validates:
    1. API key is valid
    2. Embedding model is accessible
    3. We can generate embeddings (our primary use case)
    """
    import httpx
    import time

    api_key = await service.get_provider_key(IntegrationProvider.OPENAI, "api_key")
    if not api_key:
        return TestIntegrationResponse(
            provider=provider,
            success=False,
            message="OpenAI API key not configured",
        )

    try:
        start_time = time.time()

        async with httpx.AsyncClient() as client:
            # Test 1: Verify API key with models endpoint
            models_response = await client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10.0,
            )

            if models_response.status_code == 401:
                return TestIntegrationResponse(
                    provider=provider,
                    success=False,
                    message="Invalid API key - authentication failed",
                    details={"error": "API key is invalid or expired"},
                )
            elif models_response.status_code != 200:
                return TestIntegrationResponse(
                    provider=provider,
                    success=False,
                    message=f"OpenAI API returned status {models_response.status_code}",
                    details={"response": models_response.text[:200]},
                )

            models_data = models_response.json().get("data", [])
            model_ids = [m.get("id") for m in models_data]

            # Check for embedding model availability
            embedding_model = "text-embedding-3-small"
            has_embedding_model = embedding_model in model_ids

            # Test 2: Generate a test embedding to verify full functionality
            embedding_response = await client.post(
                "https://api.openai.com/v1/embeddings",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": embedding_model,
                    "input": "Health check test embedding",
                },
                timeout=15.0,
            )

            elapsed_time = time.time() - start_time

            if embedding_response.status_code == 200:
                embedding_data = embedding_response.json()
                embedding_dim = len(embedding_data.get("data", [{}])[0].get("embedding", []))
                tokens_used = embedding_data.get("usage", {}).get("total_tokens", 0)

                return TestIntegrationResponse(
                    provider=provider,
                    success=True,
                    message="OpenAI integration fully operational",
                    details={
                        "models_available": len(models_data),
                        "embedding_model": embedding_model,
                        "embedding_dimensions": embedding_dim,
                        "test_tokens_used": tokens_used,
                        "response_time_ms": round(elapsed_time * 1000),
                        "has_gpt4": "gpt-4" in model_ids or "gpt-4-turbo" in model_ids,
                    },
                )
            else:
                error_detail = embedding_response.json().get("error", {}).get("message", "Unknown error")
                return TestIntegrationResponse(
                    provider=provider,
                    success=False,
                    message=f"Embedding test failed: {error_detail}",
                    details={
                        "status_code": embedding_response.status_code,
                        "models_available": len(models_data),
                    },
                )

    except httpx.TimeoutException:
        return TestIntegrationResponse(
            provider=provider,
            success=False,
            message="Connection timeout - OpenAI API is slow or unreachable",
        )
    except Exception as e:
        return TestIntegrationResponse(
            provider=provider,
            success=False,
            message=f"Failed to connect to OpenAI: {str(e)}",
        )


async def _test_lovepdf_integration(
    service: IntegrationKeyService,
    provider: IntegrationProvider,
) -> TestIntegrationResponse:
    """Test LovePDF integration by authenticating and starting a test task.

    This validates:
    1. Public key is valid
    2. Secret key can authenticate
    3. API is accessible
    """
    import httpx

    public_key = await service.get_provider_key(IntegrationProvider.LOVEPDF, "public_key")
    secret_key = await service.get_provider_key(IntegrationProvider.LOVEPDF, "secret_key")

    missing = []
    if not public_key:
        missing.append("public_key")
    if not secret_key:
        missing.append("secret_key")

    if missing:
        return TestIntegrationResponse(
            provider=provider,
            success=False,
            message=f"LovePDF keys not configured: {', '.join(missing)}",
        )

    try:
        async with httpx.AsyncClient() as client:
            # LovePDF authentication - get a token using the keys
            auth_response = await client.post(
                "https://api.ilovepdf.com/v1/auth",
                json={"public_key": public_key},
                timeout=10.0,
            )

            if auth_response.status_code == 401:
                return TestIntegrationResponse(
                    provider=provider,
                    success=False,
                    message="Invalid public key - authentication failed",
                    details={"error": "Public key is invalid"},
                )
            elif auth_response.status_code != 200:
                return TestIntegrationResponse(
                    provider=provider,
                    success=False,
                    message=f"LovePDF API returned status {auth_response.status_code}",
                    details={"response": auth_response.text[:200]},
                )

            auth_data = auth_response.json()
            token = auth_data.get("token")

            if not token:
                return TestIntegrationResponse(
                    provider=provider,
                    success=False,
                    message="LovePDF authentication failed - no token received",
                )

            # Test starting a task (we'll use pdfjpg as a simple test)
            # This validates the token works but doesn't actually process anything
            task_response = await client.get(
                "https://api.ilovepdf.com/v1/start/pdfjpg",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10.0,
            )

            if task_response.status_code == 200:
                task_data = task_response.json()
                return TestIntegrationResponse(
                    provider=provider,
                    success=True,
                    message="LovePDF integration fully operational",
                    details={
                        "server": task_data.get("server"),
                        "task_id": task_data.get("task"),
                        "remaining_files": auth_data.get("remaining_files"),
                    },
                )
            else:
                return TestIntegrationResponse(
                    provider=provider,
                    success=False,
                    message=f"LovePDF task creation failed: {task_response.status_code}",
                    details={"response": task_response.text[:200]},
                )

    except httpx.TimeoutException:
        return TestIntegrationResponse(
            provider=provider,
            success=False,
            message="Connection timeout - LovePDF API is slow or unreachable",
        )
    except Exception as e:
        return TestIntegrationResponse(
            provider=provider,
            success=False,
            message=f"Failed to connect to LovePDF: {str(e)}",
        )


async def _test_aws_integration(
    service: IntegrationKeyService,
    provider: IntegrationProvider,
) -> TestIntegrationResponse:
    """Test AWS integration by listing S3 buckets.

    This validates:
    1. Access key ID is valid
    2. Secret access key can authenticate
    3. S3 is accessible
    """
    access_key = await service.get_provider_key(IntegrationProvider.AWS, "access_key_id")
    secret_key = await service.get_provider_key(IntegrationProvider.AWS, "secret_access_key")

    missing = []
    if not access_key:
        missing.append("access_key_id")
    if not secret_key:
        missing.append("secret_access_key")

    if missing:
        return TestIntegrationResponse(
            provider=provider,
            success=False,
            message=f"AWS keys not configured: {', '.join(missing)}",
        )

    try:
        import boto3
        from botocore.exceptions import ClientError, NoCredentialsError

        # Create S3 client with the stored credentials
        s3_client = boto3.client(
            "s3",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )

        # Try to list buckets - this validates credentials
        response = s3_client.list_buckets()
        buckets = [b["Name"] for b in response.get("Buckets", [])]

        return TestIntegrationResponse(
            provider=provider,
            success=True,
            message="AWS integration fully operational",
            details={
                "buckets_accessible": len(buckets),
                "bucket_names": buckets[:5],  # Show first 5 buckets
            },
        )

    except NoCredentialsError:
        return TestIntegrationResponse(
            provider=provider,
            success=False,
            message="Invalid AWS credentials",
        )
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        error_message = e.response.get("Error", {}).get("Message", str(e))
        return TestIntegrationResponse(
            provider=provider,
            success=False,
            message=f"AWS API error: {error_code}",
            details={"error": error_message},
        )
    except ImportError:
        return TestIntegrationResponse(
            provider=provider,
            success=False,
            message="boto3 library not installed - cannot test AWS integration",
        )
    except Exception as e:
        return TestIntegrationResponse(
            provider=provider,
            success=False,
            message=f"Failed to connect to AWS: {str(e)}",
        )
