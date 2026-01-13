"""API module - FastAPI routes and dependencies."""

from evidence_repository.api.dependencies import get_current_user, get_storage
from evidence_repository.api.routes import router

__all__ = [
    "router",
    "get_current_user",
    "get_storage",
]
