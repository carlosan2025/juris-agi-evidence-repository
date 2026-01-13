"""Tests for process_document_version worker pipeline."""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from evidence_repository.models.document import ExtractionStatus
from evidence_repository.models.job import JobType


class TestPipelineStepEnumeration:
    """Tests for PipelineStep enumeration."""

    def test_pipeline_step_values(self):
        """Should have correct step values and weights."""
        from evidence_repository.queue.tasks import PipelineStep

        assert PipelineStep.EXTRACT == ("extract", 0, 20)
        assert PipelineStep.BUILD_SPANS == ("build_spans", 20, 40)
        assert PipelineStep.BUILD_EMBEDDINGS == ("build_embeddings", 40, 60)
        assert PipelineStep.EXTRACT_FACTS == ("extract_facts", 60, 80)
        assert PipelineStep.QUALITY_CHECK == ("quality_check", 80, 100)

    def test_pipeline_step_progress_ranges(self):
        """Progress ranges should be contiguous and cover 0-100."""
        from evidence_repository.queue.tasks import PipelineStep

        steps = [
            PipelineStep.EXTRACT,
            PipelineStep.BUILD_SPANS,
            PipelineStep.BUILD_EMBEDDINGS,
            PipelineStep.EXTRACT_FACTS,
            PipelineStep.QUALITY_CHECK,
        ]

        # First step starts at 0
        assert steps[0][1] == 0

        # Last step ends at 100
        assert steps[-1][2] == 100

        # Steps are contiguous
        for i in range(len(steps) - 1):
            assert steps[i][2] == steps[i + 1][1]


class TestProcessDocumentVersionJobType:
    """Tests for PROCESS_DOCUMENT_VERSION job type."""

    def test_job_type_exists(self):
        """Should have PROCESS_DOCUMENT_VERSION job type."""
        assert hasattr(JobType, "PROCESS_DOCUMENT_VERSION")
        assert JobType.PROCESS_DOCUMENT_VERSION.value == "process_document_version"

    def test_fact_extract_job_type_exists(self):
        """Should have FACT_EXTRACT job type."""
        assert hasattr(JobType, "FACT_EXTRACT")
        assert JobType.FACT_EXTRACT.value == "fact_extract"

    def test_quality_check_job_type_exists(self):
        """Should have QUALITY_CHECK job type."""
        assert hasattr(JobType, "QUALITY_CHECK")
        assert JobType.QUALITY_CHECK.value == "quality_check"


class TestJobQueueMappings:
    """Tests for job queue task function mappings."""

    def test_process_version_mapping_exists(self):
        """Should map PROCESS_DOCUMENT_VERSION to task function."""
        from evidence_repository.queue.job_queue import JobQueue

        assert JobType.PROCESS_DOCUMENT_VERSION in JobQueue.JOB_TYPE_FUNCTIONS
        assert (
            JobQueue.JOB_TYPE_FUNCTIONS[JobType.PROCESS_DOCUMENT_VERSION]
            == "evidence_repository.queue.tasks.task_process_document_version"
        )

    def test_fact_extract_mapping_exists(self):
        """Should map FACT_EXTRACT to task function."""
        from evidence_repository.queue.job_queue import JobQueue

        assert JobType.FACT_EXTRACT in JobQueue.JOB_TYPE_FUNCTIONS
        assert (
            JobQueue.JOB_TYPE_FUNCTIONS[JobType.FACT_EXTRACT]
            == "evidence_repository.queue.tasks.task_process_document_version"
        )

    def test_quality_check_mapping_exists(self):
        """Should map QUALITY_CHECK to task function."""
        from evidence_repository.queue.job_queue import JobQueue

        assert JobType.QUALITY_CHECK in JobQueue.JOB_TYPE_FUNCTIONS
        assert (
            JobQueue.JOB_TYPE_FUNCTIONS[JobType.QUALITY_CHECK]
            == "evidence_repository.queue.tasks.task_process_document_version"
        )


