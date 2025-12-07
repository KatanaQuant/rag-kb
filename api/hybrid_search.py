"""
Hybrid search combining vector similarity and keyword search

Uses rank_bm25 library for probabilistic BM25 scoring instead of FTS5.
FTS5 uses boolean MATCH (implicit AND) which returns nothing when any
term is missing. BM25Okapi scores ALL documents probabilistically,
matching how LangChain/LlamaIndex implement keyword search.
"""
import sqlite3
import re
from typing import List, Dict, Tuple, Optional
from collections import defaultdict

from rank_bm25 import BM25Okapi


class BM25Searcher:
    """
    BM25 keyword search using rank_bm25 library.

    Scores ALL documents probabilistically rather than FTS5's boolean matching.
    Documents missing query terms still get partial scores based on terms present.
    """

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self._corpus: List[List[str]] = []  # Tokenized documents
        self._chunk_data: List[Tuple] = []  # (id, content, file_path, page)
        self._bm25: Optional[BM25Okapi] = None
        self._build_index()

    def _tokenize(self, text: str) -> List[str]:
        """
        Simple word tokenization with lowercasing.

        Splits on non-alphanumeric characters, lowercases all tokens.
        Can be extended with stemming/lemmatization later.
        """
        # Split on non-word characters, filter empty strings
        tokens = re.split(r'\W+', text.lower())
        return [t for t in tokens if t]

    def _build_index(self) -> None:
        """Load all chunks from database and build BM25 index."""
        cursor = self.conn.execute("""
            SELECT c.id, c.content, d.file_path, c.page
            FROM chunks c
            JOIN documents d ON c.document_id = d.id
            ORDER BY c.id
        """)

        self._corpus = []
        self._chunk_data = []

        for row in cursor:
            chunk_id, content, file_path, page = row
            self._chunk_data.append((chunk_id, content, file_path, page))
            self._corpus.append(self._tokenize(content))

        # Build BM25 index (empty corpus is handled gracefully)
        # Using defaults: k1=2.0, b=0.75 (tested k1=1.5/b=0.5 and k1=2.5/b=0.9, no improvement)
        if self._corpus:
            self._bm25 = BM25Okapi(self._corpus)
        else:
            self._bm25 = None

    def refresh(self) -> None:
        """Rebuild the BM25 index from database (call after adding documents)."""
        self._build_index()

    def _get_title_boost(self, file_path: str, query_tokens: List[str]) -> float:
        """
        Calculate title boost multiplier based on query-title overlap.

        If query contains words from the document title/filename, boost that document.
        This helps queries like "24 Assets" find the "24 Assets" book.

        Can be disabled via TITLE_BOOST_ENABLED=false env var (for permutation testing).
        """
        import os
        if os.getenv("TITLE_BOOST_ENABLED", "true").lower() != "true":
            return 1.0

        if not file_path or not query_tokens:
            return 1.0

        # Extract filename without extension and path
        from pathlib import Path
        filename = Path(file_path).stem.lower()

        # Tokenize filename
        filename_tokens = set(self._tokenize(filename))
        query_token_set = set(query_tokens)

        # Count overlapping tokens
        overlap = len(filename_tokens & query_token_set)

        if overlap == 0:
            return 1.0

        # Boost based on overlap: 1.5x for 1 match, 2.0x for 2+, 3.0x for 3+
        if overlap >= 3:
            return 3.0
        elif overlap >= 2:
            return 2.0
        else:
            return 1.5

    def search(self, query: str, top_k: int) -> List[Tuple]:
        """
        Search using BM25 scoring with title boosting.

        Returns results in same format as KeywordSearcher:
        List of (id, content, file_path, page, score) tuples.

        Unlike FTS5, this scores ALL documents probabilistically.
        Documents missing some query terms still get partial scores.
        Title boost: documents whose filename matches query terms get higher scores.
        """
        if not self._bm25 or not self._corpus:
            return []

        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        # Get scores for ALL documents
        scores = self._bm25.get_scores(query_tokens)

        # Apply title boosting
        for idx in range(len(scores)):
            if scores[idx] > 0:
                file_path = self._chunk_data[idx][2]
                boost = self._get_title_boost(file_path, query_tokens)
                scores[idx] *= boost

        # Get indices of top-k scores (descending order)
        # argsort returns ascending, so we reverse and take first top_k
        top_indices = scores.argsort()[::-1][:top_k]

        results = []
        for idx in top_indices:
            score = scores[idx]
            # Skip zero-score results (no matching terms)
            if score <= 0:
                continue
            chunk_id, content, file_path, page = self._chunk_data[idx]
            results.append((chunk_id, content, file_path, page, score))

        return results


