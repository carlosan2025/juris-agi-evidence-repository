"""RQ Worker entry point for background job processing.

This module provides the entry point for running RQ workers that process
jobs from the Evidence Repository queue.

Usage:
    python -m evidence_repository.worker
    python -m evidence_repository.worker --queues evidence_jobs_high evidence_jobs
    python -m evidence_repository.worker --burst  # Exit when queues empty

Multiple workers can run in parallel for horizontal scaling.
Workers listen to all priority queues by default: high, normal, low.
"""

import logging
import signal
import socket
import sys
from datetime import datetime

from redis import Redis
from rq import Worker
from rq.job import Job

from evidence_repository.config import get_settings
from evidence_repository.queue.connection import (
    get_high_priority_queue,
    get_low_priority_queue,
    get_queue,
    get_redis_connection,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


class EvidenceWorker(Worker):
    """Custom RQ worker with enhanced logging and monitoring."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.hostname = socket.gethostname()
        self._job_start_times: dict[str, datetime] = {}

    def perform_job(self, job: Job, queue) -> bool:
        """Perform job with timing and logging."""
        self._job_start_times[job.id] = datetime.utcnow()
        logger.info(
            f"[{self.hostname}] Starting job {job.id} "
            f"from queue '{queue.name}' func={job.func_name}"
        )
        return super().perform_job(job, queue)

    def handle_job_success(self, job: Job, queue, started_job_registry):
        """Handle successful job completion."""
        start_time = self._job_start_times.pop(job.id, None)
        duration = (datetime.utcnow() - start_time).total_seconds() if start_time else 0
        logger.info(f"[{self.hostname}] Job {job.id} completed successfully in {duration:.2f}s")
        return super().handle_job_success(job, queue, started_job_registry)

    def handle_job_failure(self, job: Job, queue, started_job_registry, exc_string=""):
        """Handle job failure."""
        start_time = self._job_start_times.pop(job.id, None)
        duration = (datetime.utcnow() - start_time).total_seconds() if start_time else 0
        logger.error(
            f"[{self.hostname}] Job {job.id} FAILED after {duration:.2f}s: {exc_string[:200]}"
        )
        return super().handle_job_failure(job, queue, started_job_registry, exc_string)


def run_worker(
    queues: list[str] | None = None,
    burst: bool = False,
    name: str | None = None,
) -> None:
    """Start an RQ worker.

    Workers process jobs in priority order: high -> normal -> low.
    Multiple workers can run in parallel safely - RQ handles job locking.

    Args:
        queues: List of queue names to process (defaults to all).
        burst: Run in burst mode (exit when queues are empty).
        name: Optional worker name.
    """
    settings = get_settings()
    redis_conn = get_redis_connection()
    hostname = socket.gethostname()

    # Default to all queues in priority order
    if queues is None:
        queue_objects = [
            get_high_priority_queue(),
            get_queue(),
            get_low_priority_queue(),
        ]
    else:
        from rq import Queue
        queue_objects = [Queue(name=q, connection=redis_conn) for q in queues]

    # Generate worker name if not provided
    if name is None:
        name = f"evidence-worker-{hostname}-{datetime.utcnow().strftime('%H%M%S')}"

    logger.info("=" * 60)
    logger.info("Evidence Repository Worker")
    logger.info("=" * 60)
    logger.info(f"Worker name: {name}")
    logger.info(f"Hostname: {hostname}")
    logger.info(f"Queues: {[q.name for q in queue_objects]}")
    logger.info(f"Redis URL: {settings.redis_url}")
    logger.info(f"Job timeout: {settings.redis_job_timeout}s")
    logger.info(f"Result TTL: {settings.redis_result_ttl}s")
    logger.info(f"Burst mode: {burst}")
    logger.info("=" * 60)

    # Create custom worker with enhanced logging
    worker = EvidenceWorker(
        queues=queue_objects,
        name=name,
        connection=redis_conn,
    )

    # Setup graceful shutdown
    def handle_shutdown(signum, frame):
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        worker.request_stop(signum, frame)

    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    logger.info("Worker ready, waiting for jobs...")

    try:
        worker.work(
            burst=burst,
            logging_level=settings.log_level,
        )
    except KeyboardInterrupt:
        logger.info("Worker interrupted by user")
    finally:
        logger.info("Worker shutdown complete")


def main() -> None:
    """CLI entry point for worker."""
    import argparse

    parser = argparse.ArgumentParser(description="Evidence Repository Worker")
    parser.add_argument(
        "--queues",
        "-q",
        nargs="+",
        help="Queue names to process (default: all)",
    )
    parser.add_argument(
        "--burst",
        "-b",
        action="store_true",
        help="Run in burst mode (exit when empty)",
    )
    parser.add_argument(
        "--name",
        "-n",
        help="Worker name",
    )

    args = parser.parse_args()

    run_worker(
        queues=args.queues,
        burst=args.burst,
        name=args.name,
    )


if __name__ == "__main__":
    main()
