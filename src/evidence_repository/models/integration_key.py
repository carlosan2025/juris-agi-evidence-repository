"""Database models for third-party integration API keys."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, String, Text, func, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from evidence_repository.models.base import Base, TimestampMixin, UUIDMixin


class IntegrationProvider(str, enum.Enum):
    """Supported third-party integration providers."""

    OPENAI = "openai"
    LOVEPDF = "lovepdf"
    AWS = "aws"  # For S3 storage
    ANTHROPIC = "anthropic"  # Future: Claude integration
    CUSTOM = "custom"  # For user-defined integrations


class IntegrationKey(Base, UUIDMixin, TimestampMixin):
    """Model for storing encrypted third-party API keys.

    API keys are encrypted at rest using Fernet symmetric encryption.
    The encryption key is derived from the application's JWT secret.
    """

    __tablename__ = "integration_keys"

    # Provider identification
    provider: Mapped[IntegrationProvider] = mapped_column(
        Enum(
            IntegrationProvider,
            name="integrationprovider",
            create_type=False,  # Created by migration
            values_callable=lambda x: [e.value for e in x],  # Use lowercase values
        ),
        nullable=False,
        index=True,
    )

    # Human-readable name/label for the key
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    # Key identifier (e.g., "api_key", "public_key", "secret_key", "access_key_id")
    key_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    # Encrypted API key value
    encrypted_value: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    # Optional description
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Whether this key is currently active
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    # Last time the key was used (for monitoring)
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Who created/updated this key (actor_id from auth)
    created_by: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    updated_by: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    def __repr__(self) -> str:
        return f"<IntegrationKey {self.provider.value}:{self.key_type} ({self.name})>"
