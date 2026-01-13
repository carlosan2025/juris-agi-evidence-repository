"""OpenAI embeddings client with retry logic and rate limiting."""

import asyncio
import logging
import random
from typing import Sequence

from openai import AsyncOpenAI, RateLimitError, APIError, APIConnectionError, APITimeoutError

from evidence_repository.config import get_settings

logger = logging.getLogger(__name__)


class OpenAIEmbeddingError(Exception):
    """Error from OpenAI embeddings API."""

    pass


class RateLimitExceededError(OpenAIEmbeddingError):
    """Rate limit exceeded, should retry after delay."""

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class OpenAIEmbeddingClient:
    """Client for generating embeddings using OpenAI API.

    Uses the text-embedding-3-small model by default for cost-effective
    high-quality embeddings.

    Features:
    - Exponential backoff retry for transient errors
    - Rate limit handling with retry-after
    - Automatic batching for large requests
    - Token tracking for cost estimation
    """

    # Retry configuration
    MAX_RETRIES = 5
    BASE_DELAY = 1.0  # seconds
    MAX_DELAY = 60.0  # seconds
    BATCH_SIZE = 100  # Max texts per API call (OpenAI limit is 2048)

    # Retryable errors
    RETRYABLE_ERRORS = (RateLimitError, APIConnectionError, APITimeoutError)

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        dimensions: int | None = None,
        max_retries: int | None = None,
    ):
        """Initialize OpenAI embeddings client.

        Args:
            api_key: OpenAI API key (uses settings if not provided).
            model: Embedding model name (uses settings if not provided).
            dimensions: Embedding dimensions (uses settings if not provided).
            max_retries: Maximum retry attempts for transient errors.
        """
        settings = get_settings()

        self.api_key = api_key or settings.openai_api_key
        self.model = model or settings.openai_embedding_model
        self.dimensions = dimensions or settings.openai_embedding_dimensions
        self.max_retries = max_retries or self.MAX_RETRIES

        # Track total tokens used (for cost estimation)
        self.total_tokens_used = 0

        if not self.api_key:
            logger.warning(
                "OpenAI API key not configured. "
                "Set OPENAI_API_KEY environment variable."
            )

        self._client: AsyncOpenAI | None = None

    @property
    def client(self) -> AsyncOpenAI:
        """Get or create the AsyncOpenAI client."""
        if self._client is None:
            if not self.api_key:
                raise OpenAIEmbeddingError(
                    "OpenAI API key not configured. "
                    "Set OPENAI_API_KEY environment variable."
                )
            self._client = AsyncOpenAI(api_key=self.api_key)
        return self._client

    async def embed_text(self, text: str) -> list[float]:
        """Generate embedding for a single text.

        Args:
            text: Text to embed.

        Returns:
            Embedding vector as list of floats.

        Raises:
            OpenAIEmbeddingError: If embedding generation fails.
        """
        embeddings = await self.embed_texts([text])
        return embeddings[0]

    async def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts with retry logic.

        Batches requests to OpenAI API for efficiency. Handles rate limits
        and transient errors with exponential backoff.

        Args:
            texts: List of texts to embed.

        Returns:
            List of embedding vectors.

        Raises:
            OpenAIEmbeddingError: If embedding generation fails after retries.
        """
        if not texts:
            return []

        # Clean and validate texts
        cleaned_texts = [self._clean_text(t) for t in texts]

        # Filter out empty texts (keep track of indices)
        non_empty_indices = [i for i, t in enumerate(cleaned_texts) if t]
        non_empty_texts = [cleaned_texts[i] for i in non_empty_indices]

        if not non_empty_texts:
            # All texts were empty, return zero vectors
            return [[0.0] * self.dimensions for _ in texts]

        # Process in batches if needed
        all_embeddings: list[list[float]] = []

        for batch_start in range(0, len(non_empty_texts), self.BATCH_SIZE):
            batch_end = min(batch_start + self.BATCH_SIZE, len(non_empty_texts))
            batch = non_empty_texts[batch_start:batch_end]

            batch_embeddings = await self._embed_batch_with_retry(batch)
            all_embeddings.extend(batch_embeddings)

        # Reconstruct full list with zero vectors for empty texts
        result: list[list[float]] = []
        api_idx = 0

        for i in range(len(texts)):
            if i in non_empty_indices:
                result.append(all_embeddings[api_idx])
                api_idx += 1
            else:
                result.append([0.0] * self.dimensions)

        return result

    async def _embed_batch_with_retry(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts with exponential backoff retry.

        Args:
            texts: Batch of texts to embed.

        Returns:
            List of embedding vectors.

        Raises:
            OpenAIEmbeddingError: If all retries fail.
        """
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                return await self._call_embedding_api(texts)

            except RateLimitError as e:
                last_error = e
                # Extract retry-after if available
                retry_after = self._get_retry_after(e)
                delay = retry_after or self._calculate_backoff(attempt)

                logger.warning(
                    f"Rate limit hit (attempt {attempt + 1}/{self.max_retries + 1}), "
                    f"waiting {delay:.1f}s"
                )

                if attempt < self.max_retries:
                    await asyncio.sleep(delay)
                else:
                    raise RateLimitExceededError(
                        f"Rate limit exceeded after {self.max_retries + 1} attempts",
                        retry_after=retry_after,
                    ) from e

            except (APIConnectionError, APITimeoutError) as e:
                last_error = e
                delay = self._calculate_backoff(attempt)

                logger.warning(
                    f"Transient error (attempt {attempt + 1}/{self.max_retries + 1}): {e}, "
                    f"retrying in {delay:.1f}s"
                )

                if attempt < self.max_retries:
                    await asyncio.sleep(delay)
                else:
                    raise OpenAIEmbeddingError(
                        f"API error after {self.max_retries + 1} attempts: {e}"
                    ) from e

            except APIError as e:
                # Non-retryable API errors
                logger.error(f"OpenAI API error: {e}")
                raise OpenAIEmbeddingError(f"API error: {e}") from e

            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                raise OpenAIEmbeddingError(f"Unexpected error: {e}") from e

        # Should not reach here, but just in case
        raise OpenAIEmbeddingError(f"Failed after retries: {last_error}")

    async def _call_embedding_api(self, texts: list[str]) -> list[list[float]]:
        """Make the actual API call to generate embeddings.

        Args:
            texts: Texts to embed.

        Returns:
            List of embedding vectors.
        """
        response = await self.client.embeddings.create(
            model=self.model,
            input=texts,
            dimensions=self.dimensions,
        )

        # Track token usage
        self.total_tokens_used += response.usage.total_tokens

        logger.debug(
            f"Generated {len(texts)} embeddings "
            f"({response.usage.total_tokens} tokens)"
        )

        return [item.embedding for item in response.data]

    def _calculate_backoff(self, attempt: int) -> float:
        """Calculate exponential backoff delay with jitter.

        Args:
            attempt: Current attempt number (0-indexed).

        Returns:
            Delay in seconds.
        """
        # Exponential backoff: base * 2^attempt
        delay = self.BASE_DELAY * (2 ** attempt)

        # Add jitter (0-25% of delay)
        jitter = delay * random.uniform(0, 0.25)
        delay += jitter

        # Cap at max delay
        return min(delay, self.MAX_DELAY)

    def _get_retry_after(self, error: RateLimitError) -> float | None:
        """Extract retry-after value from rate limit error.

        Args:
            error: Rate limit error from OpenAI.

        Returns:
            Retry-after seconds or None.
        """
        # Try to extract from error response
        if hasattr(error, 'response') and error.response:
            retry_after = error.response.headers.get('retry-after')
            if retry_after:
                try:
                    return float(retry_after)
                except ValueError:
                    pass

        # Default fallback
        return None

    def _clean_text(self, text: str) -> str:
        """Clean text for embedding.

        Args:
            text: Raw text.

        Returns:
            Cleaned text suitable for embedding.
        """
        if not text:
            return ""

        # Remove excessive whitespace
        text = " ".join(text.split())

        # Truncate very long texts (OpenAI has token limits)
        # text-embedding-3-small supports up to 8191 tokens
        # Rough estimate: 1 token ~= 4 characters
        max_chars = 8000 * 4
        if len(text) > max_chars:
            text = text[:max_chars]

        return text

    async def close(self) -> None:
        """Close the client connection."""
        if self._client:
            await self._client.close()
            self._client = None

    def get_token_usage(self) -> int:
        """Get total tokens used by this client instance.

        Returns:
            Total tokens consumed.
        """
        return self.total_tokens_used

    def reset_token_usage(self) -> None:
        """Reset the token usage counter."""
        self.total_tokens_used = 0
