"""OpenAI embeddings client."""

import logging
from typing import Sequence

from openai import AsyncOpenAI

from evidence_repository.config import get_settings

logger = logging.getLogger(__name__)


class OpenAIEmbeddingError(Exception):
    """Error from OpenAI embeddings API."""

    pass


class OpenAIEmbeddingClient:
    """Client for generating embeddings using OpenAI API.

    Uses the text-embedding-3-small model by default for cost-effective
    high-quality embeddings.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        dimensions: int | None = None,
    ):
        """Initialize OpenAI embeddings client.

        Args:
            api_key: OpenAI API key (uses settings if not provided).
            model: Embedding model name (uses settings if not provided).
            dimensions: Embedding dimensions (uses settings if not provided).
        """
        settings = get_settings()

        self.api_key = api_key or settings.openai_api_key
        self.model = model or settings.openai_embedding_model
        self.dimensions = dimensions or settings.openai_embedding_dimensions

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
        """Generate embeddings for multiple texts.

        Batches requests to OpenAI API for efficiency.

        Args:
            texts: List of texts to embed.

        Returns:
            List of embedding vectors.

        Raises:
            OpenAIEmbeddingError: If embedding generation fails.
        """
        if not texts:
            return []

        try:
            # Clean and validate texts
            cleaned_texts = [self._clean_text(t) for t in texts]

            # Filter out empty texts (keep track of indices)
            non_empty_indices = [i for i, t in enumerate(cleaned_texts) if t]
            non_empty_texts = [cleaned_texts[i] for i in non_empty_indices]

            if not non_empty_texts:
                # All texts were empty, return zero vectors
                return [[0.0] * self.dimensions for _ in texts]

            # Call OpenAI API
            response = await self.client.embeddings.create(
                model=self.model,
                input=non_empty_texts,
                dimensions=self.dimensions,
            )

            # Extract embeddings
            api_embeddings = [item.embedding for item in response.data]

            # Reconstruct full list with zero vectors for empty texts
            result: list[list[float]] = []
            api_idx = 0

            for i in range(len(texts)):
                if i in non_empty_indices:
                    result.append(api_embeddings[api_idx])
                    api_idx += 1
                else:
                    result.append([0.0] * self.dimensions)

            logger.debug(
                f"Generated {len(non_empty_texts)} embeddings "
                f"({response.usage.total_tokens} tokens)"
            )

            return result

        except Exception as e:
            logger.error(f"OpenAI embedding error: {e}")
            raise OpenAIEmbeddingError(f"Failed to generate embeddings: {e}") from e

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