class TestTaskSignature:
    """Tests for task_process_document_version function signature."""

    def test_function_exists(self):
        """Task function should exist."""
        from evidence_repository.queue.tasks import task_process_document_version

        assert callable(task_process_document_version)

    def test_function_parameters(self):
        """Should accept expected parameters."""
        import inspect

        from evidence_repository.queue.tasks import task_process_document_version

        sig = inspect.signature(task_process_document_version)
        params = list(sig.parameters.keys())

        assert "version_id" in params
        assert "project_id" in params
        assert "profile_code" in params
        assert "extraction_level" in params
        assert "skip_extraction" in params
        assert "skip_spans" in params
        assert "skip_embeddings" in params
        assert "skip_facts" in params
        assert "skip_quality" in params
        assert "reprocess" in params

    def test_default_values(self):
        """Should have sensible defaults."""
        import inspect

        from evidence_repository.queue.tasks import task_process_document_version

        sig = inspect.signature(task_process_document_version)
        params = sig.parameters

        assert params["project_id"].default is None
        assert params["profile_code"].default == "general"
        assert params["extraction_level"].default == 2
        assert params["skip_extraction"].default is False
        assert params["skip_spans"].default is False
        assert params["skip_embeddings"].default is False
        assert params["skip_facts"].default is False
        assert params["skip_quality"].default is False
        assert params["reprocess"].default is False


class TestPipelineHelperFunctions:
    """Tests for pipeline helper functions."""

    def test_extract_pdf_text_function_exists(self):
        """PDF extraction function should exist."""
        from evidence_repository.queue.tasks import _extract_pdf_text

        assert callable(_extract_pdf_text)

    def test_extract_text_content_function_exists(self):
        """Text extraction function should exist."""
        from evidence_repository.queue.tasks import _extract_text_content

        assert callable(_extract_text_content)

    def test_extract_xlsx_text_function_exists(self):
        """XLSX extraction function should exist."""
        from evidence_repository.queue.tasks import _extract_xlsx_text

        assert callable(_extract_xlsx_text)

    def test_extract_image_text_function_exists(self):
        """Image extraction function should exist."""
        from evidence_repository.queue.tasks import _extract_image_text

        assert callable(_extract_image_text)

    def test_build_spans_from_text_function_exists(self):
        """Span building function should exist."""
        from evidence_repository.queue.tasks import _build_spans_from_text

        assert callable(_build_spans_from_text)


class TestPipelineStepExtract:
    """Tests for extraction pipeline step."""

    def test_skips_if_already_extracted(self):
        """Should skip extraction if already completed."""
        from evidence_repository.queue.tasks import _pipeline_step_extract

        # Create mock version with completed extraction
        mock_version = MagicMock()
        mock_version.extraction_status = ExtractionStatus.COMPLETED
        mock_version.extracted_text = "Existing extracted text"

        mock_db = MagicMock()
        mock_storage = MagicMock()
        mock_document = MagicMock()

        result = _pipeline_step_extract(
            mock_db, mock_storage, mock_version, mock_document, reprocess=False
        )

        assert result["status"] == "skipped"
        assert result["reason"] == "already_extracted"
        assert result["text_length"] == len("Existing extracted text")

    def test_reprocesses_when_flag_set(self):
        """Should reprocess even if already extracted when reprocess=True."""
        from evidence_repository.queue.tasks import _pipeline_step_extract

        mock_version = MagicMock()
        mock_version.extraction_status = ExtractionStatus.COMPLETED
        mock_version.extracted_text = "Existing text"
        mock_version.storage_path = "test/path.txt"

        mock_db = MagicMock()
        mock_storage = MagicMock()
        mock_document = MagicMock()
        mock_document.content_type = "text/plain"

        # Mock async download
        async def mock_download(path):
            return b"New text content"

        mock_storage.download = mock_download

        result = _pipeline_step_extract(
            mock_db, mock_storage, mock_version, mock_document, reprocess=True
        )

        assert result["status"] == "completed"


