"""Semantic chunker - extracted from ObsidianExtractor

POODR Phase 2.2: God Class Decomposition
- Extracted from ObsidianExtractor (CC 16 - highest complexity!)
- Single Responsibility: Chunk markdown with semantic boundaries
- Reduces ObsidianExtractor complexity
"""

from pathlib import Path
from typing import List, Tuple, Optional


class SemanticChunker:
    """Chunk markdown content with semantic awareness

    Single Responsibility: Smart markdown chunking

    Respects markdown structure:
    - Headers (# ## ###) create hard boundaries
    - Paragraphs stay together
    - Code blocks stay together
    - Max chunk size: ~2048 chars (aligns with embedding model)
    - Overlap between chunks for context preservation
    """

    def __init__(self, max_size: int = 2048, overlap: int = 200):
        """Initialize chunker with size parameters

        Args:
            max_size: Maximum chunk size in characters
            overlap: Overlap size in characters between chunks
        """
        self.max_size = max_size
        self.overlap = overlap

    def chunk(self, content: str, path: Path) -> List[Tuple[str, Optional[int]]]:
        """Chunk content with header-aware boundaries

        Uses custom semantic chunking that respects markdown structure:
        - Headers (# ## ###) create hard boundaries
        - Paragraphs stay together
        - Code blocks stay together
        - Max chunk size: ~2048 chars (aligns with embedding model)

        Args:
            content: Markdown content to chunk
            path: File path (for metadata, not used in chunking)

        Returns:
            List of (chunk_text, page_number) tuples (page_number always None)
        """
        chunks = []
        current_chunk = []
        current_size = 0

        lines = content.split('\n')
        i = 0

        while i < len(lines):
            line = lines[i]

            # Header creates boundary
            if line.startswith('#'):
                if current_chunk:
                    chunks.append(('\n'.join(current_chunk), None))
                    # Add overlap from previous chunk
                    current_chunk = self._get_overlap_lines(current_chunk, self.overlap)
                    current_size = sum(len(l) for l in current_chunk)

                current_chunk.append(line)
                current_size += len(line) + 1
                i += 1
                continue

            # Code block - keep together
            if line.startswith('```'):
                code_block = [line]
                i += 1
                while i < len(lines) and not lines[i].startswith('```'):
                    code_block.append(lines[i])
                    i += 1
                if i < len(lines):  # Closing ```
                    code_block.append(lines[i])
                    i += 1

                code_text = '\n'.join(code_block)
                if current_size + len(code_text) > self.max_size and current_chunk:
                    # Flush current chunk
                    chunks.append(('\n'.join(current_chunk), None))
                    current_chunk = self._get_overlap_lines(current_chunk, self.overlap)
                    current_size = sum(len(l) for l in current_chunk)

                current_chunk.extend(code_block)
                current_size += len(code_text)
                continue

            # Regular line
            if current_size + len(line) > self.max_size:
                if current_chunk:
                    chunks.append(('\n'.join(current_chunk), None))
                    current_chunk = self._get_overlap_lines(current_chunk, self.overlap)
                    current_size = sum(len(l) for l in current_chunk)

            current_chunk.append(line)
            current_size += len(line) + 1
            i += 1

        # Final chunk
        if current_chunk:
            chunks.append(('\n'.join(current_chunk), None))

        return chunks

    def _get_overlap_lines(self, lines: List[str], overlap_chars: int) -> List[str]:
        """Get last N characters worth of lines for overlap

        Args:
            lines: Lines from previous chunk
            overlap_chars: Target overlap size in characters

        Returns:
            List of lines from end of previous chunk for overlap
        """
        if not lines:
            return []

        overlap_lines = []
        char_count = 0

        for line in reversed(lines):
            if char_count >= overlap_chars:
                break
            overlap_lines.insert(0, line)
            char_count += len(line) + 1

        return overlap_lines