class KeywordSearcher:
    """
    DEPRECATED: FTS5 keyword search.

    Kept for reference. Use BM25Searcher instead for probabilistic scoring.
    FTS5 MATCH uses boolean AND between terms, returning nothing when
    any term is missing from a document.
    """

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def search(self, query: str, top_k: int) -> List[Tuple]:
        """Search using FTS5 keyword matching"""
        cursor = self.conn.execute("""
            SELECT c.id, c.content, d.file_path, c.page,
                   fts.rank as score
            FROM fts_chunks fts
            JOIN chunks c ON fts.rowid = c.id
            JOIN documents d ON c.document_id = d.id
            WHERE fts_chunks MATCH ?
            ORDER BY fts.rank DESC
            LIMIT ?
        """, (query, top_k))
        return cursor.fetchall()

class RankFusion:
    """Reciprocal Rank Fusion algorithm"""

    def __init__(self, k: int = 20):
        self.k = k

    def fuse(self, vector_results: List[Dict],
            keyword_results: List[Tuple]) -> List[Dict]:
        """Merge vector and keyword results using RRF"""
        scores = defaultdict(float)
        chunk_data = {}

        self._add_vector(vector_results, scores, chunk_data)
        self._add_keyword(keyword_results, scores, chunk_data)

        return self._sort_results(scores, chunk_data)

    def _add_vector(self, results, scores, data):
        """Add vector search scores"""
        for rank, result in enumerate(results, 1):
            key = self._make_key(result)
            scores[key] += 1.0 / (self.k + rank)
            data[key] = result

    def _add_keyword(self, results, scores, data):
        """Add keyword search scores"""
        for rank, row in enumerate(results, 1):
            result = self._row_to_dict(row)
            key = self._make_key(result)
            scores[key] += 1.0 / (self.k + rank)
            if key not in data:
                data[key] = result

    @staticmethod
    def _make_key(result: Dict) -> str:
        """Create unique key for result"""
        return f"{result['source']}:{result['page']}:{result['content'][:50]}"

    @staticmethod
    def _row_to_dict(row: Tuple) -> Dict:
        """Convert DB row to result dict"""
        from pathlib import Path
        return {
            'content': row[1],
            'source': Path(row[2]).name,
            'page': row[3],
            'score': float(abs(row[4]))
        }

    def _sort_results(self, scores, data) -> List[Dict]:
        """Sort by fused score"""
        sorted_keys = sorted(scores.keys(), key=lambda k: scores[k], reverse=True)
        results = []
        for key in sorted_keys:
            result = data[key].copy()
            result['score'] = float(scores[key])
            results.append(result)
        return results

class HybridSearcher:
    """Combines vector and keyword search using BM25 for keyword scoring."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.keyword = BM25Searcher(conn)
        self.fusion = RankFusion()

    def refresh_keyword_index(self) -> None:
        """Refresh BM25 index after documents are added/removed."""
        self.keyword.refresh()

    def search(self, query: str, vector_results: List[Dict],
              top_k: int) -> List[Dict]:
        """Execute hybrid search"""
        try:
            keyword_results = self.keyword.search(query, top_k * 4)
            fused = self.fusion.fuse(vector_results, keyword_results)
            return fused[:top_k]
        except Exception:
            return vector_results
