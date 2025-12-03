"""Interface compliance tests for pipeline components.

Tests that all implementations adhere to their interface contracts.
Following Beck TDD: write tests first, then implementations.
"""

import pytest
from pathlib import Path
from typing import List, Dict

from pipeline.interfaces import (
    ExtractorInterface,
    ChunkerInterface,
    EmbedderInterface,
    RerankerInterface,
    NoopReranker,
)
from domain_models import ExtractionResult


class TestRerankerInterface:
    """Test RerankerInterface contract compliance."""

    def test_noop_reranker_returns_list(self):
        """NoopReranker.rerank() must return List[dict]."""
        reranker = NoopReranker()
        candidates = [
            {"content": "first", "score": 0.9},
            {"content": "second", "score": 0.8},
        ]
        result = reranker.rerank("query", candidates, top_k=5)
        assert isinstance(result, list)
        assert all(isinstance(item, dict) for item in result)

    def test_noop_reranker_respects_top_k(self):
        """NoopReranker must return at most top_k results."""
        reranker = NoopReranker()
        candidates = [
            {"content": f"item {i}", "score": 0.9 - i * 0.1}
            for i in range(10)
        ]
        result = reranker.rerank("query", candidates, top_k=3)
        assert len(result) == 3

    def test_noop_reranker_preserves_candidates(self):
        """NoopReranker must preserve original candidate dicts."""
        reranker = NoopReranker()
        candidates = [
            {"content": "text", "score": 0.9, "source": "doc.pdf", "page": 1},
        ]
        result = reranker.rerank("query", candidates, top_k=5)
        assert result[0] == candidates[0]

    def test_noop_reranker_model_name(self):
        """NoopReranker.model_name must return string."""
        reranker = NoopReranker()
        assert isinstance(reranker.model_name, str)
        assert reranker.model_name == "noop"

    def test_noop_reranker_is_disabled(self):
        """NoopReranker.is_enabled must return False."""
        reranker = NoopReranker()
        assert reranker.is_enabled is False

    def test_noop_reranker_empty_candidates(self):
        """NoopReranker must handle empty candidate list."""
        reranker = NoopReranker()
        result = reranker.rerank("query", [], top_k=5)
        assert result == []

    def test_noop_reranker_top_k_larger_than_candidates(self):
        """NoopReranker must handle top_k > len(candidates)."""
        reranker = NoopReranker()
        candidates = [{"content": "only one"}]
        result = reranker.rerank("query", candidates, top_k=10)
        assert len(result) == 1


class TestEmbedderInterfaceContract:
    """Test EmbedderInterface contract requirements."""

    def test_embedder_interface_has_embed_method(self):
        """EmbedderInterface must define embed method."""
        assert hasattr(EmbedderInterface, 'embed')

    def test_embedder_interface_has_dimension_property(self):
        """EmbedderInterface must define dimension property."""
        assert hasattr(EmbedderInterface, 'dimension')

    def test_embedder_interface_has_model_name_property(self):
        """EmbedderInterface must define model_name property."""
        assert hasattr(EmbedderInterface, 'model_name')

    def test_embedder_interface_is_abstract(self):
        """EmbedderInterface must be abstract (cannot instantiate)."""
        with pytest.raises(TypeError):
            EmbedderInterface()


class TestChunkerInterfaceContract:
    """Test ChunkerInterface contract requirements."""

    def test_chunker_interface_has_chunkify_method(self):
        """ChunkerInterface must define chunkify method."""
        assert hasattr(ChunkerInterface, 'chunkify')

    def test_chunker_interface_has_name_property(self):
        """ChunkerInterface must define name property."""
        assert hasattr(ChunkerInterface, 'name')

    def test_chunker_interface_is_abstract(self):
        """ChunkerInterface must be abstract (cannot instantiate)."""
        with pytest.raises(TypeError):
            ChunkerInterface()


class TestExtractorInterfaceContract:
    """Test ExtractorInterface contract requirements."""

    def test_extractor_interface_has_extract_method(self):
        """ExtractorInterface must define extract method."""
        assert hasattr(ExtractorInterface, 'extract')

    def test_extractor_interface_has_name_property(self):
        """ExtractorInterface must define name property."""
        assert hasattr(ExtractorInterface, 'name')

    def test_extractor_interface_has_supports_classmethod(self):
        """ExtractorInterface must define supports classmethod."""
        assert hasattr(ExtractorInterface, 'supports')

    def test_extractor_interface_has_supported_extensions(self):
        """ExtractorInterface must define SUPPORTED_EXTENSIONS."""
        assert hasattr(ExtractorInterface, 'SUPPORTED_EXTENSIONS')

    def test_extractor_interface_is_abstract(self):
        """ExtractorInterface must be abstract (cannot instantiate)."""
        with pytest.raises(TypeError):
            ExtractorInterface()


class TestExtractorSupportsMethod:
    """Test ExtractorInterface.supports() classmethod."""

    def test_supports_with_dot_prefix(self):
        """supports() must handle extensions with leading dot."""
        # Create a concrete subclass for testing
        class TestExtractor(ExtractorInterface):
            SUPPORTED_EXTENSIONS = {'.pdf', '.docx'}

            def extract(self, path: Path) -> ExtractionResult:
                return ExtractionResult(pages=[], method="test")

            @property
            def name(self) -> str:
                return "test"

        assert TestExtractor.supports('.pdf') is True
        assert TestExtractor.supports('.docx') is True
        assert TestExtractor.supports('.txt') is False

    def test_supports_without_dot_prefix(self):
        """supports() must handle extensions without leading dot."""
        class TestExtractor(ExtractorInterface):
            SUPPORTED_EXTENSIONS = {'.pdf'}

            def extract(self, path: Path) -> ExtractionResult:
                return ExtractionResult(pages=[], method="test")

            @property
            def name(self) -> str:
                return "test"

        assert TestExtractor.supports('pdf') is True
        assert TestExtractor.supports('PDF') is True  # Case insensitive

    def test_supports_case_insensitive(self):
        """supports() must be case-insensitive."""
        class TestExtractor(ExtractorInterface):
            SUPPORTED_EXTENSIONS = {'.pdf'}

            def extract(self, path: Path) -> ExtractionResult:
                return ExtractionResult(pages=[], method="test")

            @property
            def name(self) -> str:
                return "test"

        assert TestExtractor.supports('.PDF') is True
        assert TestExtractor.supports('.Pdf') is True


class TestRerankerInterfaceContract:
    """Test RerankerInterface contract requirements."""

    def test_reranker_interface_has_rerank_method(self):
        """RerankerInterface must define rerank method."""
        assert hasattr(RerankerInterface, 'rerank')

    def test_reranker_interface_has_model_name_property(self):
        """RerankerInterface must define model_name property."""
        assert hasattr(RerankerInterface, 'model_name')

    def test_reranker_interface_has_is_enabled_property(self):
        """RerankerInterface must define is_enabled property."""
        assert hasattr(RerankerInterface, 'is_enabled')

    def test_reranker_interface_is_enabled_default_true(self):
        """RerankerInterface.is_enabled must default to True."""
        # Create minimal concrete class
        class TestReranker(RerankerInterface):
            def rerank(self, query, candidates, top_k):
                return candidates[:top_k]

            @property
            def model_name(self):
                return "test"

        reranker = TestReranker()
        assert reranker.is_enabled is True
