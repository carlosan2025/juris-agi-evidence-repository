"""Debug endpoints for troubleshooting."""

import os
from fastapi import APIRouter, Depends

from evidence_repository.api.dependencies import User, get_current_user
from evidence_repository.config import get_settings

router = APIRouter(tags=["Debug"])


@router.get(
    "/config-check",
    summary="Check Configuration",
    description="Check if important configuration values are set (values are not exposed).",
)
async def check_config(
    user: User = Depends(get_current_user),
) -> dict:
    """Check configuration status without exposing values."""
    settings = get_settings()

    # Check which config values are set (without exposing actual values)
    return {
        "openai_api_key_set": bool(settings.openai_api_key),
        "openai_api_key_length": len(settings.openai_api_key) if settings.openai_api_key else 0,
        "openai_api_key_prefix": settings.openai_api_key[:7] + "..." if settings.openai_api_key and len(settings.openai_api_key) > 10 else "not set",
        "openai_env_var_set": bool(os.environ.get("OPENAI_API_KEY")),
        "database_url_set": bool(settings.database_url),
        "storage_backend": settings.storage_backend,
        "s3_bucket": settings.s3_bucket_name,
        "s3_endpoint_set": bool(settings.s3_endpoint_url),
    }
