"""FastAPI middleware for audit logging and error handling."""

import logging
import time
import uuid
from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import insert
from starlette.middleware.base import BaseHTTPMiddleware

from evidence_repository.db.session import get_session_factory
from evidence_repository.models.audit import AuditAction, AuditLog

logger = logging.getLogger(__name__)


# Mapping of HTTP methods + paths to audit actions
AUDIT_ACTION_MAP: dict[tuple[str, str], AuditAction] = {
    # Documents
    ("POST", "/api/v1/documents"): AuditAction.DOCUMENT_UPLOAD,
    ("DELETE", "/api/v1/documents/{id}"): AuditAction.DOCUMENT_DELETE,
    # Projects
    ("POST", "/api/v1/projects"): AuditAction.PROJECT_CREATE,
    ("PATCH", "/api/v1/projects/{id}"): AuditAction.PROJECT_UPDATE,
    ("DELETE", "/api/v1/projects/{id}"): AuditAction.PROJECT_DELETE,
    ("POST", "/api/v1/projects/{id}/documents"): AuditAction.DOCUMENT_ATTACH,
    ("DELETE", "/api/v1/projects/{id}/documents/{doc_id}"): AuditAction.DOCUMENT_DETACH,
    # Extraction
    ("POST", "/api/v1/documents/{id}/extract"): AuditAction.EXTRACTION_START,
    # Search
    ("POST", "/api/v1/search"): AuditAction.SEARCH_EXECUTE,
    ("POST", "/api/v1/projects/{id}/search"): AuditAction.SEARCH_EXECUTE,
    # Evidence
    ("POST", "/api/v1/spans"): AuditAction.SPAN_CREATE,
    ("DELETE", "/api/v1/spans/{id}"): AuditAction.SPAN_DELETE,
    ("POST", "/api/v1/claims"): AuditAction.CLAIM_CREATE,
    ("DELETE", "/api/v1/claims/{id}"): AuditAction.CLAIM_DELETE,
    ("POST", "/api/v1/metrics"): AuditAction.METRIC_CREATE,
    ("DELETE", "/api/v1/metrics/{id}"): AuditAction.METRIC_DELETE,
    # Evidence Packs
    ("POST", "/api/v1/evidence-packs"): AuditAction.EVIDENCE_PACK_CREATE,
    ("PATCH", "/api/v1/evidence-packs/{id}"): AuditAction.EVIDENCE_PACK_UPDATE,
    ("DELETE", "/api/v1/evidence-packs/{id}"): AuditAction.EVIDENCE_PACK_DELETE,
    ("GET", "/api/v1/evidence-packs/{id}/export"): AuditAction.EVIDENCE_PACK_EXPORT,
}


def match_route_pattern(method: str, path: str) -> tuple[AuditAction | None, dict[str, str]]:
    """Match a request path to an audit action.

    Args:
        method: HTTP method.
        path: Request path.

    Returns:
        Tuple of (AuditAction, path_params) or (None, {}).
    """
    for (pattern_method, pattern_path), action in AUDIT_ACTION_MAP.items():
        if method != pattern_method:
            continue

        # Simple pattern matching with {param} placeholders
        pattern_parts = pattern_path.split("/")
        path_parts = path.split("/")

        if len(pattern_parts) != len(path_parts):
            continue

        params: dict[str, str] = {}
        match = True

        for pattern_part, path_part in zip(pattern_parts, path_parts):
            if pattern_part.startswith("{") and pattern_part.endswith("}"):
                param_name = pattern_part[1:-1]
                params[param_name] = path_part
            elif pattern_part != path_part:
                match = False
                break

        if match:
            return action, params

    return None, {}


class AuditLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware that logs auditable actions to the database."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Any]
    ) -> Response:
        """Process request and log audit entry if applicable."""
        start_time = time.time()

        # Generate request ID
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        # Process request
        response = await call_next(request)

        # Check if this action should be audited
        action, path_params = match_route_pattern(request.method, request.url.path)

        if action and response.status_code < 400:
            # Log successful auditable actions
            try:
                await self._log_audit(
                    request=request,
                    action=action,
                    path_params=path_params,
                    response_status=response.status_code,
                    duration_ms=(time.time() - start_time) * 1000,
                )
            except Exception as e:
                logger.error(f"Failed to log audit entry: {e}")

        return response

    async def _log_audit(
        self,
        request: Request,
        action: AuditAction,
        path_params: dict[str, str],
        response_status: int,
        duration_ms: float,
    ) -> None:
        """Write audit log entry to database."""
        # Get user from request state (set by auth dependency)
        user = getattr(request.state, "user", None)
        actor_id = user.id if user else None

        # Determine entity type and ID from path params
        entity_type = "unknown"
        entity_id = None

        if "id" in path_params:
            try:
                entity_id = uuid.UUID(path_params["id"])
            except ValueError:
                pass

        # Infer entity type from action
        if action.value.startswith("document"):
            entity_type = "document"
        elif action.value.startswith("project"):
            entity_type = "project"
        elif action.value.startswith("span"):
            entity_type = "span"
        elif action.value.startswith("claim"):
            entity_type = "claim"
        elif action.value.startswith("metric"):
            entity_type = "metric"
        elif action.value.startswith("evidence_pack"):
            entity_type = "evidence_pack"
        elif action.value.startswith("search"):
            entity_type = "search"
        elif action.value.startswith("extraction"):
            entity_type = "document_version"
        elif action.value.startswith("embedding"):
            entity_type = "document_version"

        # Build details
        details = {
            "request_id": getattr(request.state, "request_id", None),
            "method": request.method,
            "path": str(request.url.path),
            "query_params": dict(request.query_params),
            "response_status": response_status,
            "duration_ms": round(duration_ms, 2),
        }

        # Get client info
        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")

        # Insert audit log
        session_factory = get_session_factory()
        async with session_factory() as session:
            await session.execute(
                insert(AuditLog).values(
                    action=action,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    actor_id=actor_id,
                    details=details,
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
            )
            await session.commit()


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """Middleware for consistent error response formatting."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Any]
    ) -> Response:
        """Process request and handle exceptions."""
        import os
        import traceback

        try:
            return await call_next(request)
        except Exception as e:
            logger.exception(f"Unhandled exception: {e}")

            # In debug mode or serverless, include more error details for debugging
            is_debug = os.environ.get("DEBUG", "").lower() in ("true", "1")
            is_serverless = os.environ.get("VERCEL") == "1"

            details: dict[str, Any] = {
                "request_id": getattr(request.state, "request_id", None),
            }

            # Include error details in serverless mode to help debug deployment issues
            if is_debug or is_serverless:
                details["error_type"] = type(e).__name__
                details["error_message"] = str(e)
                details["traceback"] = traceback.format_exc().split("\n")[-10:]

            return JSONResponse(
                status_code=500,
                content={
                    "error": "internal_server_error",
                    "message": "An unexpected error occurred",
                    "details": details,
                },
            )


def setup_middleware(app: FastAPI) -> None:
    """Configure middleware for the FastAPI application."""
    # Order matters: error handling should be outermost
    app.add_middleware(ErrorHandlingMiddleware)
    app.add_middleware(AuditLoggingMiddleware)
