"""Integration tests for reranking functionality.

Tests BGEReranker behavior by mocking CrossEncoder to avoid
loading the actual 560MB model in CI/tests.
"""

import pytest
from unittest.mock import MagicMock, patch

from pipeline.rerankers.bge_reranker import BGEReranker
from pipeline.interfaces.reranker import NoopReranker


class TestBGERerankerBehavior:
    """Test BGEReranker behavior (without loading actual model)."""

    def test_reranker_adds_rerank_score(self):
        """BGEReranker must add rerank_score to results."""
        with patch.object(BGEReranker, '_load_model') as mock_load:
            reranker = BGEReranker()
            reranker._model = MagicMock()
            reranker._model.predict.return_value = [0.9, 0.5, 0.7]

            candidates = [
                {"content": "first", "source": "a.pdf"},
                {"content": "second", "source": "b.pdf"},
                {"content": "third", "source": "c.pdf"},
            ]
            result = reranker.rerank("query", candidates, top_k=3)

            assert all("rerank_score" in r for r in result)

    def test_reranker_sorts_by_score_descending(self):
        """BGEReranker must return results sorted by score (best first)."""
        with patch.object(BGEReranker, '_load_model'):
            reranker = BGEReranker()
            reranker._model = MagicMock()
            reranker._model.predict.return_value = [0.3, 0.9, 0.6]  # second is best

            candidates = [
                {"content": "first"},
                {"content": "second"},
                {"content": "third"},
            ]
            result = reranker.rerank("query", candidates, top_k=3)

            assert result[0]["content"] == "second"  # highest score
            assert result[1]["content"] == "third"
            assert result[2]["content"] == "first"   # lowest score

    def test_reranker_respects_top_k(self):
        """BGEReranker must return at most top_k results."""
        with patch.object(BGEReranker, '_load_model'):
            reranker = BGEReranker()
            reranker._model = MagicMock()
            reranker._model.predict.return_value = [0.5] * 10

            candidates = [{"content": f"item {i}"} for i in range(10)]
            result = reranker.rerank("query", candidates, top_k=3)

            assert len(result) == 3

    def test_reranker_preserves_metadata(self):
        """BGEReranker must preserve all candidate metadata."""
        with patch.object(BGEReranker, '_load_model'):
            reranker = BGEReranker()
            reranker._model = MagicMock()
            reranker._model.predict.return_value = [0.9]

            candidates = [
                {"content": "text", "source": "doc.pdf", "page": 5, "custom_field": "value"}
            ]
            result = reranker.rerank("query", candidates, top_k=1)

            assert result[0]["source"] == "doc.pdf"
            assert result[0]["page"] == 5
            assert result[0]["custom_field"] == "value"

    def test_reranker_handles_empty_candidates(self):
        """BGEReranker must return empty list for empty input."""
        reranker = BGEReranker()
        result = reranker.rerank("query", [], top_k=5)
        assert result == []

    def test_reranker_handles_single_candidate(self):
        """BGEReranker must handle single candidate without model call."""
        reranker = BGEReranker()
        candidates = [{"content": "only one"}]
        result = reranker.rerank("query", candidates, top_k=5)
        assert len(result) == 1
        assert result[0]["content"] == "only one"

    def test_reranker_model_name_property(self):
        """BGEReranker.model_name must return configured model."""
        reranker = BGEReranker(model_name="custom/model")
        assert reranker.model_name == "custom/model"

    def test_reranker_default_model(self):
        """BGEReranker must use default model when none specified."""
        reranker = BGEReranker()
        assert reranker.model_name == "BAAI/bge-reranker-large"

    def test_reranker_is_enabled(self):
        """BGEReranker.is_enabled must return True."""
        reranker = BGEReranker()
        assert reranker.is_enabled is True


class TestNoopRerankerBehavior:
    """Test NoopReranker passthrough behavior."""

    def test_noop_passes_through_unchanged(self):
        """NoopReranker must return candidates unchanged (except top_k slice)."""
        reranker = NoopReranker()
        candidates = [
            {"content": "a", "score": 0.9},
            {"content": "b", "score": 0.8},
            {"content": "c", "score": 0.7},
        ]
        result = reranker.rerank("query", candidates, top_k=10)

        # Order preserved, no rerank_score added
        assert len(result) == 3
        assert result[0]["content"] == "a"
        assert result[1]["content"] == "b"
        assert result[2]["content"] == "c"
        assert "rerank_score" not in result[0]

    def test_noop_is_disabled(self):
        """NoopReranker.is_enabled must return False."""
        reranker = NoopReranker()
        assert reranker.is_enabled is False

    def test_noop_model_name(self):
        """NoopReranker.model_name must return 'noop'."""
        reranker = NoopReranker()
        assert reranker.model_name == "noop"
