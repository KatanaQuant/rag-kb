"""Chunking quality metrics for RAG evaluation.

Metrics implemented:
1. Boundary Coherence - Do splits happen at natural breaks?
2. Retrieval Accuracy - Does query find right chunks? (requires test set)
3. Chunk Statistics - Size distribution, count per document

Reference: internal_planning/CHUNKING_STRATEGY_EVALUATION.md
"""

import re
import statistics
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from collections import Counter


@dataclass
class ChunkStats:
    """Statistics for a set of chunks"""
    count: int
    total_chars: int
    avg_size: float
    median_size: float
    min_size: int
    max_size: int
    std_dev: float
    size_distribution: Dict[str, int] = field(default_factory=dict)


@dataclass
class BoundaryCoherenceResult:
    """Results from boundary coherence analysis"""
    score: float  # 0-1, higher is better
    total_boundaries: int
    clean_boundaries: int
    mid_sentence_splits: int
    mid_word_splits: int
    details: List[Dict] = field(default_factory=list)


@dataclass
class RetrievalResult:
    """Results from retrieval accuracy test"""
    precision_at_k: float
    recall_at_k: float
    mean_reciprocal_rank: float
    queries_evaluated: int
    details: List[Dict] = field(default_factory=list)


class ChunkAnalyzer:
    """Analyze chunk quality without needing database access"""

    # Sentence-ending patterns
    SENTENCE_END = re.compile(r'[.!?]["\')\]]*\s*$')

    # Code block boundaries (functions, classes, etc.)
    CODE_BOUNDARIES = re.compile(
        r'(?:^|\n)(?:def |class |function |async def |const |let |var |export |import )',
        re.MULTILINE
    )

    # Markdown section boundaries
    MARKDOWN_BOUNDARIES = re.compile(r'^#{1,6}\s+', re.MULTILINE)

    def compute_stats(self, chunks: List[str]) -> ChunkStats:
        """Compute basic statistics for chunk sizes"""
        if not chunks:
            return ChunkStats(
                count=0, total_chars=0, avg_size=0.0, median_size=0.0,
                min_size=0, max_size=0, std_dev=0.0
            )

        sizes = [len(c) for c in chunks]

        # Size distribution buckets
        buckets = {'tiny (<100)': 0, 'small (100-500)': 0,
                   'medium (500-2000)': 0, 'large (2000-5000)': 0,
                   'huge (>5000)': 0}
        for size in sizes:
            if size < 100:
                buckets['tiny (<100)'] += 1
            elif size < 500:
                buckets['small (100-500)'] += 1
            elif size < 2000:
                buckets['medium (500-2000)'] += 1
            elif size < 5000:
                buckets['large (2000-5000)'] += 1
            else:
                buckets['huge (>5000)'] += 1

        return ChunkStats(
            count=len(chunks),
            total_chars=sum(sizes),
            avg_size=statistics.mean(sizes),
            median_size=statistics.median(sizes),
            min_size=min(sizes),
            max_size=max(sizes),
            std_dev=statistics.stdev(sizes) if len(sizes) > 1 else 0.0,
            size_distribution=buckets
        )

    def analyze_boundary_coherence(
        self,
        chunks: List[str],
        content_type: str = 'text'
    ) -> BoundaryCoherenceResult:
        """Analyze whether chunks end at natural boundaries.

        A "clean" boundary is:
        - Text: End of sentence (. ! ?)
        - Code: End of function/class/statement
        - Markdown: End of section or paragraph

        Args:
            chunks: List of chunk contents
            content_type: 'text', 'code', or 'markdown'

        Returns:
            BoundaryCoherenceResult with score and details
        """
        if not chunks or len(chunks) < 2:
            return BoundaryCoherenceResult(
                score=1.0, total_boundaries=0, clean_boundaries=0,
                mid_sentence_splits=0, mid_word_splits=0
            )

        total_boundaries = len(chunks) - 1
        clean_boundaries = 0
        mid_sentence_splits = 0
        mid_word_splits = 0
        details = []

        for i in range(len(chunks) - 1):
            # Keep original for whitespace checks, stripped for content checks
            chunk_original = chunks[i]
            chunk_end = chunk_original.rstrip()
            next_original = chunks[i + 1]
            next_chunk_start = next_original.lstrip()

            boundary_info = {
                'boundary_index': i,
                'end_preview': chunk_end[-50:] if len(chunk_end) > 50 else chunk_end,
                'start_preview': next_chunk_start[:50] if len(next_chunk_start) > 50 else next_chunk_start,
                'is_clean': False,
                'issue': None
            }

            # Check for mid-word split: chunk ends with letter AND no whitespace at boundary
            # A true mid-word split has no whitespace between chunk end and next start
            has_trailing_whitespace = len(chunk_original) > len(chunk_end)
            has_leading_whitespace = len(next_original) > len(next_chunk_start)

            if (chunk_end and chunk_end[-1].isalpha() and
                next_chunk_start and next_chunk_start[0].isalpha() and
                not has_trailing_whitespace and not has_leading_whitespace):
                # True mid-word split (no whitespace at boundary)
                mid_word_splits += 1
                boundary_info['issue'] = 'mid_word'
                details.append(boundary_info)
                continue

            # Content-type specific boundary checking (use original for newline checks)
            if content_type == 'code':
                is_clean = self._is_clean_code_boundary(chunk_original, next_chunk_start)
            elif content_type == 'markdown':
                is_clean = self._is_clean_markdown_boundary(chunk_original, next_chunk_start)
            else:
                is_clean = self._is_clean_text_boundary(chunk_original, next_chunk_start)

            if is_clean:
                clean_boundaries += 1
                boundary_info['is_clean'] = True
            else:
                mid_sentence_splits += 1
                boundary_info['issue'] = 'mid_sentence'

            details.append(boundary_info)

        score = clean_boundaries / total_boundaries if total_boundaries > 0 else 1.0

        return BoundaryCoherenceResult(
            score=score,
            total_boundaries=total_boundaries,
            clean_boundaries=clean_boundaries,
            mid_sentence_splits=mid_sentence_splits,
            mid_word_splits=mid_word_splits,
            details=details
        )

    def _is_clean_text_boundary(self, chunk_end: str, next_start: str) -> bool:
        """Check if text boundary is at sentence end"""
        # End of sentence
        if self.SENTENCE_END.search(chunk_end):
            return True
        # Empty line (paragraph break)
        if chunk_end.endswith('\n\n') or chunk_end.endswith('\n'):
            return True
        return False

    def _is_clean_code_boundary(self, chunk_end: str, next_start: str) -> bool:
        """Check if code boundary is at natural break"""
        # Ends with closing brace/bracket
        if chunk_end.rstrip().endswith(('}', ')', ']', ':')):
            return True
        # Ends with newline (statement boundary)
        if chunk_end.endswith('\n'):
            return True
        # Next chunk starts with def/class/function
        if self.CODE_BOUNDARIES.match(next_start):
            return True
        return False

    def _is_clean_markdown_boundary(self, chunk_end: str, next_start: str) -> bool:
        """Check if markdown boundary is at natural break"""
        # End of paragraph
        if chunk_end.endswith('\n\n') or chunk_end.endswith('\n'):
            return True
        # Next chunk starts with header
        if self.MARKDOWN_BOUNDARIES.match(next_start):
            return True
        # End of sentence
        if self.SENTENCE_END.search(chunk_end):
            return True
        return False


