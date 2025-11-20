

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
        """Chunk content with header-aware boundaries"""
        chunks = []
        current_chunk = []
        current_size = 0
        lines = content.split('\n')
        i = 0

        while i < len(lines):
            line = lines[i]

            if self._is_header(line):
                chunks, current_chunk, current_size = self._process_header(line, chunks, current_chunk)
                i += 1
            elif self._is_code_block_start(line):
                i, current_chunk, current_size = self._process_code_block(lines, i, chunks, current_chunk, current_size)
            else:
                current_chunk, current_size = self._process_regular_line(line, chunks, current_chunk, current_size)
                i += 1

        return self._finalize_chunks(chunks, current_chunk)

    def _is_header(self, line: str) -> bool:
        """Check if line is a markdown header"""
        return line.startswith('#')

    def _is_code_block_start(self, line: str) -> bool:
        """Check if line starts a code block"""
        return line.startswith('```')

    def _process_header(self, line: str, chunks: List, current_chunk: List) -> Tuple:
        """Process header line and create boundary"""
        if current_chunk:
            chunks.append(('\n'.join(current_chunk), None))
            current_chunk = self._get_overlap_lines(current_chunk, self.overlap)

        current_chunk.append(line)
        current_size = self._calculate_chunk_size(current_chunk)
        return chunks, current_chunk, current_size

    def _process_code_block(self, lines: List[str], i: int, chunks: List, current_chunk: List, current_size: int) -> Tuple:
        """Process complete code block"""
        code_block, i = self._extract_code_block(lines, i)
        current_chunk, current_size = self._add_code_block_to_chunk(code_block, chunks, current_chunk, current_size)
        return i, current_chunk, current_size

    def _extract_code_block(self, lines: List[str], start_idx: int) -> Tuple[List[str], int]:
        """Extract complete code block from lines"""
        code_block = [lines[start_idx]]
        i = start_idx + 1
        while i < len(lines) and not lines[i].startswith('```'):
            code_block.append(lines[i])
            i += 1
        if i < len(lines):
            code_block.append(lines[i])
            i += 1
        return code_block, i

    def _add_code_block_to_chunk(self, code_block: List[str], chunks: List, current_chunk: List, current_size: int) -> Tuple:
        """Add code block to current chunk, flushing if needed"""
        code_text = '\n'.join(code_block)
        if current_size + len(code_text) > self.max_size and current_chunk:
            chunks.append(('\n'.join(current_chunk), None))
            current_chunk = self._get_overlap_lines(current_chunk, self.overlap)
            current_size = self._calculate_chunk_size(current_chunk)

        current_chunk.extend(code_block)
        current_size += len(code_text)
        return current_chunk, current_size

    def _process_regular_line(self, line: str, chunks: List, current_chunk: List, current_size: int) -> Tuple:
        """Process regular text line"""
        if current_size + len(line) > self.max_size and current_chunk:
            chunks.append(('\n'.join(current_chunk), None))
            current_chunk = self._get_overlap_lines(current_chunk, self.overlap)
            current_size = self._calculate_chunk_size(current_chunk)

        current_chunk.append(line)
        current_size += len(line) + 1
        return current_chunk, current_size

    def _calculate_chunk_size(self, chunk: List[str]) -> int:
        """Calculate total size of chunk"""
        return sum(len(l) + 1 for l in chunk)

    def _finalize_chunks(self, chunks: List, current_chunk: List) -> List[Tuple[str, Optional[int]]]:
        """Add final chunk if exists"""
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
