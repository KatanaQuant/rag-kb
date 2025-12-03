"""Semantic chunker for content-aware text splitting.

Uses semantic boundaries (sentences, paragraphs) to create meaningful chunks.
"""

import logging
import re
from typing import List, Dict

from pipeline.interfaces.chunker import ChunkerInterface

logger = logging.getLogger(__name__)


class SemanticChunker(ChunkerInterface):
    """Semantic chunker that respects content boundaries.

    Splits text at natural semantic boundaries:
    - Sentence endings
    - Paragraph breaks
    - Section headings

    Best for:
    - Prose-heavy documents
    - Articles and blog posts
    - Documentation with flowing text
    """

    def __init__(self, max_tokens: int = 512):
        """Initialize semantic chunker.

        Args:
            max_tokens: Maximum tokens per chunk (default: 512)
        """
        self.max_tokens = max_tokens
        # Approximate: 4 chars per token
        self.max_chars = max_tokens * 4

    @property
    def name(self) -> str:
        return "semantic"

    def chunkify(self, source: str, **kwargs) -> List[Dict]:
        """Chunk text using semantic boundaries.

        Args:
            source: Source text to chunk
            **kwargs: Unused, for interface compatibility

        Returns:
            List of chunk dictionaries with 'content' and 'metadata'
        """
        if not source or not source.strip():
            return []

        # Split into sentences
        sentences = self._split_sentences(source)

        # Group sentences into chunks
        chunks = []
        current_chunk = []
        current_size = 0

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            sentence_size = len(sentence)

            # If single sentence exceeds max, split it
            if sentence_size > self.max_chars:
                if current_chunk:
                    chunks.append({
                        'content': ' '.join(current_chunk),
                        'metadata': {'chunker': 'semantic'}
                    })
                    current_chunk = []
                    current_size = 0

                # Split long sentence into smaller pieces
                for piece in self._split_long_text(sentence):
                    chunks.append({
                        'content': piece,
                        'metadata': {'chunker': 'semantic', 'split': True}
                    })
                continue

            # Check if adding this sentence exceeds limit
            if current_size + sentence_size + 1 > self.max_chars and current_chunk:
                chunks.append({
                    'content': ' '.join(current_chunk),
                    'metadata': {'chunker': 'semantic'}
                })
                current_chunk = []
                current_size = 0

            current_chunk.append(sentence)
            current_size += sentence_size + 1  # +1 for space

        # Don't forget the last chunk
        if current_chunk:
            chunks.append({
                'content': ' '.join(current_chunk),
                'metadata': {'chunker': 'semantic'}
            })

        return chunks

    def _split_sentences(self, text: str) -> List[str]:
        """Split text into sentences.

        Handles common sentence boundaries while preserving
        abbreviations and decimal numbers.
        """
        # Simple sentence splitting - handles . ! ? followed by space and capital
        # Preserves abbreviations like "Dr.", "Mr.", "e.g.", numbers like "3.14"
        sentence_pattern = r'(?<=[.!?])\s+(?=[A-Z])'
        sentences = re.split(sentence_pattern, text)

        # Also split on double newlines (paragraphs)
        result = []
        for sentence in sentences:
            if '\n\n' in sentence:
                result.extend(sentence.split('\n\n'))
            else:
                result.append(sentence)

        return [s.strip() for s in result if s.strip()]

    def _split_long_text(self, text: str) -> List[str]:
        """Split text that exceeds max_chars into smaller pieces."""
        pieces = []
        while len(text) > self.max_chars:
            # Find a good break point (space, newline)
            break_point = text.rfind(' ', 0, self.max_chars)
            if break_point == -1:
                break_point = self.max_chars

            pieces.append(text[:break_point].strip())
            text = text[break_point:].strip()

        if text:
            pieces.append(text)

        return pieces
