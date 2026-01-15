"""Database polling worker for document processing.

This module provides a simple database-as-queue worker for processing
documents without external queue dependencies.

Key features:
- Polls database for PENDING documents
- Processes documents using shared DigestionPipeline
- Self-triggering for batch processing
- Graceful shutdown handling
- Status monitoring endpoint support
"""

import asyncio
import logging
import signal
import socket
import sys
from datetime import datetime
from typing import Callable

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from evidence_repository.config import get_settings
from evidence_repository.models.document import Document, DocumentVersion, ExtractionStatus
from evidence_repository.digestion.pipeline import DigestionPipeline, DigestResult

logger = logging.getLogger(__name__)


class PollingWorker:
    """Database polling worker for document processing.

    This worker polls the database for documents with PENDING status
    and processes them through the digestion pipeline.

    Usage:
        worker = PollingWorker()
        await worker.run()

    Or use the convenience function:
        await run_polling_worker()
    """

    def __init__(
        self,
        poll_interval: float = 5.0,
        batch_size: int = 5,
        max_iterations: int | None = None,
    ):
        """Initialize polling worker.

        Args:
            poll_interval: Seconds between database polls.
            batch_size: Maximum documents to process per batch.
            max_iterations: Maximum poll iterations (None for infinite).
        """
        self.poll_interval = poll_interval
        self.batch_size = batch_size
        self.max_iterations = max_iterations
        self._settings = get_settings()
        self._shutdown_requested = False
        self._current_job: str | None = None
        self._hostname = socket.gethostname()
        self._stats = {
            "started_at": None,
            "documents_processed": 0,
            "documents_failed": 0,
            "iterations": 0,
            "last_poll_at": None,
        }

        # Database setup
        self._engine = None
        self._session_maker = None

    async def _get_session(self) -> AsyncSession:
        """Get async database session."""
        if self._engine is None:
            self._engine = create_async_engine(
                self._settings.database_url,
                pool_size=5,
                max_overflow=10,
            )
            self._session_maker = sessionmaker(
                self._engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )
        return self._session_maker()

    def request_shutdown(self) -> None:
        """Request graceful shutdown."""
        logger.info(f"[{self._hostname}] Shutdown requested")
        self._shutdown_requested = True

    async def run(self) -> dict:
        """Run the polling worker loop.

        Returns:
            Stats dictionary when worker exits.
        """
        self._stats["started_at"] = datetime.utcnow()
        logger.info("=" * 60)
        logger.info("Evidence Repository Polling Worker")
        logger.info("=" * 60)
        logger.info(f"Hostname: {self._hostname}")
        logger.info(f"Poll interval: {self.poll_interval}s")
        logger.info(f"Batch size: {self.batch_size}")
        logger.info(f"Max iterations: {self.max_iterations or 'unlimited'}")
        logger.info("=" * 60)

        iteration = 0

        while not self._shutdown_requested:
            iteration += 1
            self._stats["iterations"] = iteration
            self._stats["last_poll_at"] = datetime.utcnow()

            if self.max_iterations and iteration > self.max_iterations:
                logger.info(f"Max iterations ({self.max_iterations}) reached")
                break

            try:
                # Poll and process pending documents
                processed = await self._poll_and_process()

                if processed > 0:
                    logger.info(
                        f"[{self._hostname}] Iteration {iteration}: "
                        f"processed {processed} documents"
                    )
                    # Continue immediately if we processed something
                    continue

            except Exception as e:
                logger.error(f"[{self._hostname}] Poll iteration failed: {e}")
                self._stats["documents_failed"] += 1

            # Wait before next poll
            await asyncio.sleep(self.poll_interval)

        logger.info(f"[{self._hostname}] Worker shutting down")
        logger.info(f"Stats: {self._stats}")

        return self._stats

    async def _poll_and_process(self) -> int:
        """Poll for pending documents and process them.

        Returns:
            Number of documents processed.
        """
        async with await self._get_session() as session:
            # Find pending documents
            pending = await session.execute(
                select(DocumentVersion)
                .where(DocumentVersion.extraction_status == ExtractionStatus.PENDING)
                .order_by(DocumentVersion.created_at)
                .limit(self.batch_size)
            )
            versions = pending.scalars().all()

            if not versions:
                return 0

            logger.info(f"[{self._hostname}] Found {len(versions)} pending documents")

            processed = 0
            for version in versions:
                if self._shutdown_requested:
                    break

                try:
                    await self._process_version(session, version)
                    processed += 1
                    self._stats["documents_processed"] += 1
                except Exception as e:
                    logger.error(f"Failed to process version {version.id}: {e}")
                    self._stats["documents_failed"] += 1

            return processed

    async def _process_version(
        self,
        session: AsyncSession,
        version: DocumentVersion,
    ) -> DigestResult:
        """Process a single document version.

        Args:
            session: Database session.
            version: DocumentVersion to process.

        Returns:
            DigestResult from processing.
        """
        logger.info(f"[{self._hostname}] Processing version {version.id}")
        self._current_job = str(version.id)

        try:
            # Mark as processing (prevents duplicate processing)
            await session.execute(
                update(DocumentVersion)
                .where(DocumentVersion.id == version.id)
                .values(extraction_status=ExtractionStatus.PROCESSING)
            )
            await session.commit()

            # Get document
            doc_result = await session.execute(
                select(Document).where(Document.id == version.document_id)
            )
            document = doc_result.scalar_one()

            # Initialize pipeline
            pipeline = DigestionPipeline(db=session)

            # Download file
            file_data = await pipeline.storage.download(version.storage_path)

            # Run pipeline steps
            result = DigestResult(
                document_id=document.id,
                version_id=version.id,
                started_at=datetime.utcnow(),
            )

            # Parse
            await pipeline._step_parse(document, version, file_data, result)

            # Build sections
            await pipeline._step_build_sections(version, result)

            # Generate embeddings
            await pipeline._step_generate_embeddings(version, result)

            # Mark complete
            version.extraction_status = ExtractionStatus.COMPLETED
            await session.commit()

            result.status = "ready"
            result.completed_at = datetime.utcnow()

            logger.info(
                f"[{self._hostname}] Completed version {version.id} - "
                f"text: {result.text_length} chars, "
                f"sections: {result.section_count}, "
                f"embeddings: {result.embedding_count}"
            )

            return result

        except Exception as e:
            # Mark as failed
            await session.execute(
                update(DocumentVersion)
                .where(DocumentVersion.id == version.id)
                .values(
                    extraction_status=ExtractionStatus.FAILED,
                    extraction_error=str(e),
                )
            )
            await session.commit()

            logger.error(f"[{self._hostname}] Version {version.id} failed: {e}")
            raise

        finally:
            self._current_job = None

    @property
    def stats(self) -> dict:
        """Get current worker statistics."""
        return {
            **self._stats,
            "hostname": self._hostname,
            "current_job": self._current_job,
            "shutdown_requested": self._shutdown_requested,
        }


