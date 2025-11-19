"""Code Cell Chunker - Duck Type Implementation

POODR Phase 3: Duck Typing
- Implements Chunkable duck type
- Responds to: chunk(cell, path)
- Delegates to ChunkerFactory for actual chunking
"""

from typing import List, Dict
from ingestion.chunker_factory import ChunkerFactory


class CodeCellChunker:
    """Chunk code cells using AST-aware chunking

    Duck Type: Implements Chunkable interface
    - Responds to: chunk(cell, path)
    - Polymorphic with MarkdownCellChunker

    POODR Pattern: Duck Typing + Delegation
    - Trusts ChunkerFactory to provide right chunker
    - Enriches chunks with cell metadata
    """

    def __init__(self, chunker_factory: ChunkerFactory = None):
        """Initialize with optional chunker factory

        Args:
            chunker_factory: Factory for creating code chunkers
                            If None, uses default ChunkerFactory
        """
        self.chunker_factory = chunker_factory or ChunkerFactory()

    def chunk(self, cell, path: str) -> List[Dict]:
        """Chunk code cell into searchable chunks

        Duck Type Method: Implements Chunkable interface

        Args:
            cell: Notebook cell object with source, outputs, etc.
            path: File path for metadata

        Returns:
            List of chunk dictionaries with code, metadata, outputs
        """
        if not cell.source or not cell.source.strip():
            return []

        # Detect language from cell metadata or path
        language = self._detect_language(cell, path)

        # Delegate to chunker factory for actual chunking
        cell_size = len(cell.source)
        chunker = self.chunker_factory.create_chunker(language, cell_size)
        code_chunks = chunker.chunkify(cell.source, filepath=path)

        # Enrich chunks with cell metadata
        enriched_chunks = []
        for chunk in code_chunks:
            enriched_chunks.append({
                'content': chunk['content'],
                'type': 'code',
                'language': language,
                'cell_number': getattr(cell, 'cell_number', 0),
                'cell_type': 'code',
                'execution_count': getattr(cell, 'execution_count', None),
                'has_output': len(getattr(cell, 'outputs', [])) > 0,
                'outputs': getattr(cell, 'outputs', []),
                'metadata': chunk.get('metadata', {}),
                'filepath': path,
            })

        return enriched_chunks

    def _detect_language(self, cell, path: str) -> str:
        """Detect programming language for cell

        Args:
            cell: Notebook cell
            path: File path (fallback detection)

        Returns:
            Language string ('python', 'r', etc.)
        """
        # Try cell.language attribute (set by JupyterExtractor)
        if hasattr(cell, 'language'):
            return cell.language

        # Try cell metadata
        if hasattr(cell, 'metadata') and 'language' in cell.metadata:
            return cell.metadata['language']

        # Fallback to Python for Jupyter notebooks
        return 'python'