class RetrievalEvaluator:
    """Evaluate retrieval accuracy using test queries.

    Requires a test set of (query, expected_chunk_ids) pairs.
    """

    def __init__(self, search_fn):
        """
        Args:
            search_fn: Callable(query, top_k) -> List[Dict] with 'id' key
        """
        self.search_fn = search_fn

    def evaluate(
        self,
        test_set: List[Dict],
        k: int = 5
    ) -> RetrievalResult:
        """Evaluate retrieval accuracy on test set.

        Args:
            test_set: List of {'query': str, 'relevant_ids': List[int]}
            k: Number of results to retrieve

        Returns:
            RetrievalResult with precision, recall, MRR
        """
        if not test_set:
            return RetrievalResult(
                precision_at_k=0.0, recall_at_k=0.0,
                mean_reciprocal_rank=0.0, queries_evaluated=0
            )

        precisions = []
        recalls = []
        reciprocal_ranks = []
        details = []

        for item in test_set:
            query = item['query']
            relevant_ids = set(item['relevant_ids'])

            # Get search results
            results = self.search_fn(query, k)
            retrieved_ids = [r.get('id') or r.get('chunk_id') for r in results]

            # Precision@k: fraction of retrieved that are relevant
            relevant_retrieved = len(set(retrieved_ids) & relevant_ids)
            precision = relevant_retrieved / k if k > 0 else 0.0
            precisions.append(precision)

            # Recall@k: fraction of relevant that were retrieved
            recall = relevant_retrieved / len(relevant_ids) if relevant_ids else 0.0
            recalls.append(recall)

            # Reciprocal rank: 1/position of first relevant result
            rr = 0.0
            for i, rid in enumerate(retrieved_ids):
                if rid in relevant_ids:
                    rr = 1.0 / (i + 1)
                    break
            reciprocal_ranks.append(rr)

            details.append({
                'query': query,
                'precision': precision,
                'recall': recall,
                'reciprocal_rank': rr,
                'retrieved': retrieved_ids,
                'relevant': list(relevant_ids)
            })

        return RetrievalResult(
            precision_at_k=statistics.mean(precisions) if precisions else 0.0,
            recall_at_k=statistics.mean(recalls) if recalls else 0.0,
            mean_reciprocal_rank=statistics.mean(reciprocal_ranks) if reciprocal_ranks else 0.0,
            queries_evaluated=len(test_set),
            details=details
        )


def analyze_document_chunks(
    chunks: List[str],
    content_type: str = 'text'
) -> Dict:
    """Convenience function to analyze chunks from a document.

    Args:
        chunks: List of chunk content strings
        content_type: 'text', 'code', or 'markdown'

    Returns:
        Dict with 'stats' and 'boundary_coherence' results
    """
    analyzer = ChunkAnalyzer()
    return {
        'stats': analyzer.compute_stats(chunks),
        'boundary_coherence': analyzer.analyze_boundary_coherence(chunks, content_type)
    }
