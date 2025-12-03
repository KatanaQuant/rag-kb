"""Chunker interface for text chunking strategies.

Enhanced from api/ingestion/chunker_interface.py with name property.
"""

from abc import ABC, abstractmethod
from typing import List, Dict


class ChunkerInterface(ABC):
    """Interface for text chunking implementations.

    Contract (Liskov Substitution):
        - chunkify() must return List[Dict]
        - Each dict must have 'content' key (str)
        - May have 'metadata' key (dict)
        - Must not raise exceptions (return empty list on error)
    """

    @abstractmethod
    def chunkify(self, source: str, **kwargs) -> List[Dict]:
        """Chunk source text into semantic units.

        Args:
            source: Source text to chunk
            **kwargs: Implementation-specific options (filepath, language, etc.)

        Returns:
            List of chunk dictionaries with 'content' and optional 'metadata'
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of this chunker."""
        pass
