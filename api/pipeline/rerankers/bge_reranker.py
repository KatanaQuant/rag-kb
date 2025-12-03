"""BGE Reranker implementation using CrossEncoder.

Uses BAAI/bge-reranker-large (560MB) for CPU-viable reranking.
Expected improvement: +20-30% retrieval quality.
"""

import logging
import time
from typing import List, Optional

from pipeline.interfaces.reranker import RerankerInterface

logger = logging.getLogger(__name__)


class BGEReranker(RerankerInterface):
    """BGE CrossEncoder reranker for search result reranking.

    Lazy-loads the model on first use to avoid startup latency.
    Thread-safe for concurrent query execution.
    """

    DEFAULT_MODEL = "BAAI/bge-reranker-large"

    def __init__(self, model_name: Optional[str] = None, enable_timing: bool = False):
        """Initialize BGE reranker.

        Args:
            model_name: CrossEncoder model name (default: bge-reranker-large)
            enable_timing: If True, log reranking timing diagnostics
        """
        self._model_name = model_name or self.DEFAULT_MODEL
        self._model = None
        self._enable_timing = enable_timing

    def _load_model(self):
        """Lazy-load the CrossEncoder model."""
        if self._model is None:
            from sentence_transformers import CrossEncoder

            logger.info(f"Loading reranker model: {self._model_name}")
            start = time.perf_counter()
            self._model = CrossEncoder(self._model_name)
            elapsed = time.perf_counter() - start
            logger.info(f"Reranker model loaded in {elapsed:.2f}s")

    def rerank(
        self,
        query: str,
        candidates: List[dict],
        top_k: int
    ) -> List[dict]:
        """Rerank candidates by relevance to query.

        Args:
            query: The search query text
            candidates: List of candidate dicts (must have 'content' key)
            top_k: Maximum number of results to return

        Returns:
            Top-k candidates sorted by reranker score (best first)
        """
        if not candidates:
            return []

        if len(candidates) <= 1:
            return candidates[:top_k]

        self._load_model()

        start = time.perf_counter()

        # Build query-document pairs for scoring
        pairs = [(query, c.get("content", "")) for c in candidates]

        # Score all pairs
        scores = self._model.predict(pairs, show_progress_bar=False)

        # Attach scores and sort
        scored = list(zip(candidates, scores))
        scored.sort(key=lambda x: x[1], reverse=True)

        # Take top_k and add rerank_score to each result
        results = []
        for candidate, score in scored[:top_k]:
            result = dict(candidate)
            result["rerank_score"] = float(score)
            results.append(result)

        if self._enable_timing:
            elapsed = time.perf_counter() - start
            logger.info(
                f"Reranked {len(candidates)} candidates to top {top_k} in {elapsed:.3f}s"
            )

        return results

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def is_enabled(self) -> bool:
        return True
