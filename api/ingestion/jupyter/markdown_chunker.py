"""Markdown cell chunker - extracted from JupyterExtractor

POODR Phase 2: God Class Decomposition
- Extracted from JupyterExtractor
- Single Responsibility: Process markdown cells
- Reduces JupyterExtractor complexity
"""

from typing import List, Dict
from ingestion.jupyter_extractor import NotebookCell


class MarkdownCellChunker:
    """Process markdown cells from Jupyter notebooks

    Single Responsibility: Chunk markdown cells

    Markdown cells are usually section headers or explanations.
    Split on headers (##) as natural boundaries.
    """

    @staticmethod
    def chunk(cell: NotebookCell, filepath: str) -> List[Dict]:
        """Process markdown cell

        Markdown cells are usually section headers or explanations.
        Split on headers (## ) as natural boundaries.

        Args:
            cell: Notebook cell
            filepath: Notebook filepath

        Returns:
            List of markdown chunks
        """
        if not cell.source or not cell.source.strip():
            return []

        # Check if cell starts with header
        has_header = cell.source.strip().startswith('#')

        # For now, treat each markdown cell as one chunk
        # (Can enhance later to split on headers within cell)
        return [{
            'content': cell.source,
            'type': 'markdown',
            'cell_number': cell.cell_number,
            'cell_type': 'markdown',
            'is_header': has_header,
            'filepath': filepath,
        }]
