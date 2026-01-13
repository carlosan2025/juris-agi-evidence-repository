"""Unit tests for JobQueue and job processing."""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from evidence_repository.models.job import Job, JobStatus, JobType


class TestJobModel:
    """Tests for the Job database model."""

    def test_job_status_enum_values(self):
        """Should have expected status values."""
        assert JobStatus.QUEUED.value == "queued"
        assert JobStatus.RUNNING.value == "running"
        assert JobStatus.SUCCEEDED.value == "succeeded"
        assert JobStatus.FAILED.value == "failed"
        assert JobStatus.CANCELED.value == "canceled"
        assert JobStatus.RETRYING.value == "retrying"

    def test_job_type_enum_values(self):
        """Should have expected job type values."""
        assert JobType.DOCUMENT_INGEST.value == "document_ingest"
        assert JobType.DOCUMENT_EXTRACT.value == "document_extract"
        assert JobType.DOCUMENT_EMBED.value == "document_embed"
        assert JobType.DOCUMENT_PROCESS_FULL.value == "document_process_full"
        assert JobType.BULK_FOLDER_INGEST.value == "bulk_folder_ingest"
        assert JobType.BULK_URL_INGEST.value == "bulk_url_ingest"

    def test_job_is_terminal_property(self):
        """Should correctly identify terminal states."""
        job = Job(
            id=uuid.uuid4(),
            type=JobType.DOCUMENT_INGEST,
            status=JobStatus.QUEUED,
            payload={},
        )

        assert job.is_terminal is False

        job.status = JobStatus.RUNNING
        assert job.is_terminal is False

        job.status = JobStatus.SUCCEEDED
        assert job.is_terminal is True

        job.status = JobStatus.FAILED
        assert job.is_terminal is True

        job.status = JobStatus.CANCELED
        assert job.is_terminal is True

    def test_job_can_retry_property(self):
        """Should correctly identify retryable jobs."""
        job = Job(
            id=uuid.uuid4(),
            type=JobType.DOCUMENT_INGEST,
            status=JobStatus.FAILED,
            payload={},
            attempts=1,
            max_attempts=3,
        )

        assert job.can_retry is True

        job.attempts = 3
        assert job.can_retry is False

        job.status = JobStatus.SUCCEEDED
        job.attempts = 1
        assert job.can_retry is False

    def test_job_duration_calculation(self):
        """Should calculate job duration correctly."""
        job = Job(
            id=uuid.uuid4(),
            type=JobType.DOCUMENT_INGEST,
            status=JobStatus.SUCCEEDED,
            payload={},
        )

        # No timestamps - should return None
        assert job.duration_seconds is None

        # With timestamps
        job.started_at = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        job.finished_at = datetime(2025, 1, 1, 12, 0, 30, tzinfo=timezone.utc)
        assert job.duration_seconds == 30.0


