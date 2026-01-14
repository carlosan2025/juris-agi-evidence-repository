"""Encryption service for securing sensitive data like API keys.

Uses Fernet symmetric encryption with a key derived from the application's
JWT secret. This provides secure encryption at rest while allowing the
application to decrypt values when needed.
"""

import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken

from evidence_repository.config import get_settings

logger = logging.getLogger(__name__)


class EncryptionError(Exception):
    """Raised when encryption/decryption fails."""

    pass


class EncryptionService:
    """Service for encrypting and decrypting sensitive values.

    Uses Fernet (AES-128-CBC) encryption with a key derived from
    the application's JWT secret using SHA-256.
    """

    def __init__(self, secret_key: str | None = None):
        """Initialize the encryption service.

        Args:
            secret_key: Secret key for deriving encryption key.
                        If not provided, uses JWT secret from settings.
        """
        if secret_key is None:
            settings = get_settings()
            secret_key = settings.jwt_secret_key

        # Derive a 32-byte key from the secret using SHA-256
        # Then base64 encode it for Fernet (requires URL-safe base64)
        key_bytes = hashlib.sha256(secret_key.encode()).digest()
        fernet_key = base64.urlsafe_b64encode(key_bytes)
        self._fernet = Fernet(fernet_key)

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a plaintext string.

        Args:
            plaintext: The string to encrypt.

        Returns:
            Base64-encoded encrypted string.

        Raises:
            EncryptionError: If encryption fails.
        """
        try:
            encrypted_bytes = self._fernet.encrypt(plaintext.encode("utf-8"))
            return encrypted_bytes.decode("utf-8")
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            raise EncryptionError(f"Failed to encrypt value: {e}") from e

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt an encrypted string.

        Args:
            ciphertext: The base64-encoded encrypted string.

        Returns:
            The decrypted plaintext string.

        Raises:
            EncryptionError: If decryption fails (invalid key or corrupted data).
        """
        try:
            decrypted_bytes = self._fernet.decrypt(ciphertext.encode("utf-8"))
            return decrypted_bytes.decode("utf-8")
        except InvalidToken:
            logger.error("Decryption failed: invalid token (wrong key or corrupted data)")
            raise EncryptionError(
                "Failed to decrypt value: invalid token. "
                "This may indicate the encryption key has changed or the data is corrupted."
            )
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            raise EncryptionError(f"Failed to decrypt value: {e}") from e

    @staticmethod
    def mask_value(value: str, visible_prefix: int = 3, visible_suffix: int = 4) -> str:
        """Create a masked version of a sensitive value.

        Args:
            value: The value to mask.
            visible_prefix: Number of characters to show at the start.
            visible_suffix: Number of characters to show at the end.

        Returns:
            Masked string like "sk-...abc1"
        """
        if len(value) <= visible_prefix + visible_suffix:
            return "*" * len(value)

        prefix = value[:visible_prefix]
        suffix = value[-visible_suffix:]
        return f"{prefix}...{suffix}"


# Global instance for convenience
_encryption_service: EncryptionService | None = None


def get_encryption_service() -> EncryptionService:
    """Get the global encryption service instance."""
    global _encryption_service
    if _encryption_service is None:
        _encryption_service = EncryptionService()
    return _encryption_service
