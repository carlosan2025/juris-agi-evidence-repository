"""Tests for span embedding service."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from evidence_repository.embeddings.span_embedding_service import SpanEmbeddingService
from evidence_repository.embeddings.openai_client import (
    OpenAIEmbeddingClient,
    OpenAIEmbeddingError,
    RateLimitExceededError,
)
from evidence_repository.models.evidence import SpanType


class TestOpenAIEmbeddingClient:
    """Tests for OpenAI embedding client."""

    @pytest.fixture
    def client(self):
        """Create client with mocked API key."""
        with patch.object(OpenAIEmbeddingClient, "client", new_callable=MagicMock):
            return OpenAIEmbeddingClient(api_key="test-key")

    def test_clean_text_empty(self, client):
        """Test cleaning empty text."""
        assert client._clean_text("") == ""
        assert client._clean_text(None) == ""

    def test_clean_text_whitespace(self, client):
        """Test cleaning excessive whitespace."""
        text = "  hello   world  \n\t  test  "
        cleaned = client._clean_text(text)
        assert cleaned == "hello world test"

    def test_clean_text_truncation(self, client):
        """Test that very long text is truncated."""
        # Create text longer than max_chars (8000 * 4 = 32000)
        long_text = "A" * 40000
        cleaned = client._clean_text(long_text)
        assert len(cleaned) == 32000

    def test_calculate_backoff(self, client):
        """Test exponential backoff calculation."""
        # First attempt (2^0 = 1)
        delay0 = client._calculate_backoff(0)
        assert 1.0 <= delay0 <= 1.25  # Base delay + up to 25% jitter

        # Second attempt (2^1 = 2)
        delay1 = client._calculate_backoff(1)
        assert 2.0 <= delay1 <= 2.5

        # Third attempt (2^2 = 4)
        delay2 = client._calculate_backoff(2)
        assert 4.0 <= delay2 <= 5.0

        # Test max delay cap
        delay_high = client._calculate_backoff(10)
        assert delay_high <= 60.0  # MAX_DELAY

    def test_token_usage_tracking(self, client):
        """Test token usage tracking methods."""
        assert client.get_token_usage() == 0

        client.total_tokens_used = 100
        assert client.get_token_usage() == 100

        client.reset_token_usage()
        assert client.get_token_usage() == 0


class TestSpanEmbeddingServiceTypes:
    """Tests for span type filtering in embedding service."""

    def test_embeddable_span_types(self):
        """Test that only text-based spans are embeddable."""
        expected_types = {SpanType.TEXT, SpanType.HEADING, SpanType.CITATION, SpanType.FOOTNOTE}
        assert SpanEmbeddingService.EMBEDDABLE_SPAN_TYPES == expected_types

    def test_non_embeddable_types(self):
        """Test that table and figure spans are not embeddable."""
        embeddable = SpanEmbeddingService.EMBEDDABLE_SPAN_TYPES
        assert SpanType.TABLE not in embeddable
        assert SpanType.FIGURE not in embeddable
        assert SpanType.OTHER not in embeddable


class TestSpanEmbeddingServiceMocked:
    """Tests for SpanEmbeddingService with mocked dependencies."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database session."""
        return AsyncMock()

    @pytest.fixture
    def mock_embedding_client(self):
        """Create mock embedding client."""
        client = AsyncMock(spec=OpenAIEmbeddingClient)
        client.embed_text.return_value = [0.1] * 1536
        client.embed_texts.return_value = [[0.1] * 1536]
        client.get_token_usage.return_value = 100
        return client

    @pytest.fixture
    def service(self, mock_db, mock_embedding_client):
        """Create service with mocked dependencies."""
        return SpanEmbeddingService(
            db=mock_db,
            embedding_client=mock_embedding_client,
            batch_size=10,
        )

    @pytest.mark.asyncio
    async def test_embed_single_span_non_embeddable_type(self, service):
        """Test that non-embeddable span types are skipped."""
        mock_span = MagicMock()
        mock_span.span_type = SpanType.TABLE
        mock_span.id = uuid4()

        result = await service.embed_single_span(mock_span)
        assert result is None

    @pytest.mark.asyncio
    async def test_embed_single_span_empty_content(self, service):
        """Test that spans with empty content are skipped."""
        mock_span = MagicMock()
        mock_span.span_type = SpanType.TEXT
        mock_span.id = uuid4()
        mock_span.text_content = ""

        result = await service.embed_single_span(mock_span)
        assert result is None

    @pytest.mark.asyncio
    async def test_embed_single_span_whitespace_only(self, service):
        """Test that spans with only whitespace are skipped."""
        mock_span = MagicMock()
        mock_span.span_type = SpanType.TEXT
        mock_span.id = uuid4()
        mock_span.text_content = "   \n\t  "

        result = await service.embed_single_span(mock_span)
        assert result is None


