"""Pydantic schemas for integration key management."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from evidence_repository.models.integration_key import IntegrationProvider


class IntegrationKeyBase(BaseModel):
    """Base schema for integration keys."""

    provider: IntegrationProvider = Field(
        ..., description="Third-party provider (openai, lovepdf, aws, etc.)"
    )
    name: str = Field(
        ..., min_length=1, max_length=255, description="Human-readable name for this key"
    )
    key_type: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Type of key (api_key, public_key, secret_key, access_key_id, etc.)",
    )
    description: str | None = Field(None, description="Optional description")
    is_active: bool = Field(True, description="Whether this key is active")


class IntegrationKeyCreate(IntegrationKeyBase):
    """Schema for creating a new integration key."""

    value: str = Field(
        ..., min_length=1, description="The actual API key value (will be encrypted)"
    )


class IntegrationKeyUpdate(BaseModel):
    """Schema for updating an integration key."""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None)
    is_active: bool | None = Field(None)
    value: str | None = Field(
        None, min_length=1, description="New key value (will be encrypted if provided)"
    )


class IntegrationKeyResponse(IntegrationKeyBase):
    """Schema for integration key responses (without the actual key value)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime
    last_used_at: datetime | None = None
    created_by: str | None = None
    updated_by: str | None = None

    # Value is masked for security
    masked_value: str = Field(
        ..., description="Masked version of the key (e.g., 'sk-...abc123')"
    )


class IntegrationKeyWithValue(IntegrationKeyResponse):
    """Schema including the decrypted key value (for admin use only)."""

    decrypted_value: str = Field(..., description="The actual decrypted API key value")


class IntegrationKeyListResponse(BaseModel):
    """Response for listing integration keys."""

    items: list[IntegrationKeyResponse]
    total: int
    by_provider: dict[str, int] = Field(
        default_factory=dict, description="Count of keys per provider"
    )


class IntegrationStatusResponse(BaseModel):
    """Response showing status of all integration configurations."""

    openai: "IntegrationStatus"
    lovepdf: "IntegrationStatus"
    aws: "IntegrationStatus"


class IntegrationStatus(BaseModel):
    """Status of a single integration."""

    configured: bool = Field(
        ..., description="Whether at least one active key exists for this provider"
    )
    keys_count: int = Field(..., description="Number of keys configured")
    active_keys_count: int = Field(..., description="Number of active keys")
    last_used: datetime | None = Field(
        None, description="When any key for this provider was last used"
    )
    required_key_types: list[str] = Field(
        ..., description="Key types required for this integration"
    )
    configured_key_types: list[str] = Field(
        ..., description="Key types that are configured"
    )
    missing_key_types: list[str] = Field(
        ..., description="Key types that are still needed"
    )


class TestIntegrationRequest(BaseModel):
    """Request to test an integration."""

    provider: IntegrationProvider


class TestIntegrationResponse(BaseModel):
    """Response from testing an integration."""

    provider: IntegrationProvider
    success: bool
    message: str
    details: dict | None = None


# Provider-specific key type requirements
PROVIDER_KEY_REQUIREMENTS: dict[IntegrationProvider, list[str]] = {
    IntegrationProvider.OPENAI: ["api_key"],
    IntegrationProvider.LOVEPDF: ["public_key", "secret_key"],
    IntegrationProvider.AWS: ["access_key_id", "secret_access_key"],
    IntegrationProvider.ANTHROPIC: ["api_key"],
    IntegrationProvider.CUSTOM: [],  # No requirements for custom providers
}
