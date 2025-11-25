

from pathlib import Path
from typing import List, Tuple, Optional
from dataclasses import dataclass, field

@dataclass
class ChunkAccumulator:
    """Accumulates chunk state during markdown parsing

    Encapsulates the data clump (chunks, current_chunk, current_size)
    that was being passed around multiple methods.
    """
    chunks: List[Tuple[str, Optional[int]]] = field(default_factory=list)
    current_chunk: List[str] = field(default_factory=list)
    current_size: int = 0

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
        acc = ChunkAccumulator()
        lines = content.split('\n')
        i = 0

        while i < len(lines):
            line = lines[i]

            if self._is_header(line):
                self._process_header(line, acc)
                i += 1
            elif self._is_code_block_start(line):
                i = self._process_code_block(lines, i, acc)
            else:
                self._process_regular_line(line, acc)
                i += 1

        return self._finalize_chunks(acc)

    def _is_header(self, line: str) -> bool:
        """Check if line is a markdown header"""
        return line.startswith('#')

    def _is_code_block_start(self, line: str) -> bool:
        """Check if line starts a code block"""
        return line.startswith('```')

    def _process_header(self, line: str, acc: ChunkAccumulator):
        """Process header line and create boundary"""
        if acc.current_chunk:
            acc.chunks.append(('\n'.join(acc.current_chunk), None))
            acc.current_chunk = self._get_overlap_lines(acc.current_chunk, self.overlap)

        acc.current_chunk.append(line)
        acc.current_size = self._calculate_chunk_size(acc.current_chunk)

    def _process_code_block(self, lines: List[str], i: int, acc: ChunkAccumulator) -> int:
        """Process complete code block"""
        code_block, i = self._extract_code_block(lines, i)
        self._add_code_block_to_chunk(code_block, acc)
        return i

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

    def _add_code_block_to_chunk(self, code_block: List[str], acc: ChunkAccumulator):
        """Add code block to current chunk, flushing if needed"""
        code_text = '\n'.join(code_block)
        if acc.current_size + len(code_text) > self.max_size and acc.current_chunk:
            acc.chunks.append(('\n'.join(acc.current_chunk), None))
            acc.current_chunk = self._get_overlap_lines(acc.current_chunk, self.overlap)
            acc.current_size = self._calculate_chunk_size(acc.current_chunk)

        acc.current_chunk.extend(code_block)
        acc.current_size += len(code_text)

    def _process_regular_line(self, line: str, acc: ChunkAccumulator):
        """Process regular text line"""
        if acc.current_size + len(line) > self.max_size and acc.current_chunk:
            acc.chunks.append(('\n'.join(acc.current_chunk), None))
            acc.current_chunk = self._get_overlap_lines(acc.current_chunk, self.overlap)
            acc.current_size = self._calculate_chunk_size(acc.current_chunk)

        acc.current_chunk.append(line)
        acc.current_size += len(line) + 1

    def _calculate_chunk_size(self, chunk: List[str]) -> int:
        """Calculate total size of chunk"""
        return sum(len(l) + 1 for l in chunk)

    def _finalize_chunks(self, acc: ChunkAccumulator) -> List[Tuple[str, Optional[int]]]:
        """Add final chunk if exists"""
        if acc.current_chunk:
            acc.chunks.append(('\n'.join(acc.current_chunk), None))
        return acc.chunks

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
