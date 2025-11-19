"""Cell Chunker Interface - Duck Type for POODR

POODR Phase 3: Duck Typing
- Replaces if/elif cell_type conditionals
- Polymorphism via behavior, not type checking
- "If it chunks like a cell, it's a cell chunker"

Duck Type: Chunkable
- Responds to: chunk(cell, path) -> List[Dict]
- Implementation: CodeCellChunker, MarkdownCellChunker
"""

from typing import List, Dict, Protocol


class ChunkableCell(Protocol):
    """Duck type for objects that can be chunked

    POODR Pattern: Duck Typing (Chapter 5)
    - Trust objects to respond to messages
    - Don't check types, check behavior
    - Polymorphism through shared interface

    Any class that implements chunk(cell, path) is Chunkable!
    """

    @staticmethod
    def chunk(cell, path: str) -> List[Dict]:
        """Chunk a cell into searchable chunks

        Args:
            cell: Jupyter cell object
            path: File path for metadata

        Returns:
            List of chunk dictionaries with text, metadata
        """
        ...


class CellChunkerFactory:
    """Factory for creating cell chunkers based on cell type

    POODR Pattern: Factory + Duck Typing
    - Creates appropriate chunker based on cell_type
    - Returns objects that respond to chunk() message
    - Caller doesn't need to know which chunker it got
    """

    @staticmethod
    def create_chunker(cell_type: str) -> ChunkableCell:
        """Create appropriate chunker for cell type

        Args:
            cell_type: 'code' or 'markdown'

        Returns:
            Chunker object that responds to chunk() message

        Raises:
            ValueError: If cell_type is unknown
        """
        from ingestion.jupyter.code_cell_chunker import CodeCellChunker
        from ingestion.jupyter.markdown_chunker import MarkdownCellChunker

        if cell_type == 'code':
            return CodeCellChunker()
        elif cell_type == 'markdown':
            return MarkdownCellChunker()
        else:
            raise ValueError(f"Unknown cell type: {cell_type}")

    @staticmethod
    def chunk_cell(cell, path: str) -> List[Dict]:
        """Chunk a cell using appropriate chunker (convenience method)

        Args:
            cell: Jupyter cell object with cell_type attribute
            path: File path for metadata

        Returns:
            List of chunk dictionaries
        """
        if not hasattr(cell, 'cell_type'):
            return []  # Skip cells without type

        if cell.cell_type not in ['code', 'markdown']:
            return []  # Skip raw cells

        chunker = CellChunkerFactory.create_chunker(cell.cell_type)
        return chunker.chunk(cell, path)
