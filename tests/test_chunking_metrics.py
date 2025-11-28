"""Tests for chunking quality metrics"""

import pytest
from evaluation.chunking_metrics import (
    ChunkAnalyzer, ChunkStats, BoundaryCoherenceResult,
    RetrievalEvaluator, RetrievalResult, analyze_document_chunks
)


class TestChunkAnalyzer:
    """Tests for ChunkAnalyzer"""

    @pytest.fixture
    def analyzer(self):
        return ChunkAnalyzer()

    def test_compute_stats_empty(self, analyzer):
        """Empty list returns zero stats"""
        stats = analyzer.compute_stats([])
        assert stats.count == 0
        assert stats.avg_size == 0.0
        assert stats.total_chars == 0

    def test_compute_stats_single_chunk(self, analyzer):
        """Single chunk computes correctly"""
        chunks = ["Hello world"]
        stats = analyzer.compute_stats(chunks)
        assert stats.count == 1
        assert stats.total_chars == 11
        assert stats.avg_size == 11.0
        assert stats.min_size == 11
        assert stats.max_size == 11
        assert stats.std_dev == 0.0

    def test_compute_stats_multiple_chunks(self, analyzer):
        """Multiple chunks compute averages correctly"""
        chunks = ["short", "medium text", "this is a longer piece of text"]
        stats = analyzer.compute_stats(chunks)
        assert stats.count == 3
        assert stats.min_size == 5
        assert stats.max_size == 30  # "this is a longer piece of text" = 30 chars
        assert stats.avg_size == pytest.approx(15.33, rel=0.01)

    def test_size_distribution_buckets(self, analyzer):
        """Size distribution categorizes correctly"""
        chunks = [
            "x" * 50,    # tiny
            "x" * 200,   # small
            "x" * 1000,  # medium
            "x" * 3000,  # large
            "x" * 6000,  # huge
        ]
        stats = analyzer.compute_stats(chunks)
        assert stats.size_distribution['tiny (<100)'] == 1
        assert stats.size_distribution['small (100-500)'] == 1
        assert stats.size_distribution['medium (500-2000)'] == 1
        assert stats.size_distribution['large (2000-5000)'] == 1
        assert stats.size_distribution['huge (>5000)'] == 1


class TestBoundaryCoherence:
    """Tests for boundary coherence analysis"""

    @pytest.fixture
    def analyzer(self):
        return ChunkAnalyzer()

    def test_single_chunk_perfect_score(self, analyzer):
        """Single chunk has no boundaries, score is 1.0"""
        result = analyzer.analyze_boundary_coherence(["Single chunk"])
        assert result.score == 1.0
        assert result.total_boundaries == 0

    def test_clean_sentence_boundaries(self, analyzer):
        """Sentences ending with punctuation are clean"""
        chunks = [
            "This is the first sentence.",
            "This is the second sentence!"
        ]
        result = analyzer.analyze_boundary_coherence(chunks, 'text')
        assert result.score == 1.0
        assert result.clean_boundaries == 1
        assert result.mid_sentence_splits == 0

    def test_mid_sentence_split_detected(self, analyzer):
        """Mid-sentence splits are detected (with space at boundary)"""
        chunks = [
            "This is an incomplete ",  # trailing space = not mid-word
            "sentence that continues here."
        ]
        result = analyzer.analyze_boundary_coherence(chunks, 'text')
        assert result.score < 1.0
        assert result.mid_sentence_splits == 1

    def test_mid_word_split_detected(self, analyzer):
        """Mid-word splits are detected"""
        chunks = [
            "This is incomp",
            "lete word split"
        ]
        result = analyzer.analyze_boundary_coherence(chunks, 'text')
        assert result.mid_word_splits == 1

    def test_code_boundary_clean_braces(self, analyzer):
        """Code chunks ending with braces are clean"""
        chunks = [
            "function foo() {\n    return 1;\n}",
            "function bar() {\n    return 2;\n}"
        ]
        result = analyzer.analyze_boundary_coherence(chunks, 'code')
        assert result.score == 1.0

    def test_code_boundary_newline(self, analyzer):
        """Code chunks ending with newline are clean"""
        chunks = [
            "x = 1\n",
            "y = 2\n"
        ]
        result = analyzer.analyze_boundary_coherence(chunks, 'code')
        assert result.score == 1.0

    def test_markdown_header_boundary(self, analyzer):
        """Markdown with header starts is clean"""
        chunks = [
            "Some content.\n",
            "# New Section\nMore content."
        ]
        result = analyzer.analyze_boundary_coherence(chunks, 'markdown')
        assert result.score == 1.0

    def test_paragraph_boundary_clean(self, analyzer):
        """Double newline (paragraph) is clean boundary"""
        chunks = [
            "First paragraph.\n\n",
            "Second paragraph."
        ]
        result = analyzer.analyze_boundary_coherence(chunks, 'text')
        assert result.score == 1.0

    def test_multiple_boundaries_mixed(self, analyzer):
        """Multiple boundaries with mixed quality"""
        chunks = [
            "Clean sentence end.",
            "Mid-sentence ",  # trailing space = mid-sentence, not mid-word
            "split here.",
            "Another clean end!"
        ]
        result = analyzer.analyze_boundary_coherence(chunks, 'text')
        # 3 boundaries: 2 clean, 1 mid-sentence
        assert result.total_boundaries == 3
        assert result.clean_boundaries == 2
        assert result.mid_sentence_splits == 1
        assert result.score == pytest.approx(2/3, rel=0.01)


