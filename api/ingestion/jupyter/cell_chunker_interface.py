"""Cell chunker interface using duck typing"""

from typing import List, Dict, Protocol

class ChunkableCell(Protocol):
    """Protocol for cell chunkers"""
    

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
