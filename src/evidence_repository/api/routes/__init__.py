"""API routes module."""

from fastapi import APIRouter

from evidence_repository.api.routes.admin import router as admin_router
from evidence_repository.api.routes.debug import router as debug_router
from evidence_repository.api.routes.documents import router as documents_router
from evidence_repository.api.routes.evidence import router as evidence_router
from evidence_repository.api.routes.extraction import router as extraction_router
from evidence_repository.api.routes.folders import router as folders_router
from evidence_repository.api.routes.health import router as health_router
from evidence_repository.api.routes.ingest import router as ingest_router
from evidence_repository.api.routes.jobs import router as jobs_router
from evidence_repository.api.routes.projects import router as projects_router
from evidence_repository.api.routes.search import router as search_router
from evidence_repository.api.routes.worker import router as worker_router

# Main API router
router = APIRouter()

# Include all sub-routers
router.include_router(health_router, tags=["Health"])
router.include_router(documents_router, prefix="/documents", tags=["Documents"])
router.include_router(projects_router, prefix="/projects", tags=["Projects"])
router.include_router(folders_router, prefix="/projects", tags=["Folders"])
router.include_router(search_router, prefix="/search", tags=["Search"])
router.include_router(evidence_router, tags=["Evidence"])
router.include_router(extraction_router, tags=["Extraction"])
router.include_router(jobs_router, prefix="/jobs", tags=["Jobs"])
router.include_router(ingest_router, prefix="/ingest", tags=["Bulk Ingestion"])
router.include_router(admin_router, prefix="/admin", tags=["Admin"])
router.include_router(worker_router, prefix="/worker", tags=["Worker"])
router.include_router(debug_router, prefix="/debug", tags=["Debug"])

__all__ = ["router"]
