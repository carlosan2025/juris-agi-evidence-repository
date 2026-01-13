"""Common schemas used across the API."""

from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class BaseSchema(BaseModel):
    """Base schema with common configuration."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
    )


class ErrorResponse(BaseModel):
    """Standard error response."""

    error: str = Field(..., description="Error type/code")
    message: str = Field(..., description="Human-readable error message")
    details: dict[str, Any] | None = Field(
        default=None, description="Additional error details"
    )


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = Field(..., description="Service status (healthy, degraded, unhealthy)")
    version: str = Field(..., description="API version")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Current server time"
    )
    database: str = Field(default="unknown", description="Database connection status")
    redis: str = Field(default="unknown", description="Redis connection status")
    details: dict[str, Any] | None = Field(
        default=None, description="Additional health details"
    )


class PaginationParams(BaseModel):
    """Pagination parameters."""

    page: int = Field(default=1, ge=1, description="Page number (1-indexed)")
    page_size: int = Field(
        default=20, ge=1, le=100, description="Items per page (max 100)"
    )

    @property
    def offset(self) -> int:
        """Calculate database offset."""
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        """Get limit (same as page_size)."""
        return self.page_size


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response."""

    items: list[T] = Field(..., description="Page items")
    total: int = Field(..., description="Total number of items")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Items per page")
    pages: int = Field(..., description="Total number of pages")

    @classmethod
    def create(
        cls,
        items: list[T],
        total: int,
        page: int,
        page_size: int,
    ) -> "PaginatedResponse[T]":
        """Create a paginated response."""
        pages = (total + page_size - 1) // page_size if total > 0 else 0
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )


class TimestampMixin(BaseModel):
    """Mixin for timestamp fields."""

    created_at: datetime
    updated_at: datetime
