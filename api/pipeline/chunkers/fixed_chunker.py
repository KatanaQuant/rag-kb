"""Fixed-size chunker for simple token-based splitting.

Splits text into fixed-size chunks based on token count.
Simple and predictable, useful for uniform chunk sizes.
"""

import logging
from typing import List, Dict

from pipeline.interfaces.chunker import ChunkerInterface

logger = logging.getLogger(__name__)


class FixedChunker(ChunkerInterface):
    """Fixed-size token-based chunker.

    Splits text into chunks of approximately equal token size.
    Uses overlap to maintain context between chunks.

    Best for:
    - When uniform chunk sizes are required
    - Simple content without complex structure
    - Testing and benchmarking
    """

    def __init__(self, max_tokens: int = 512, overlap_tokens: int = 50):
        """Initialize fixed chunker.

        Args:
            max_tokens: Maximum tokens per chunk (default: 512)
            overlap_tokens: Token overlap between chunks (default: 50)
        """
        self.max_tokens = max_tokens
        self.overlap_tokens = overlap_tokens
        # Approximate: 4 chars per token
        self.max_chars = max_tokens * 4
        self.overlap_chars = overlap_tokens * 4

    @property
    def name(self) -> str:
        return "fixed"

    def chunkify(self, source: str, **kwargs) -> List[Dict]:
        """Chunk text into fixed-size pieces.

        Args:
            source: Source text to chunk
            **kwargs: Unused, for interface compatibility

        Returns:
            List of chunk dictionaries with 'content' and 'metadata'
        """
        if not source or not source.strip():
            return []

        text = source.strip()
        chunks = []
        start = 0

        while start < len(text):
            # Calculate end position
            end = start + self.max_chars

            # If this is the last chunk, take everything
            if end >= len(text):
                chunk_text = text[start:].strip()
                if chunk_text:
                    chunks.append({
                        'content': chunk_text,
                        'metadata': {
                            'chunker': 'fixed',
                            'chunk_index': len(chunks),
                            'start_char': start
                        }
                    })
                break

            # Find a good break point (word boundary)
            break_point = self._find_break_point(text, end)

            chunk_text = text[start:break_point].strip()
            if chunk_text:
                chunks.append({
                    'content': chunk_text,
                    'metadata': {
                        'chunker': 'fixed',
                        'chunk_index': len(chunks),
                        'start_char': start
                    }
                })

            # Move start, accounting for overlap
            start = break_point - self.overlap_chars
            if start < 0:
                start = 0
            # Ensure we're making progress
            if start <= chunks[-1]['metadata']['start_char'] if chunks else 0:
                start = break_point

        return chunks

    def _find_break_point(self, text: str, target: int) -> int:
        """Find a good break point near the target position.

        Prefers breaking at:
        1. Paragraph breaks (double newline)
        2. Sentence endings
        3. Word boundaries (spaces)
        """
        # Look within a window around the target
        window_start = max(0, target - 100)
        window_end = min(len(text), target + 50)

        # Check for paragraph break
        para_break = text.rfind('\n\n', window_start, target)
        if para_break != -1 and para_break > window_start:
            return para_break + 2  # After the newlines

        # Check for sentence ending
        for punct in ['. ', '! ', '? ']:
            sent_break = text.rfind(punct, window_start, target)
            if sent_break != -1 and sent_break > window_start:
                return sent_break + 2  # After punct and space

        # Fall back to word boundary
        space = text.rfind(' ', window_start, target)
        if space != -1:
            return space + 1

        # Last resort: hard break at target
        return target