class TestRetrievalEvaluator:
    """Tests for retrieval accuracy evaluation"""

    def test_empty_test_set(self):
        """Empty test set returns zeros"""
        evaluator = RetrievalEvaluator(lambda q, k: [])
        result = evaluator.evaluate([], k=5)
        assert result.precision_at_k == 0.0
        assert result.recall_at_k == 0.0
        assert result.mean_reciprocal_rank == 0.0
        assert result.queries_evaluated == 0

    def test_perfect_retrieval(self):
        """Perfect retrieval scores 1.0"""
        def search_fn(query, k):
            return [{'id': 1}, {'id': 2}, {'id': 3}]

        evaluator = RetrievalEvaluator(search_fn)
        test_set = [{'query': 'test', 'relevant_ids': [1, 2, 3]}]

        result = evaluator.evaluate(test_set, k=3)
        assert result.precision_at_k == 1.0
        assert result.recall_at_k == 1.0
        assert result.mean_reciprocal_rank == 1.0

    def test_partial_recall(self):
        """Partial recall when not all relevant retrieved"""
        def search_fn(query, k):
            return [{'id': 1}, {'id': 4}, {'id': 5}]

        evaluator = RetrievalEvaluator(search_fn)
        test_set = [{'query': 'test', 'relevant_ids': [1, 2, 3]}]

        result = evaluator.evaluate(test_set, k=3)
        # 1 relevant out of 3 retrieved
        assert result.precision_at_k == pytest.approx(1/3, rel=0.01)
        # 1 relevant out of 3 total relevant
        assert result.recall_at_k == pytest.approx(1/3, rel=0.01)
        # First relevant at position 1
        assert result.mean_reciprocal_rank == 1.0

    def test_mrr_calculation(self):
        """MRR calculated correctly for different positions"""
        def search_fn(query, k):
            if 'first' in query:
                return [{'id': 1}, {'id': 2}, {'id': 3}]  # relevant at 1
            elif 'second' in query:
                return [{'id': 2}, {'id': 1}, {'id': 3}]  # relevant at 2
            else:
                return [{'id': 2}, {'id': 3}, {'id': 1}]  # relevant at 3

        evaluator = RetrievalEvaluator(search_fn)
        test_set = [
            {'query': 'first', 'relevant_ids': [1]},
            {'query': 'second', 'relevant_ids': [1]},
            {'query': 'third', 'relevant_ids': [1]},
        ]

        result = evaluator.evaluate(test_set, k=3)
        # MRR = (1/1 + 1/2 + 1/3) / 3 = (1 + 0.5 + 0.333) / 3 = 0.611
        expected_mrr = (1 + 0.5 + 1/3) / 3
        assert result.mean_reciprocal_rank == pytest.approx(expected_mrr, rel=0.01)

    def test_no_relevant_retrieved(self):
        """Zero scores when no relevant results retrieved"""
        def search_fn(query, k):
            return [{'id': 10}, {'id': 11}, {'id': 12}]

        evaluator = RetrievalEvaluator(search_fn)
        test_set = [{'query': 'test', 'relevant_ids': [1, 2, 3]}]

        result = evaluator.evaluate(test_set, k=3)
        assert result.precision_at_k == 0.0
        assert result.recall_at_k == 0.0
        assert result.mean_reciprocal_rank == 0.0

    def test_chunk_id_key_variant(self):
        """Handles chunk_id key as alternative to id"""
        def search_fn(query, k):
            return [{'chunk_id': 1}, {'chunk_id': 2}]

        evaluator = RetrievalEvaluator(search_fn)
        test_set = [{'query': 'test', 'relevant_ids': [1, 2]}]

        result = evaluator.evaluate(test_set, k=2)
        assert result.precision_at_k == 1.0


class TestAnalyzeDocumentChunks:
    """Tests for convenience function"""

    def test_returns_stats_and_coherence(self):
        """Returns both stats and boundary coherence"""
        chunks = ["First sentence.", "Second sentence."]
        result = analyze_document_chunks(chunks, 'text')

        assert 'stats' in result
        assert 'boundary_coherence' in result
        assert isinstance(result['stats'], ChunkStats)
        assert isinstance(result['boundary_coherence'], BoundaryCoherenceResult)

    def test_respects_content_type(self):
        """Content type affects coherence analysis"""
        code_chunks = [
            "def foo():\n    pass\n",
            "def bar():\n    pass\n"
        ]

        # As code - should be clean (ends with newline)
        result_code = analyze_document_chunks(code_chunks, 'code')
        assert result_code['boundary_coherence'].score == 1.0

        # As text - also clean (ends with newline)
        result_text = analyze_document_chunks(code_chunks, 'text')
        assert result_text['boundary_coherence'].score == 1.0


class TestEdgeCases:
    """Edge case tests"""

    @pytest.fixture
    def analyzer(self):
        return ChunkAnalyzer()

    def test_whitespace_only_chunks(self, analyzer):
        """Handles whitespace-only chunks"""
        chunks = ["   ", "\n\n", "\t"]
        stats = analyzer.compute_stats(chunks)
        assert stats.count == 3

    def test_unicode_content(self, analyzer):
        """Handles unicode content correctly"""
        chunks = ["Hello, world!", "Bonjour, le monde!"]
        stats = analyzer.compute_stats(chunks)
        # Character count should be correct
        assert stats.total_chars == len(chunks[0]) + len(chunks[1])

    def test_very_long_chunk(self, analyzer):
        """Handles very long chunks"""
        long_chunk = "x" * 100000
        stats = analyzer.compute_stats([long_chunk])
        assert stats.max_size == 100000
        assert stats.size_distribution['huge (>5000)'] == 1

    def test_empty_string_chunk(self, analyzer):
        """Handles empty string chunks"""
        chunks = ["", "content", ""]
        stats = analyzer.compute_stats(chunks)
        assert stats.count == 3
        assert stats.min_size == 0