async def run_polling_worker(
    poll_interval: float = 5.0,
    batch_size: int = 5,
    max_iterations: int | None = None,
) -> dict:
    """Convenience function to run polling worker.

    Args:
        poll_interval: Seconds between database polls.
        batch_size: Documents per batch.
        max_iterations: Max iterations (None for infinite).

    Returns:
        Worker stats when complete.
    """
    worker = PollingWorker(
        poll_interval=poll_interval,
        batch_size=batch_size,
        max_iterations=max_iterations,
    )

    # Setup signal handlers
    def handle_shutdown(signum, frame):
        worker.request_shutdown()

    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    return await worker.run()


# =============================================================================
# CLI Entry Point
# =============================================================================


def main():
    """CLI entry point for polling worker."""
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    parser = argparse.ArgumentParser(description="Evidence Repository Polling Worker")
    parser.add_argument(
        "--interval",
        "-i",
        type=float,
        default=5.0,
        help="Poll interval in seconds (default: 5)",
    )
    parser.add_argument(
        "--batch-size",
        "-b",
        type=int,
        default=5,
        help="Documents per batch (default: 5)",
    )
    parser.add_argument(
        "--max-iterations",
        "-n",
        type=int,
        help="Maximum iterations (default: unlimited)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process one batch and exit",
    )

    args = parser.parse_args()

    max_iterations = 1 if args.once else args.max_iterations

    try:
        stats = asyncio.run(
            run_polling_worker(
                poll_interval=args.interval,
                batch_size=args.batch_size,
                max_iterations=max_iterations,
            )
        )
        print(f"\nWorker finished. Stats: {stats}")
    except KeyboardInterrupt:
        print("\nWorker interrupted")


if __name__ == "__main__":
    main()
