"""Document digestion pipeline module.

This module provides a unified pipeline for processing documents from
upload through to searchable state.

Key features:
- Database-as-queue pattern for simple deployments
- Shared pipeline logic for all processing modes
- Content hash deduplication
- Two-stage search architecture
- Truthfulness assessment
"""

from evidence_repository.digestion.pipeline import (
    DigestResult,
    DigestionPipeline,
    DigestOptions,
    digest_document,
    digest_pending_documents,
)
from evidence_repository.digestion.polling_worker import (
    PollingWorker,
    run_polling_worker,
)
from evidence_repository.digestion.status import (
    ProcessingStatus,
    get_processing_stats,
    get_queue_status,
)

__all__ = [
    "DigestResult",
    "DigestionPipeline",
    "DigestOptions",
    "digest_document",
    "digest_pending_documents",
    "PollingWorker",
    "run_polling_worker",
    "ProcessingStatus",
    "get_processing_stats",
    "get_queue_status",
]
