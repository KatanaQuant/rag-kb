

from typing import List, Dict
from ingestion.chunker_factory import ChunkerFactory

class CodeCellChunker:
    

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

        language = self._detect_language(cell, path)
        code_chunks = self._create_code_chunks(cell, language, path)
        return self._enrich_chunks_with_metadata(code_chunks, cell, language, path)

    def _create_code_chunks(self, cell, language: str, path: str) -> List[Dict]:
        """Create code chunks using chunker factory"""
        cell_size = len(cell.source)
        chunker = self.chunker_factory.create_chunker(language, cell_size)
        return chunker.chunkify(cell.source, filepath=path)

    def _enrich_chunks_with_metadata(self, code_chunks: List[Dict], cell,
                                     language: str, path: str) -> List[Dict]:
        """Enrich chunks with cell metadata"""
        enricher = ChunkEnricher(cell, language, path)
        return [enricher.build_enriched_chunk(chunk) for chunk in code_chunks]

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


class ChunkEnricher:
    """Enriches code chunks with cell metadata

    Encapsulates cell context (cell, language, path) to reduce parameter count.
    Follows "Introduce Parameter Object" refactoring pattern (Fowler).
    """

    def __init__(self, cell, language: str, path: str):
        """Initialize with cell context

        Args:
            cell: Notebook cell object
            language: Programming language
            path: File path for metadata
        """
        self.cell = cell
        self.language = language
        self.path = path

    def build_enriched_chunk(self, chunk: Dict) -> Dict:
        """Build a single enriched chunk with cell metadata

        Args:
            chunk: Base chunk from chunker

        Returns:
            Enriched chunk dictionary
        """
        return {
            'content': chunk['content'],
            'type': 'code',
            'language': self.language,
            'cell_number': getattr(self.cell, 'cell_number', 0),
            'cell_type': 'code',
            'execution_count': getattr(self.cell, 'execution_count', None),
            'has_output': len(getattr(self.cell, 'outputs', [])) > 0,
            'outputs': getattr(self.cell, 'outputs', []),
            'metadata': chunk.get('metadata', {}),
            'filepath': self.path,
        }
