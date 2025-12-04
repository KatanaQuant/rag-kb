"""
Tests for agentic query enhancements.

Phase 1: Confidence Scores (rerank_score exposure)
Phase 2: Follow-up Suggestions
Phase 3: Query Decomposition
"""

import pytest
import numpy as np
from unittest.mock import Mock, AsyncMock
from models import QueryRequest, QueryResponse, SearchResult
from operations.query_executor import QueryExecutor


class TestConfidenceScores:
    """Phase 1: Expose reranker scores in API response"""

    @pytest.mark.asyncio
    async def test_rerank_score_exposed_when_reranking_enabled(self):
        """Reranker score should be exposed when reranking is enabled"""
        # Given: a mock reranker that adds rerank_score
        mock_model = Mock()
        mock_model.encode.return_value = np.array([0.1] * 384)

        mock_store = AsyncMock()
        mock_store.search.return_value = [
            {"content": "test content", "source": "test.md", "page": 1, "score": 0.8}
        ]

        mock_reranker = Mock()
        mock_reranker.is_enabled = True
        mock_reranker.top_n = 20
        mock_reranker.rerank.return_value = [
            {
                "content": "test content",
                "source": "test.md",
                "page": 1,
                "score": 0.8,
                "rerank_score": 0.92,  # Added by reranker
            }
        ]

        executor = QueryExecutor(mock_model, mock_store, None, mock_reranker)

        # When: query executed
        request = QueryRequest(text="test query", top_k=5)
        response = await executor.execute(request)

        # Then: results have rerank_score field
        assert len(response.results) == 1
        assert response.results[0].rerank_score == 0.92

    @pytest.mark.asyncio
    async def test_rerank_score_none_when_reranking_disabled(self):
        """Rerank score should be None when reranking is not applied"""
        # Given: no reranker
        mock_model = Mock()
        mock_model.encode.return_value = np.array([0.1] * 384)

        mock_store = AsyncMock()
        mock_store.search.return_value = [
            {"content": "test content", "source": "test.md", "page": 1, "score": 0.8}
        ]

        executor = QueryExecutor(mock_model, mock_store, None, None)

        # When: query executed without reranker
        request = QueryRequest(text="test query", top_k=5)
        response = await executor.execute(request)

        # Then: rerank_score should be None
        assert len(response.results) == 1
        assert response.results[0].rerank_score is None


class TestFollowUpSuggestions:
    """Phase 2: Return related queries with results"""

    @pytest.mark.asyncio
    async def test_suggestions_returned_with_results(self):
        """Suggestions should be returned based on result content"""
        # Given: results with meaningful content
        mock_model = Mock()
        mock_model.encode.return_value = np.array([0.1] * 384)

        mock_store = AsyncMock()
        mock_store.search.return_value = [
            {
                "content": "Position sizing determines how much capital to risk per trade. "
                "The Kelly criterion is a popular method for optimal position sizing.",
                "source": "trading.md",
                "page": 1,
                "score": 0.85,
            },
            {
                "content": "Risk management includes stop losses and position limits.",
                "source": "risk.md",
                "page": 1,
                "score": 0.75,
            },
        ]

        executor = QueryExecutor(mock_model, mock_store, None, None)

        # When: query executed
        request = QueryRequest(text="position sizing", top_k=5)
        response = await executor.execute(request)

        # Then: suggestions list is present (always, even if empty)
        assert hasattr(response, "suggestions")
        assert isinstance(response.suggestions, list)

    @pytest.mark.asyncio
    async def test_suggestions_empty_when_no_results(self):
        """Suggestions should be empty list when no results"""
        # Given: no results
        mock_model = Mock()
        mock_model.encode.return_value = np.array([0.1] * 384)

        mock_store = AsyncMock()
        mock_store.search.return_value = []

        executor = QueryExecutor(mock_model, mock_store, None, None)

        # When: query returns no results
        request = QueryRequest(text="nonexistent topic", top_k=5)
        response = await executor.execute(request)

        # Then: suggestions is empty list (not None)
        assert response.suggestions == []


class TestQueryDecomposition:
    """Phase 3: Break complex queries into sub-queries"""

    @pytest.mark.asyncio
    async def test_decomposition_metadata_always_present(self):
        """Decomposition info should always be present in response"""
        # Given: simple query
        mock_model = Mock()
        mock_model.encode.return_value = np.array([0.1] * 384)

        mock_store = AsyncMock()
        mock_store.search.return_value = [
            {"content": "test content", "source": "test.md", "page": 1, "score": 0.8}
        ]

        executor = QueryExecutor(mock_model, mock_store, None, None)

        # When: query executed
        request = QueryRequest(text="simple query", top_k=5)
        response = await executor.execute(request)

        # Then: decomposition metadata is present
        assert hasattr(response, "decomposition")
        assert response.decomposition is not None
        assert hasattr(response.decomposition, "applied")
        assert hasattr(response.decomposition, "sub_queries")

    @pytest.mark.asyncio
    async def test_simple_query_not_decomposed(self):
        """Simple queries should not be decomposed"""
        # Given: simple non-compound query
        mock_model = Mock()
        mock_model.encode.return_value = np.array([0.1] * 384)

        mock_store = AsyncMock()
        mock_store.search.return_value = [
            {"content": "test content", "source": "test.md", "page": 1, "score": 0.8}
        ]

        executor = QueryExecutor(mock_model, mock_store, None, None)

        # When: simple query executed
        request = QueryRequest(text="what is position sizing", top_k=5)
        response = await executor.execute(request)

        # Then: not decomposed
        assert response.decomposition.applied is False
        assert response.decomposition.sub_queries == []

    @pytest.mark.asyncio
    async def test_compound_query_decomposed_by_default(self):
        """Compound queries should be auto-decomposed by default"""
        # Given: compound query with "and"
        mock_model = Mock()
        mock_model.encode.return_value = np.array([0.1] * 384)

        mock_store = AsyncMock()
        mock_store.search.return_value = [
            {"content": "test content", "source": "test.md", "page": 1, "score": 0.8}
        ]

        executor = QueryExecutor(mock_model, mock_store, None, None)

        # When: compound query executed
        request = QueryRequest(text="what is position sizing and how does it affect risk", top_k=5)
        response = await executor.execute(request)

        # Then: decomposed into sub-queries
        assert response.decomposition.applied is True
        assert len(response.decomposition.sub_queries) >= 2

    @pytest.mark.asyncio
    async def test_decomposition_disabled_with_param(self):
        """decompose=False should prevent decomposition"""
        # Given: compound query but decompose=False
        mock_model = Mock()
        mock_model.encode.return_value = np.array([0.1] * 384)

        mock_store = AsyncMock()
        mock_store.search.return_value = [
            {"content": "test content", "source": "test.md", "page": 1, "score": 0.8}
        ]

        executor = QueryExecutor(mock_model, mock_store, None, None)

        # When: query with decompose=False
        request = QueryRequest(
            text="what is position sizing and how does it affect risk",
            top_k=5,
            decompose=False
        )
        response = await executor.execute(request)

        # Then: not decomposed despite compound query
        assert response.decomposition.applied is False
