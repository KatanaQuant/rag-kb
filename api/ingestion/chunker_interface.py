"""Chunker interface for code chunking implementations"""

from abc import ABC, abstractmethod
from typing import List, Dict

class ChunkerInterface(ABC):
    """Interface for code chunkers"""
    

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