class TestJobQueueMocked:
    """Tests for JobQueue with mocked database."""

    @pytest.fixture
    def mock_db_session(self):
        """Create a mock database session."""
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        return mock_session

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis connection."""
        return MagicMock()

    def test_enqueue_creates_job_record(self, mock_db_session, mock_redis):
        """Should create a job record in the database."""
        from evidence_repository.queue.job_queue import JobQueue

        # Create mock session factory
        mock_session_factory = MagicMock(return_value=mock_db_session)

        # Mock the queue
        with patch("evidence_repository.queue.job_queue.get_queue") as mock_get_queue:
            mock_queue = MagicMock()
            mock_queue.enqueue.return_value = MagicMock(id="rq-job-123")
            mock_get_queue.return_value = mock_queue

            job_queue = JobQueue(redis=mock_redis, db_session_factory=mock_session_factory)

            # Enqueue a job
            job_id = job_queue.enqueue(
                job_type=JobType.DOCUMENT_INGEST,
                payload={"filename": "test.pdf"},
                priority=0,
            )

            # Verify job record was created
            assert job_id is not None
            mock_db_session.add.assert_called_once()
            mock_db_session.commit.assert_called()

    def test_enqueue_selects_queue_by_priority(self, mock_db_session, mock_redis):
        """Should select appropriate queue based on priority."""
        from evidence_repository.queue.job_queue import JobQueue

        mock_session_factory = MagicMock(return_value=mock_db_session)

        with patch("evidence_repository.queue.job_queue.get_high_priority_queue") as mock_high:
            with patch("evidence_repository.queue.job_queue.get_low_priority_queue") as mock_low:
                with patch("evidence_repository.queue.job_queue.get_queue") as mock_normal:
                    # Setup mock queues
                    for mock_q in [mock_high, mock_low, mock_normal]:
                        queue = MagicMock()
                        queue.enqueue.return_value = MagicMock(id="rq-job-123")
                        mock_q.return_value = queue

                    job_queue = JobQueue(redis=mock_redis, db_session_factory=mock_session_factory)

                    # High priority (>= 10)
                    job_queue.enqueue(JobType.DOCUMENT_INGEST, {}, priority=15)
                    mock_high.assert_called()

                    # Low priority (< 0)
                    job_queue.enqueue(JobType.DOCUMENT_INGEST, {}, priority=-5)
                    mock_low.assert_called()

                    # Normal priority
                    job_queue.enqueue(JobType.DOCUMENT_INGEST, {}, priority=5)
                    mock_normal.assert_called()


class TestJobEnqueueRequest:
    """Tests for JobEnqueueRequest schema."""

    def test_valid_enqueue_request(self):
        """Should accept valid enqueue request."""
        from evidence_repository.schemas.job import JobEnqueueRequest

        request = JobEnqueueRequest(
            type="document_ingest",
            payload={"filename": "test.pdf", "content_type": "application/pdf"},
            priority=0,
        )

        assert request.type == "document_ingest"
        assert request.payload["filename"] == "test.pdf"
        assert request.priority == 0

    def test_priority_bounds(self):
        """Should enforce priority bounds."""
        from evidence_repository.schemas.job import JobEnqueueRequest
        from pydantic import ValidationError

        # Valid bounds
        JobEnqueueRequest(type="document_ingest", payload={}, priority=-100)
        JobEnqueueRequest(type="document_ingest", payload={}, priority=100)

        # Out of bounds
        with pytest.raises(ValidationError):
            JobEnqueueRequest(type="document_ingest", payload={}, priority=-101)

        with pytest.raises(ValidationError):
            JobEnqueueRequest(type="document_ingest", payload={}, priority=101)

    def test_default_priority(self):
        """Should default to priority 0."""
        from evidence_repository.schemas.job import JobEnqueueRequest

        request = JobEnqueueRequest(type="document_ingest", payload={})
        assert request.priority == 0


class TestJobResponse:
    """Tests for JobResponse schema."""

    def test_job_response_creation(self):
        """Should create valid job response."""
        from evidence_repository.schemas.job import JobResponse

        response = JobResponse(
            job_id="123e4567-e89b-12d3-a456-426614174000",
            job_type="document_ingest",
            status="running",
            created_at="2025-01-13T12:00:00",
            started_at="2025-01-13T12:00:01",
            ended_at=None,
            result=None,
            error=None,
            progress=50.0,
            progress_message="Processing document",
            metadata={"filename": "test.pdf"},
        )

        assert response.job_id == "123e4567-e89b-12d3-a456-426614174000"
        assert response.status == "running"
        assert response.progress == 50.0

    def test_job_response_with_error(self):
        """Should handle error responses."""
        from evidence_repository.schemas.job import JobResponse

        response = JobResponse(
            job_id="123e4567-e89b-12d3-a456-426614174000",
            job_type="document_ingest",
            status="failed",
            error="Document processing failed: invalid format",
            progress=30.0,
        )

        assert response.status == "failed"
        assert "invalid format" in response.error


class TestWorkerConfiguration:
    """Tests for worker configuration."""

    def test_worker_queues_order(self):
        """Workers should process queues in priority order."""
        from evidence_repository.queue.connection import (
            get_high_priority_queue,
            get_low_priority_queue,
            get_queue,
        )

        # Verify queue names follow priority pattern
        with patch("evidence_repository.queue.connection.get_redis_connection"):
            with patch("evidence_repository.queue.connection.get_settings") as mock_settings:
                mock_settings.return_value.redis_queue_name = "evidence_jobs"
                mock_settings.return_value.redis_job_timeout = 3600

                high_q = get_high_priority_queue()
                normal_q = get_queue()
                low_q = get_low_priority_queue()

                assert "high" in high_q.name
                assert "low" in low_q.name


class TestIdempotency:
    """Tests for job idempotency."""

    def test_duplicate_job_detection(self):
        """Jobs with same document hash should be detected as duplicates."""
        # This tests the document ingestion idempotency
        # The actual implementation is in tasks.py which checks file_hash
        from evidence_repository.queue.tasks import _compute_file_hash

        data1 = b"Same content"
        data2 = b"Same content"
        data3 = b"Different content"

        hash1 = _compute_file_hash(data1)
        hash2 = _compute_file_hash(data2)
        hash3 = _compute_file_hash(data3)

        assert hash1 == hash2  # Same content = same hash
        assert hash1 != hash3  # Different content = different hash


class TestProgressTracking:
    """Tests for job progress tracking."""

    def test_progress_update_bounds(self):
        """Progress should be bounded to 0-100."""
        from evidence_repository.queue.jobs import JobManager

        with patch("evidence_repository.queue.jobs.get_redis_connection") as mock_redis:
            with patch("evidence_repository.queue.jobs.get_queue"):
                mock_redis_conn = MagicMock()
                mock_redis.return_value = mock_redis_conn

                manager = JobManager(redis=mock_redis_conn)

                # Update progress with out-of-bounds values
                manager.update_progress("job-123", -10.0, "Test")
                manager.update_progress("job-123", 150.0, "Test")

                # Check that hset was called with bounded values
                calls = mock_redis_conn.hset.call_args_list
                for call in calls:
                    progress_val = float(call[1]["mapping"]["progress"])
                    assert 0.0 <= progress_val <= 100.0


class TestMIMETypeMapping:
    """Tests for MIME type detection."""

    def test_mime_type_mapping(self):
        """Should correctly map file extensions to MIME types."""
        from evidence_repository.queue.tasks import MIME_TYPE_MAP

        assert MIME_TYPE_MAP[".pdf"] == "application/pdf"
        assert MIME_TYPE_MAP[".txt"] == "text/plain"
        assert MIME_TYPE_MAP[".xlsx"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        assert MIME_TYPE_MAP[".png"] == "image/png"
        assert MIME_TYPE_MAP[".jpg"] == "image/jpeg"
        assert MIME_TYPE_MAP[".jpeg"] == "image/jpeg"
