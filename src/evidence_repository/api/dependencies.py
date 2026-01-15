"""FastAPI dependency injection."""

from collections.abc import AsyncGenerator
from dataclasses import dataclass
from functools import lru_cache

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from evidence_repository.config import get_settings
from evidence_repository.db.session import get_db_session
from evidence_repository.storage import StorageBackend, get_storage_backend


@dataclass
class User:
    """Represents an authenticated user/API client.

    This is a placeholder that can be extended to support JWT claims
    when upgrading from API key auth.
    """

    id: str
    api_key: str | None = None
    # JWT fields (for future use)
    email: str | None = None
    name: str | None = None
    roles: list[str] | None = None

    @property
    def is_api_key_auth(self) -> bool:
        """Check if authenticated via API key."""
        return self.api_key is not None


async def verify_api_key(api_key: str) -> User:
    """Verify an API key and return a User.

    Args:
        api_key: The API key to verify.

    Returns:
        User object if valid.

    Raises:
        HTTPException: If API key is invalid.
    """
    settings = get_settings()

    if api_key in settings.api_keys:
        # Create a user based on the API key
        # Use hash to avoid exposing any part of the key
        import hashlib
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()[:12]
        return User(
            id=f"apikey:{key_hash}",
            api_key=api_key,
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API key",
        headers={"WWW-Authenticate": "ApiKey"},
    )


async def verify_jwt(token: str) -> User:
    """Verify a JWT token and return a User.

    This is a placeholder for future JWT authentication.

    Args:
        token: JWT token to verify.

    Returns:
        User object if valid.

    Raises:
        HTTPException: If token is invalid.
    """
    # TODO: Implement JWT verification when upgrading auth
    # from jose import JWTError, jwt
    # settings = get_settings()
    # try:
    #     payload = jwt.decode(
    #         token,
    #         settings.jwt_secret_key,
    #         algorithms=[settings.jwt_algorithm],
    #     )
    #     return User(
    #         id=payload["sub"],
    #         email=payload.get("email"),
    #         name=payload.get("name"),
    #         roles=payload.get("roles", []),
    #     )
    # except JWTError as e:
    #     raise HTTPException(
    #         status_code=status.HTTP_401_UNAUTHORIZED,
    #         detail=f"Invalid token: {e}",
    #         headers={"WWW-Authenticate": "Bearer"},
    #     )

    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="JWT authentication not yet implemented",
    )


async def get_current_user(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
) -> User:
    """Dependency to get the current authenticated user.

    Supports both API key and JWT authentication (JWT for future use).
    API key takes precedence for backwards compatibility.

    Args:
        request: FastAPI request object.
        x_api_key: API key from X-API-Key header.
        authorization: Authorization header (for Bearer token).

    Returns:
        Authenticated User object.

    Raises:
        HTTPException: If authentication fails.
    """
    # Try API key first
    if x_api_key:
        user = await verify_api_key(x_api_key)
        # Store user in request state for audit logging
        request.state.user = user
        return user

    # Try JWT Bearer token
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
        user = await verify_jwt(token)
        request.state.user = user
        return user

    # No authentication provided
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required. Provide X-API-Key header or Bearer token.",
        headers={"WWW-Authenticate": 'ApiKey, Bearer realm="evidence-repository"'},
    )


async def get_optional_user(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
) -> User | None:
    """Dependency to optionally get the current user.

    Returns None if no authentication is provided (for public endpoints).
    """
    if not x_api_key and not authorization:
        return None

    return await get_current_user(request, x_api_key, authorization)


@lru_cache
def get_storage() -> StorageBackend:
    """Dependency to get the configured storage backend.

    Cached to ensure single instance across requests.
    """
    return get_storage_backend()


async def get_db(db: AsyncSession = Depends(get_db_session)) -> AsyncGenerator[AsyncSession, None]:
    """Dependency to get database session.

    This is a pass-through to make the dependency injection cleaner.
    """
    yield db
