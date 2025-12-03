"""Reranker interface for search result reranking.

Defines the contract for reranking implementations (BGE, Cohere, etc.).
"""

from abc import ABC, abstractmethod
from typing import List


class RerankerInterface(ABC):
    """Interface for search result rerankers.

    Contract (Liskov Substitution):
        - rerank() must return List[dict] with same structure as input
        - Results must be sorted by relevance (best first)
        - len(result) <= top_k
        - Original candidate dicts are preserved (may add 'rerank_score')
    """

    @abstractmethod
    def rerank(
        self,
        query: str,
        candidates: List[dict],
        top_k: int
    ) -> List[dict]:
        """Rerank search candidates by relevance to query.

        Args:
            query: The search query text
            candidates: List of candidate dicts (must have 'content' key)
            top_k: Maximum number of results to return

        Returns:
            Top-k candidates sorted by relevance (best first)
        """
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Name/identifier of the reranking model."""
        pass

    @property
    def is_enabled(self) -> bool:
        """Whether reranking is enabled (default True)."""
        return True


class NoopReranker(RerankerInterface):
    """Pass-through reranker that returns candidates unchanged.

    Use when reranking is disabled but interface compliance is needed.
    """

    def rerank(
        self,
        query: str,
        candidates: List[dict],
        top_k: int
    ) -> List[dict]:
        """Return top_k candidates without reranking."""
        return candidates[:top_k]

    @property
    def model_name(self) -> str:
        return "noop"

    @property
    def is_enabled(self) -> bool:
        return False