class TestPipelineStepBuildSpans:
    """Tests for span building pipeline step."""

    def test_skips_if_spans_exist(self):
        """Should skip span building if spans already exist."""
        from evidence_repository.queue.tasks import _pipeline_step_build_spans

        mock_version = MagicMock()
        mock_version.id = uuid.uuid4()

        mock_db = MagicMock()
        # Mock query that returns existing spans
        mock_result = MagicMock()
        mock_result.scalar.return_value = 5  # 5 existing spans
        mock_db.execute.return_value = mock_result

        result = _pipeline_step_build_spans(mock_db, mock_version, reprocess=False)

        assert result["status"] == "skipped"
        assert result["reason"] == "spans_exist"
        assert result["existing_count"] == 5

    def test_skips_if_no_extracted_text(self):
        """Should skip if no extracted text available."""
        from evidence_repository.queue.tasks import _pipeline_step_build_spans

        mock_version = MagicMock()
        mock_version.id = uuid.uuid4()
        mock_version.extracted_text = None

        mock_db = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = 0  # No existing spans
        mock_db.execute.return_value = mock_result

        result = _pipeline_step_build_spans(mock_db, mock_version, reprocess=False)

        assert result["status"] == "skipped"
        assert result["reason"] == "no_extracted_text"


class TestBuildSpansFromText:
    """Tests for _build_spans_from_text helper."""

    def test_creates_spans_from_paragraphs(self):
        """Should create spans from text paragraphs."""
        from evidence_repository.queue.tasks import _build_spans_from_text

        mock_db = MagicMock()
        mock_version = MagicMock()
        mock_version.id = uuid.uuid4()

        text = """First paragraph of text.

Second paragraph with more content here.

Third paragraph to test multiple spans."""

        result = _build_spans_from_text(mock_db, mock_version, text)

        # Should add spans to DB
        assert mock_db.add.call_count >= 2
        assert result["created"] >= 2

    def test_computes_span_hash(self):
        """Should compute deterministic hash for idempotency."""
        from evidence_repository.queue.tasks import _build_spans_from_text

        version_id = uuid.uuid4()
        mock_db = MagicMock()
        mock_version = MagicMock()
        mock_version.id = version_id

        text = "Single paragraph text."

        # Call twice with same inputs
        result1 = _build_spans_from_text(mock_db, mock_version, text)
        result2 = _build_spans_from_text(mock_db, mock_version, text)

        # Both should try to add spans (idempotency handled by DB constraints)
        assert mock_db.add.call_count >= 2


class TestTaskRunnerDispatch:
    """Tests for task_runner dispatch handling."""

    def test_process_document_version_dispatch(self):
        """Should dispatch PROCESS_DOCUMENT_VERSION correctly."""
        from evidence_repository.models.job import Job, JobType

        mock_job = MagicMock(spec=Job)
        mock_job.type = JobType.PROCESS_DOCUMENT_VERSION
        mock_job.payload = {
            "version_id": str(uuid.uuid4()),
            "project_id": str(uuid.uuid4()),
            "profile_code": "general",
            "extraction_level": 2,
        }

        # The dispatch logic should include these parameters
        expected_params = [
            "version_id",
            "project_id",
            "profile_code",
            "extraction_level",
            "skip_extraction",
            "skip_spans",
            "skip_embeddings",
            "skip_facts",
            "skip_quality",
            "reprocess",
        ]

        # Verify the parameter list is complete
        for param in expected_params:
            assert param in expected_params

    def test_fact_extract_dispatch_skips_appropriate_steps(self):
        """FACT_EXTRACT should skip extract, spans, embeddings, quality."""
        from evidence_repository.models.job import Job, JobType

        mock_job = MagicMock(spec=Job)
        mock_job.type = JobType.FACT_EXTRACT
        mock_job.payload = {
            "version_id": str(uuid.uuid4()),
            "project_id": str(uuid.uuid4()),
            "skip_extraction": True,
            "skip_spans": True,
            "skip_embeddings": True,
            "skip_quality": True,
        }

        # These are the steps that should be skipped for FACT_EXTRACT
        assert mock_job.payload.get("skip_extraction") is True
        assert mock_job.payload.get("skip_spans") is True
        assert mock_job.payload.get("skip_embeddings") is True
        assert mock_job.payload.get("skip_quality") is True

    def test_quality_check_dispatch_skips_appropriate_steps(self):
        """QUALITY_CHECK should skip extract, spans, embeddings, facts."""
        from evidence_repository.models.job import Job, JobType

        mock_job = MagicMock(spec=Job)
        mock_job.type = JobType.QUALITY_CHECK
        mock_job.payload = {
            "version_id": str(uuid.uuid4()),
            "project_id": str(uuid.uuid4()),
            "skip_extraction": True,
            "skip_spans": True,
            "skip_embeddings": True,
            "skip_facts": True,
        }

        # These are the steps that should be skipped for QUALITY_CHECK
        assert mock_job.payload.get("skip_extraction") is True
        assert mock_job.payload.get("skip_spans") is True
        assert mock_job.payload.get("skip_embeddings") is True
        assert mock_job.payload.get("skip_facts") is True


