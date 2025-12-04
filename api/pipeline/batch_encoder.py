"""Batch encoder for efficient embedding generation.

Principles:
- Single Responsibility: Only handles batch encoding logic
- Small class: Under 100 lines
- Dependency Injection: Model injected via constructor

Performance improvement: Encodes multiple texts per model.encode() call
instead of one-at-a-time, reducing forward pass overhead by 10-50x.
"""

import math
import time
from typing import List, Callable, Optional


class BatchEncoder:
    """Encodes texts in batches for efficient embedding generation.

    Uses batch encoding to reduce model forward pass overhead.
    sentence-transformers is optimized for batch operations - encoding
    32 texts at once is much faster than 32 individual encode calls.
    """

    def __init__(self, model, batch_size: int = 32, enable_timing: bool = False):
        """Initialize with embedding model.

        Args:
            model: SentenceTransformer model (or compatible)
            batch_size: Number of texts per batch (default 32, optimal for CPU)
            enable_timing: If True, print per-batch timing diagnostics
        """
        self.model = model
        self.batch_size = batch_size
        self.enable_timing = enable_timing

    def encode(
        self,
        texts: List[str],
        on_progress: Optional[Callable[[int, int, int, int], None]] = None
    ) -> List[List[float]]:
        """Encode texts in batches.

        Args:
            texts: List of texts to encode
            on_progress: Optional callback(batch_num, total_batches, items_done, total_items)

        Returns:
            List of embeddings (each is a list of floats)
        """
        if not texts:
            return []

        total_batches = math.ceil(len(texts) / self.batch_size)
        result = []

        for batch_num in range(total_batches):
            start_idx = batch_num * self.batch_size
            end_idx = min(start_idx + self.batch_size, len(texts))
            batch_texts = texts[start_idx:end_idx]

            batch_embeddings = self._encode_batch(batch_texts)
            result.extend(batch_embeddings)

            if on_progress:
                items_done = end_idx
                on_progress(batch_num + 1, total_batches, items_done, len(texts))

        return result

    def _encode_batch(self, texts: List[str]) -> List[List[float]]:
        """Encode a single batch of texts.

        Args:
            texts: Batch of texts to encode

        Returns:
            List of embeddings for this batch
        """
        start_time = time.perf_counter()
        embeddings = self.model.encode(
            texts,
            show_progress_bar=False,
            convert_to_numpy=True
        )
        if self.enable_timing:
            elapsed = time.perf_counter() - start_time
            texts_per_sec = len(texts) / elapsed if elapsed > 0 else 0
            print(f"    [BatchEncoder] {len(texts)} texts in {elapsed:.3f}s ({texts_per_sec:.1f} texts/sec)")
        return [emb.tolist() for emb in embeddings]
