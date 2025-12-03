"""Embedder interface for text embedding generation.

Defines the contract for embedding providers (SentenceTransformers, OpenAI, etc.).
"""

from abc import ABC, abstractmethod
from typing import List, Callable, Optional


class EmbedderInterface(ABC):
    """Interface for text embedding implementations.

    Contract (Liskov Substitution):
        - embed() must return List[List[float]]
        - Each inner list has length == dimension
        - Empty input returns empty list
        - Must not raise exceptions (return empty on error)
    """

    @abstractmethod
    def embed(
        self,
        texts: List[str],
        on_progress: Optional[Callable[[int, int, int, int], None]] = None
    ) -> List[List[float]]:
        """Generate embeddings for a list of texts.

        Args:
            texts: List of texts to embed
            on_progress: Optional callback(batch_num, total_batches, items_done, total_items)

        Returns:
            List of embeddings (each is a list of floats with length == dimension)
        """
        pass

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Embedding vector dimension."""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Name/identifier of the embedding model."""
        pass
