"""SentenceTransformer embedder adapter.

Wraps the existing BatchEncoder to implement EmbedderInterface.
Adapter pattern: existing code, new interface.
"""

from typing import List, Callable, Optional

from pipeline.interfaces.embedder import EmbedderInterface
from pipeline.batch_encoder import BatchEncoder


class SentenceTransformerEmbedder(EmbedderInterface):
    """Embedder implementation using SentenceTransformers.

    Wraps BatchEncoder to provide interface compliance.
    """

    def __init__(
        self,
        model,
        batch_size: int = 32,
        enable_timing: bool = False
    ):
        """Initialize with SentenceTransformer model.

        Args:
            model: SentenceTransformer model instance
            batch_size: Number of texts per batch (default 32)
            enable_timing: If True, print per-batch timing diagnostics
        """
        self._model = model
        self._batch_encoder = BatchEncoder(
            model=model,
            batch_size=batch_size,
            enable_timing=enable_timing
        )

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
            List of embeddings (each is a list of floats)
        """
        return self._batch_encoder.encode(texts, on_progress=on_progress)

    @property
    def dimension(self) -> int:
        """Embedding vector dimension."""
        return self._model.get_sentence_embedding_dimension()

    @property
    def model_name(self) -> str:
        """Name/identifier of the embedding model."""
        # SentenceTransformer models have a _name_or_path attribute
        return getattr(self._model, '_name_or_path', 'unknown')
