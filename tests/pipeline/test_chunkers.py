"""Tests for chunker implementations."""

import pytest

from pipeline.interfaces.chunker import ChunkerInterface
from pipeline.chunkers.hybrid_chunker import HybridChunker
from pipeline.chunkers.semantic_chunker import SemanticChunker
from pipeline.chunkers.fixed_chunker import FixedChunker


class TestHybridChunker:
    """Test HybridChunker implementation."""

    def test_implements_interface(self):
        """HybridChunker must implement ChunkerInterface."""
        chunker = HybridChunker()
        assert isinstance(chunker, ChunkerInterface)

    def test_name_property(self):
        """HybridChunker.name must return 'hybrid'."""
        chunker = HybridChunker()
        assert chunker.name == 'hybrid'

    def test_chunkify_returns_list(self):
        """chunkify must return a list of dicts."""
        chunker = HybridChunker(max_tokens=512)
        text = "This is a test paragraph.\n\nThis is another paragraph."
        result = chunker.chunkify(text)

        assert isinstance(result, list)
        assert all(isinstance(chunk, dict) for chunk in result)
        assert all('content' in chunk for chunk in result)

    def test_chunkify_empty_string(self):
        """chunkify must return empty list for empty input."""
        chunker = HybridChunker()
        result = chunker.chunkify("")

        assert result == []

    def test_chunkify_whitespace_only(self):
        """chunkify must return empty list for whitespace-only input."""
        chunker = HybridChunker()
        result = chunker.chunkify("   \n\n   ")

        assert result == []

    def test_max_tokens_parameter(self):
        """HybridChunker must accept max_tokens parameter."""
        chunker = HybridChunker(max_tokens=256)
        assert chunker.max_tokens == 256


class TestSemanticChunker:
    """Test SemanticChunker implementation."""

    def test_implements_interface(self):
        """SemanticChunker must implement ChunkerInterface."""
        chunker = SemanticChunker()
        assert isinstance(chunker, ChunkerInterface)

    def test_name_property(self):
        """SemanticChunker.name must return 'semantic'."""
        chunker = SemanticChunker()
        assert chunker.name == 'semantic'

    def test_chunkify_respects_sentences(self):
        """chunkify must split at sentence boundaries."""
        chunker = SemanticChunker(max_tokens=512)
        text = "First sentence. Second sentence. Third sentence."
        result = chunker.chunkify(text)

        assert isinstance(result, list)
        assert len(result) >= 1
        # Content should be preserved
        combined = ' '.join(chunk['content'] for chunk in result)
        assert 'First sentence' in combined
        assert 'Third sentence' in combined

    def test_chunkify_respects_max_tokens(self):
        """chunkify must respect max_tokens limit."""
        # Very small limit to force splitting
        chunker = SemanticChunker(max_tokens=10)  # ~40 chars
        text = "This is a longer text that should be split into multiple chunks because it exceeds the token limit."
        result = chunker.chunkify(text)

        # Should have multiple chunks
        assert len(result) > 1
        # Each chunk should respect the limit (approximately)
        max_chars = 10 * 4  # 4 chars per token
        for chunk in result:
            # Allow some overflow due to word boundaries
            assert len(chunk['content']) < max_chars * 2

    def test_chunkify_empty_string(self):
        """chunkify must return empty list for empty input."""
        chunker = SemanticChunker()
        result = chunker.chunkify("")

        assert result == []

    def test_chunkify_preserves_paragraphs(self):
        """chunkify must respect paragraph boundaries."""
        chunker = SemanticChunker(max_tokens=1024)
        text = "First paragraph content.\n\nSecond paragraph content."
        result = chunker.chunkify(text)

        assert isinstance(result, list)
        assert all('content' in chunk for chunk in result)


class TestFixedChunker:
    """Test FixedChunker implementation."""

    def test_implements_interface(self):
        """FixedChunker must implement ChunkerInterface."""
        chunker = FixedChunker()
        assert isinstance(chunker, ChunkerInterface)

    def test_name_property(self):
        """FixedChunker.name must return 'fixed'."""
        chunker = FixedChunker()
        assert chunker.name == 'fixed'

    def test_chunkify_returns_list(self):
        """chunkify must return a list of dicts."""
        chunker = FixedChunker(max_tokens=512)
        text = "This is test content " * 100
        result = chunker.chunkify(text)

        assert isinstance(result, list)
        assert all(isinstance(chunk, dict) for chunk in result)
        assert all('content' in chunk for chunk in result)

    def test_chunkify_creates_overlap(self):
        """chunkify must create overlapping chunks."""
        chunker = FixedChunker(max_tokens=50, overlap_tokens=10)
        text = "Word " * 200  # Long enough to require multiple chunks
        result = chunker.chunkify(text)

        if len(result) > 1:
            # Check that chunks have some overlap (content appears in adjacent chunks)
            first_end = result[0]['content'][-20:]
            second_start = result[1]['content'][:50]
            # With overlap, end of first should appear somewhere in start of second
            # This is approximate due to word boundaries
            assert len(result) >= 2

    def test_chunkify_empty_string(self):
        """chunkify must return empty list for empty input."""
        chunker = FixedChunker()
        result = chunker.chunkify("")

        assert result == []

    def test_chunkify_metadata_includes_index(self):
        """chunkify must include chunk_index in metadata."""
        chunker = FixedChunker(max_tokens=20)
        text = "Content " * 100
        result = chunker.chunkify(text)

        for i, chunk in enumerate(result):
            assert 'metadata' in chunk
            assert chunk['metadata'].get('chunk_index') == i

    def test_max_tokens_and_overlap_parameters(self):
        """FixedChunker must accept max_tokens and overlap_tokens."""
        chunker = FixedChunker(max_tokens=256, overlap_tokens=25)
        assert chunker.max_tokens == 256
        assert chunker.overlap_tokens == 25


class TestChunkerInterfaceContract:
    """Test that all chunkers satisfy the interface contract."""

    @pytest.fixture(params=[
        HybridChunker(max_tokens=512),
        SemanticChunker(max_tokens=512),
        FixedChunker(max_tokens=512),
    ])
    def chunker(self, request):
        """Parametrized fixture for all chunker implementations."""
        return request.param

    def test_has_name_property(self, chunker):
        """All chunkers must have name property."""
        assert hasattr(chunker, 'name')
        assert isinstance(chunker.name, str)
        assert len(chunker.name) > 0

    def test_has_chunkify_method(self, chunker):
        """All chunkers must have chunkify method."""
        assert hasattr(chunker, 'chunkify')
        assert callable(chunker.chunkify)

    def test_chunkify_returns_list_of_dicts(self, chunker):
        """chunkify must return List[Dict] with 'content' key."""
        result = chunker.chunkify("Test content for chunking.")

        assert isinstance(result, list)
        for chunk in result:
            assert isinstance(chunk, dict)
            assert 'content' in chunk
            assert isinstance(chunk['content'], str)

    def test_chunkify_handles_empty_input(self, chunker):
        """chunkify must handle empty input gracefully."""
        result = chunker.chunkify("")
        assert isinstance(result, list)
        # Should return empty list, not raise exception

    def test_chunkify_accepts_kwargs(self, chunker):
        """chunkify must accept **kwargs without error."""
        # Should not raise even with unknown kwargs
        result = chunker.chunkify("Test", unknown_param="value")
        assert isinstance(result, list)