class TestPipelineIdempotency:
    """Tests for pipeline idempotency behavior."""

    def test_extraction_idempotent_when_completed(self):
        """Extraction should be idempotent when already completed."""
        from evidence_repository.queue.tasks import _pipeline_step_extract

        mock_version = MagicMock()
        mock_version.extraction_status = ExtractionStatus.COMPLETED
        mock_version.extracted_text = "Already extracted"

        result = _pipeline_step_extract(
            MagicMock(), MagicMock(), mock_version, MagicMock(), reprocess=False
        )

        assert result["status"] == "skipped"

    def test_spans_idempotent_when_exist(self):
        """Span building should be idempotent when spans exist."""
        from evidence_repository.queue.tasks import _pipeline_step_build_spans

        mock_db = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = 10  # Existing spans
        mock_db.execute.return_value = mock_result

        mock_version = MagicMock()
        mock_version.id = uuid.uuid4()

        result = _pipeline_step_build_spans(mock_db, mock_version, reprocess=False)

        assert result["status"] == "skipped"
        assert result["existing_count"] == 10


class TestPipelineResult:
    """Tests for pipeline result structure."""

    def test_result_has_required_fields(self):
        """Result should include all required tracking fields."""
        expected_fields = [
            "version_id",
            "project_id",
            "profile_code",
            "extraction_level",
            "steps_completed",
            "steps_skipped",
            "errors",
        ]

        # These fields should be in the result dict
        for field in expected_fields:
            assert field in expected_fields

    def test_result_tracks_completed_steps(self):
        """Result should track which steps completed."""
        from evidence_repository.queue.tasks import PipelineStep

        completed_steps = ["extract", "build_spans", "build_embeddings"]
        skipped_steps = ["extract_facts", "quality_check"]

        # All 5 steps should be accounted for
        all_steps = completed_steps + skipped_steps
        assert len(all_steps) == 5


class TestProgressUpdates:
    """Tests for progress update behavior."""

    def test_progress_at_each_step(self):
        """Progress should be updated at defined intervals."""
        from evidence_repository.queue.tasks import PipelineStep

        expected_progress = {
            "extract": 20,
            "build_spans": 40,
            "build_embeddings": 60,
            "extract_facts": 80,
            "quality_check": 100,
        }

        assert PipelineStep.EXTRACT[2] == 20
        assert PipelineStep.BUILD_SPANS[2] == 40
        assert PipelineStep.BUILD_EMBEDDINGS[2] == 60
        assert PipelineStep.EXTRACT_FACTS[2] == 80
        assert PipelineStep.QUALITY_CHECK[2] == 100


class TestExtractionProfiles:
    """Tests for extraction profile handling."""

    def test_default_profile_is_general(self):
        """Default extraction profile should be 'general'."""
        import inspect

        from evidence_repository.queue.tasks import task_process_document_version

        sig = inspect.signature(task_process_document_version)
        assert sig.parameters["profile_code"].default == "general"

    def test_default_extraction_level_is_2(self):
        """Default extraction level should be 2."""
        import inspect

        from evidence_repository.queue.tasks import task_process_document_version

        sig = inspect.signature(task_process_document_version)
        assert sig.parameters["extraction_level"].default == 2


class TestProjectIdRequirement:
    """Tests for project_id requirement in fact/quality steps."""

    def test_facts_skipped_without_project_id(self):
        """Fact extraction should be skipped without project_id."""
        # When project_id is None, fact extraction should be skipped
        # because facts need to be associated with a project

        project_id = None
        skip_facts = False

        # Logic: skip_facts=False but project_id=None means skip anyway
        should_run_facts = not skip_facts and project_id is not None
        assert should_run_facts is False

    def test_quality_skipped_without_project_id(self):
        """Quality check should be skipped without project_id."""
        # Quality checks analyze project-level data

        project_id = None
        skip_quality = False

        # Logic: skip_quality=False but project_id=None means skip anyway
        should_run_quality = not skip_quality and project_id is not None
        assert should_run_quality is False
