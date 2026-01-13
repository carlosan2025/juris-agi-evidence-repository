"""Embeddings module for vector search."""

from evidence_repository.embeddings.chunker import TextChunker
from evidence_repository.embeddings.openai_client import OpenAIEmbeddingClient
from evidence_repository.embeddings.service import EmbeddingService

__all__ = ["EmbeddingService", "TextChunker", "OpenAIEmbeddingClient"]
