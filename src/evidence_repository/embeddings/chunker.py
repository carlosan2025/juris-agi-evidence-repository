"""Text chunking strategies for embedding generation."""

import re
from dataclasses import dataclass


@dataclass
class TextChunk:
    """A chunk of text with position information."""

    text: str
    index: int
    char_start: int
    char_end: int
    metadata: dict


class TextChunker:
    """Splits text into overlapping chunks for embedding.

    Chunks are created with configurable size and overlap to ensure
    semantic continuity across chunk boundaries.
    """

    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        separators: list[str] | None = None,
    ):
        """Initialize text chunker.

        Args:
            chunk_size: Target size of each chunk in characters.
            chunk_overlap: Number of overlapping characters between chunks.
            separators: List of separators to split on (in order of preference).
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators or ["\n\n", "\n", ". ", " ", ""]

    def chunk_text(self, text: str, metadata: dict | None = None) -> list[TextChunk]:
        """Split text into chunks.

        Args:
            text: Text to chunk.
            metadata: Optional metadata to include in each chunk.

        Returns:
            List of TextChunk objects.
        """
        if not text or not text.strip():
            return []

        chunks: list[TextChunk] = []
        base_metadata = metadata or {}

        # Normalize whitespace
        text = re.sub(r"\s+", " ", text).strip()

        # Split recursively
        splits = self._split_text(text, self.separators)

        # Merge splits into chunks of target size
        current_chunk: list[str] = []
        current_length = 0
        char_position = 0

        for split in splits:
            split_len = len(split)

            if current_length + split_len <= self.chunk_size:
                current_chunk.append(split)
                current_length += split_len
            else:
                # Save current chunk
                if current_chunk:
                    chunk_text = "".join(current_chunk)
                    chunks.append(
                        TextChunk(
                            text=chunk_text,
                            index=len(chunks),
                            char_start=char_position - current_length,
                            char_end=char_position,
                            metadata={**base_metadata, "chunk_index": len(chunks)},
                        )
                    )

                # Start new chunk with overlap
                overlap_text = self._get_overlap_text(current_chunk)
                current_chunk = [overlap_text, split] if overlap_text else [split]
                current_length = len(overlap_text) + split_len

            char_position += split_len

        # Don't forget the last chunk
        if current_chunk:
            chunk_text = "".join(current_chunk)
            if chunk_text.strip():  # Only add non-empty chunks
                chunks.append(
                    TextChunk(
                        text=chunk_text,
                        index=len(chunks),
                        char_start=char_position - current_length,
                        char_end=char_position,
                        metadata={**base_metadata, "chunk_index": len(chunks)},
                    )
                )

        return chunks

    def _split_text(self, text: str, separators: list[str]) -> list[str]:
        """Recursively split text using separators.

        Args:
            text: Text to split.
            separators: List of separators to try.

        Returns:
            List of text segments.
        """
        if not separators:
            return [text]

        separator = separators[0]
        remaining_separators = separators[1:]

        if not separator:
            # Empty separator means split by character
            return list(text)

        splits = text.split(separator)

        # If no splits occurred, try next separator
        if len(splits) == 1:
            return self._split_text(text, remaining_separators)

        # Add separator back to maintain spacing
        result: list[str] = []
        for i, split in enumerate(splits):
            if i > 0:
                result.append(separator)
            if split:
                result.append(split)

        return result

    def _get_overlap_text(self, chunks: list[str]) -> str:
        """Get overlap text from the end of current chunks.

        Args:
            chunks: Current chunk segments.

        Returns:
            Text to include as overlap in next chunk.
        """
        if not chunks:
            return ""

        full_text = "".join(chunks)
        if len(full_text) <= self.chunk_overlap:
            return full_text

        return full_text[-self.chunk_overlap :]


class SentenceChunker(TextChunker):
    """Chunks text by sentences while respecting size limits."""

    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
    ):
        """Initialize sentence-based chunker."""
        # Use sentence-ending punctuation as primary separator
        super().__init__(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ". ", "! ", "? ", "; ", ", ", " ", ""],
        )


class ParagraphChunker(TextChunker):
    """Chunks text by paragraphs while respecting size limits."""

    def __init__(
        self,
        chunk_size: int = 1500,
        chunk_overlap: int = 200,
    ):
        """Initialize paragraph-based chunker."""
        super().__init__(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n\n", "\n\n", "\n", ". ", " ", ""],
        )
