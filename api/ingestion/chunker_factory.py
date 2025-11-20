

from typing import Dict, List
from ingestion.chunker_interface import ChunkerInterface

class PythonChunker(ChunkerInterface):
    """Python code chunker using AST-based chunking

    Wraps external ASTChunkBuilder library
    """

    def __init__(self, max_chunk_size: int = 2048):
        self.max_chunk_size = max_chunk_size

    def chunkify(self, source: str, **kwargs) -> List[Dict]:
        """Chunk Python code using AST analysis"""
        try:
            from astchunk import ASTChunkBuilder

            chunker = ASTChunkBuilder(
                max_chunk_size=self.max_chunk_size,
                language='python',
                metadata_template='default'
            )

            ast_chunks = chunker.chunkify(source)

            # Convert astchunk format to our format
            return [
                {
                    'content': chunk.content,
                    'metadata': chunk.metadata if hasattr(chunk, 'metadata') else {}
                }
                for chunk in ast_chunks
            ]
        except Exception as e:
            # Fallback: return whole source as single chunk
            return [{
                'content': source,
                'metadata': {'error': str(e), 'chunking': 'fallback'}
            }]

class RChunker(ChunkerInterface):
    """R code chunker using TreeSitter-based chunking

    Wraps external TreeSitterChunker library
    """

    def __init__(self, max_chunk_size: int = 2048):
        self.max_chunk_size = max_chunk_size

    def chunkify(self, source: str, **kwargs) -> List[Dict]:
        """Chunk R code using TreeSitter analysis"""
        try:
            from ingestion.tree_sitter_chunker import TreeSitterChunker

            chunker = TreeSitterChunker(
                language='r',
                max_chunk_size=self.max_chunk_size,
                metadata_template='default'
            )

            filepath = kwargs.get('filepath', '')
            return chunker.chunkify(source, filepath=filepath)

        except Exception as e:
            # Fallback: return whole source
            return [{
                'content': source,
                'metadata': {'error': str(e), 'chunking': 'fallback'}
            }]

class CellLevelChunker(ChunkerInterface):
    """Default chunker: Keep entire cell as one chunk

    Used for:
    - Small cells (<2048 chars)
    - Languages without AST support
    - Fallback when other chunkers fail
    """

    def chunkify(self, source: str, **kwargs) -> List[Dict]:
        """Return source as single chunk"""
        if not source or not source.strip():
            return []

        return [{
            'content': source,
            'metadata': {'chunking': 'cell_level'}
        }]

class ChunkerFactory:
    

    def __init__(self, max_chunk_size: int = 2048):
        self.max_chunk_size = max_chunk_size

    def create_chunker(self, language: str, cell_size: int) -> ChunkerInterface:
        """Create appropriate chunker for language and size

        Args:
            language: Programming language ('python', 'r', etc.)
            cell_size: Size of code to chunk (bytes)

        Returns:
            ChunkerInterface implementation

        Strategy:
            - Large Python (>2048): Use ASTChunkBuilder (fast, well-tested)
            - Large R (>2048): Use TreeSitterChunker (AST-based)
            - Small or other: Use CellLevelChunker (preserve execution semantics)
        """
        language = language.lower()

        if language == 'python' and cell_size > self.max_chunk_size:
            return PythonChunker(self.max_chunk_size)

        elif language == 'r' and cell_size > self.max_chunk_size:
            return RChunker(self.max_chunk_size)

        else:
            # Default: cell-level chunking
            return CellLevelChunker()

    def supports_ast_chunking(self, language: str) -> bool:
        """Check if language supports AST-based chunking"""
        return language.lower() in ['python', 'r']
