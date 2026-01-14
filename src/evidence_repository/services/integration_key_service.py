"""Service for managing third-party integration API keys."""

import logging
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from evidence_repository.models.integration_key import IntegrationKey, IntegrationProvider
from evidence_repository.schemas.integration_key import (
    IntegrationKeyCreate,
    IntegrationKeyResponse,
    IntegrationKeyUpdate,
    IntegrationKeyWithValue,
    IntegrationStatus,
    IntegrationStatusResponse,
    PROVIDER_KEY_REQUIREMENTS,
)
from evidence_repository.services.encryption import (
    EncryptionService,
    get_encryption_service,
)

logger = logging.getLogger(__name__)


class IntegrationKeyService:
    """Service for CRUD operations on integration API keys."""

    def __init__(
        self,
        db: AsyncSession,
        encryption_service: EncryptionService | None = None,
    ):
        self.db = db
        self.encryption = encryption_service or get_encryption_service()

    async def create_key(
        self,
        data: IntegrationKeyCreate,
        actor_id: str | None = None,
    ) -> IntegrationKeyResponse:
        """Create a new integration key.

        Args:
            data: Key creation data including the plaintext value.
            actor_id: ID of the user creating the key.

        Returns:
            The created key response (without decrypted value).
        """
        # Encrypt the API key value
        encrypted_value = self.encryption.encrypt(data.value)
        masked_value = self.encryption.mask_value(data.value)

        key = IntegrationKey(
            provider=data.provider,
            name=data.name,
            key_type=data.key_type,
            encrypted_value=encrypted_value,
            description=data.description,
            is_active=data.is_active,
            created_by=actor_id,
            updated_by=actor_id,
        )

        self.db.add(key)
        await self.db.commit()
        await self.db.refresh(key)

        logger.info(
            f"Created integration key: {key.provider.value}:{key.key_type} "
            f"(id={key.id}, actor={actor_id})"
        )

        return IntegrationKeyResponse(
            id=key.id,
            provider=key.provider,
            name=key.name,
            key_type=key.key_type,
            description=key.description,
            is_active=key.is_active,
            created_at=key.created_at,
            updated_at=key.updated_at,
            last_used_at=key.last_used_at,
            created_by=key.created_by,
            updated_by=key.updated_by,
            masked_value=masked_value,
        )

    async def get_key(
        self,
        key_id: UUID,
        include_value: bool = False,
    ) -> IntegrationKeyResponse | IntegrationKeyWithValue | None:
        """Get an integration key by ID.

        Args:
            key_id: The UUID of the key.
            include_value: If True, include the decrypted value (admin only).

        Returns:
            The key response or None if not found.
        """
        result = await self.db.execute(
            select(IntegrationKey).where(IntegrationKey.id == key_id)
        )
        key = result.scalar_one_or_none()

        if key is None:
            return None

        # Decrypt to get masked value
        decrypted_value = self.encryption.decrypt(key.encrypted_value)
        masked_value = self.encryption.mask_value(decrypted_value)

        if include_value:
            return IntegrationKeyWithValue(
                id=key.id,
                provider=key.provider,
                name=key.name,
                key_type=key.key_type,
                description=key.description,
                is_active=key.is_active,
                created_at=key.created_at,
                updated_at=key.updated_at,
                last_used_at=key.last_used_at,
                created_by=key.created_by,
                updated_by=key.updated_by,
                masked_value=masked_value,
                decrypted_value=decrypted_value,
            )

        return IntegrationKeyResponse(
            id=key.id,
            provider=key.provider,
            name=key.name,
            key_type=key.key_type,
            description=key.description,
            is_active=key.is_active,
            created_at=key.created_at,
            updated_at=key.updated_at,
            last_used_at=key.last_used_at,
            created_by=key.created_by,
            updated_by=key.updated_by,
            masked_value=masked_value,
        )

    async def list_keys(
        self,
        provider: IntegrationProvider | None = None,
        is_active: bool | None = None,
    ) -> list[IntegrationKeyResponse]:
        """List integration keys with optional filters.

        Args:
            provider: Filter by provider.
            is_active: Filter by active status.

        Returns:
            List of key responses.
        """
        query = select(IntegrationKey)

        if provider is not None:
            query = query.where(IntegrationKey.provider == provider)
        if is_active is not None:
            query = query.where(IntegrationKey.is_active == is_active)

        query = query.order_by(IntegrationKey.provider, IntegrationKey.key_type)

        result = await self.db.execute(query)
        keys = result.scalars().all()

        responses = []
        for key in keys:
            decrypted_value = self.encryption.decrypt(key.encrypted_value)
            masked_value = self.encryption.mask_value(decrypted_value)
            responses.append(
                IntegrationKeyResponse(
                    id=key.id,
                    provider=key.provider,
                    name=key.name,
                    key_type=key.key_type,
                    description=key.description,
                    is_active=key.is_active,
                    created_at=key.created_at,
                    updated_at=key.updated_at,
                    last_used_at=key.last_used_at,
                    created_by=key.created_by,
                    updated_by=key.updated_by,
                    masked_value=masked_value,
                )
            )

        return responses

    async def update_key(
        self,
        key_id: UUID,
        data: IntegrationKeyUpdate,
        actor_id: str | None = None,
    ) -> IntegrationKeyResponse | None:
        """Update an integration key.

        Args:
            key_id: The UUID of the key to update.
            data: Update data.
            actor_id: ID of the user making the update.

        Returns:
            The updated key response or None if not found.
        """
        result = await self.db.execute(
            select(IntegrationKey).where(IntegrationKey.id == key_id)
        )
        key = result.scalar_one_or_none()

        if key is None:
            return None

        # Update fields if provided
        if data.name is not None:
            key.name = data.name
        if data.description is not None:
            key.description = data.description
        if data.is_active is not None:
            key.is_active = data.is_active
        if data.value is not None:
            key.encrypted_value = self.encryption.encrypt(data.value)

        key.updated_by = actor_id

        await self.db.commit()
        await self.db.refresh(key)

        decrypted_value = self.encryption.decrypt(key.encrypted_value)
        masked_value = self.encryption.mask_value(decrypted_value)

        logger.info(
            f"Updated integration key: {key.provider.value}:{key.key_type} "
            f"(id={key.id}, actor={actor_id})"
        )

        return IntegrationKeyResponse(
            id=key.id,
            provider=key.provider,
            name=key.name,
            key_type=key.key_type,
            description=key.description,
            is_active=key.is_active,
            created_at=key.created_at,
            updated_at=key.updated_at,
            last_used_at=key.last_used_at,
            created_by=key.created_by,
            updated_by=key.updated_by,
            masked_value=masked_value,
        )

    async def delete_key(self, key_id: UUID) -> bool:
        """Delete an integration key.

        Args:
            key_id: The UUID of the key to delete.

        Returns:
            True if deleted, False if not found.
        """
        result = await self.db.execute(
            select(IntegrationKey).where(IntegrationKey.id == key_id)
        )
        key = result.scalar_one_or_none()

        if key is None:
            return False

        logger.info(
            f"Deleting integration key: {key.provider.value}:{key.key_type} (id={key.id})"
        )

        await self.db.delete(key)
        await self.db.commit()
        return True

    async def get_provider_key(
        self,
        provider: IntegrationProvider,
        key_type: str,
    ) -> str | None:
        """Get the decrypted value of a specific provider key.

        This method also updates the last_used_at timestamp.

        Args:
            provider: The provider.
            key_type: The type of key (e.g., "api_key", "secret_key").

        Returns:
            The decrypted key value or None if not found/inactive.
        """
        result = await self.db.execute(
            select(IntegrationKey).where(
                IntegrationKey.provider == provider,
                IntegrationKey.key_type == key_type,
                IntegrationKey.is_active == True,
            )
        )
        key = result.scalar_one_or_none()

        if key is None:
            return None

        # Update last_used_at
        key.last_used_at = datetime.utcnow()
        await self.db.commit()

        return self.encryption.decrypt(key.encrypted_value)

    async def get_integration_status(self) -> IntegrationStatusResponse:
        """Get the configuration status of all integrations.

        Returns:
            Status of all supported integrations.
        """
        # Query all keys grouped by provider
        result = await self.db.execute(
            select(IntegrationKey).order_by(IntegrationKey.provider)
        )
        all_keys = result.scalars().all()

        # Group keys by provider
        keys_by_provider: dict[IntegrationProvider, list[IntegrationKey]] = {}
        for key in all_keys:
            if key.provider not in keys_by_provider:
                keys_by_provider[key.provider] = []
            keys_by_provider[key.provider].append(key)

        def get_status(provider: IntegrationProvider) -> IntegrationStatus:
            keys = keys_by_provider.get(provider, [])
            active_keys = [k for k in keys if k.is_active]
            required = PROVIDER_KEY_REQUIREMENTS.get(provider, [])
            configured_types = list(set(k.key_type for k in active_keys))
            missing_types = [t for t in required if t not in configured_types]

            last_used = None
            for key in keys:
                if key.last_used_at:
                    if last_used is None or key.last_used_at > last_used:
                        last_used = key.last_used_at

            return IntegrationStatus(
                configured=len(missing_types) == 0 and len(required) > 0,
                keys_count=len(keys),
                active_keys_count=len(active_keys),
                last_used=last_used,
                required_key_types=required,
                configured_key_types=configured_types,
                missing_key_types=missing_types,
            )

        return IntegrationStatusResponse(
            openai=get_status(IntegrationProvider.OPENAI),
            lovepdf=get_status(IntegrationProvider.LOVEPDF),
            aws=get_status(IntegrationProvider.AWS),
        )