class TestSearchModeFiltering:
    """Tests for search mode filtering."""

    def test_search_modes(self):
        """Test search mode enum values."""
        from evidence_repository.services.search_service import SearchMode

        assert SearchMode.ALL.value == "all"
        assert SearchMode.SPANS_ONLY.value == "spans_only"
        assert SearchMode.CHUNKS_ONLY.value == "chunks_only"

    def test_search_result_item_span_fields(self):
        """Test SearchResultItem includes span-specific fields."""
        from evidence_repository.services.search_service import SearchResultItem

        result = SearchResultItem(
            chunk_id=uuid4(),
            document_id=uuid4(),
            document_version_id=uuid4(),
            span_id=uuid4(),
            text="Test text",
            similarity=0.95,
            chunk_index=0,
            char_start=0,
            char_end=100,
            document_filename="test.pdf",
            document_content_type="application/pdf",
            metadata={},
            span_type="text",
            span_locator={"type": "text", "offset_start": 0, "offset_end": 100},
        )

        assert result.span_type == "text"
        assert result.span_locator is not None
        assert result.span_locator["type"] == "text"

    def test_search_results_includes_mode(self):
        """Test SearchResults includes mode and span types."""
        from evidence_repository.services.search_service import SearchResults, SearchMode

        results = SearchResults(
            query="test query",
            results=[],
            total=0,
            search_time_ms=10.0,
            timestamp=datetime.utcnow(),
            mode=SearchMode.SPANS_ONLY,
            span_types_searched=["text", "heading"],
        )

        assert results.mode == SearchMode.SPANS_ONLY
        assert results.span_types_searched == ["text", "heading"]


class TestRetryLogic:
    """Tests for retry logic in embedding client."""

    @pytest.mark.asyncio
    async def test_rate_limit_error_properties(self):
        """Test RateLimitExceededError stores retry_after."""
        error = RateLimitExceededError("Rate limited", retry_after=30.0)
        assert error.retry_after == 30.0
        assert "Rate limited" in str(error)

    @pytest.mark.asyncio
    async def test_embedding_error_base(self):
        """Test OpenAIEmbeddingError base exception."""
        error = OpenAIEmbeddingError("API failed")
        assert "API failed" in str(error)


class TestBatchProcessing:
    """Tests for batch processing in embedding service."""

    def test_batch_size_configuration(self):
        """Test batch size can be configured."""
        mock_db = AsyncMock()
        service = SpanEmbeddingService(db=mock_db, batch_size=25)
        assert service.batch_size == 25

    def test_default_batch_size(self):
        """Test default batch size."""
        mock_db = AsyncMock()
        service = SpanEmbeddingService(db=mock_db)
        assert service.batch_size == 50


class TestTaskEmbedDocument:
    """Tests for task_embed_document worker function."""

    def test_task_signature(self):
        """Test task_embed_document has correct signature."""
        from evidence_repository.queue.tasks import task_embed_document
        import inspect

        sig = inspect.signature(task_embed_document)
        params = list(sig.parameters.keys())

        assert "document_id" in params
        assert "version_id" in params
        assert "embed_spans" in params
        assert "reprocess" in params

    def test_task_reembed_version_exists(self):
        """Test task_reembed_version function exists."""
        from evidence_repository.queue.tasks import task_reembed_version
        import inspect

        sig = inspect.signature(task_reembed_version)
        params = list(sig.parameters.keys())

        assert "version_id" in params
