"""Chunker interface for dependency injection (POODR compliance)

From POODR Chapter 3: "Depend on things that change less often than you do"

This interface is an abstraction - more stable than concrete implementations.
Concrete chunkers (ASTChunkBuilder, TreeSitterChunker) can change without
affecting code that depends on this interface.

Usage:
    class JupyterExtractor:
        def __init__(self, chunker_factory: ChunkerFactory):
            self.chunker_factory = chunker_factory  # Injected!

        def _chunk_code_cell(self, cell, language, filepath):
            chunker = self.chunker_factory.create_chunker(language, len(cell.source))
            return chunker.chunkify(cell.source)
"""

from abc import ABC, abstractmethod
from typing import List, Dict


class ChunkerInterface(ABC):
    """Abstract interface for all code chunkers

    POODR Principle: Depend on abstractions, not concretions
    Liskov Substitution: All chunkers must be interchangeable
    """

    @abstractmethod
    def chunkify(self, source: str, **kwargs) -> List[Dict]:
        """Chunk source code into semantic units

        Args:
            source: Source code to chunk
            **kwargs: Implementation-specific options (filepath, etc.)

        Returns:
            List of chunk dictionaries with 'content' and optional 'metadata'

        Contract (Liskov):
            - Must return list of dicts
            - Each dict must have 'content' key (str)
            - May have 'metadata' key (dict)
            - Must not raise exceptions (return empty list on error)
        """
        pass
