"""
Hybrid search combining vector similarity and keyword search
"""
import sqlite3
from typing import List, Dict, Tuple
from collections import defaultdict


class KeywordSearcher:
    """Handles FTS5 keyword search"""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def search(self, query: str, top_k: int) -> List[Tuple]:
        """Search using FTS5 keyword matching"""
        cursor = self.conn.execute("""
            SELECT c.id, c.content, d.file_path, c.page,
                   fts.rank as score
            FROM fts_chunks fts
            JOIN chunks c ON fts.chunk_id = c.id
            JOIN documents d ON c.document_id = d.id
            WHERE fts_chunks MATCH ?
            ORDER BY fts.rank DESC
            LIMIT ?
        """, (query, top_k))
        return cursor.fetchall()


class RankFusion:
    """Reciprocal Rank Fusion algorithm"""

    def __init__(self, k: int = 60):
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
    """Combines vector and keyword search"""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.keyword = KeywordSearcher(conn)
        self.fusion = RankFusion()

    def search(self, query: str, vector_results: List[Dict],
              top_k: int) -> List[Dict]:
        """Execute hybrid search"""
        try:
            keyword_results = self.keyword.search(query, top_k * 2)
            fused = self.fusion.fuse(vector_results, keyword_results)
            return fused[:top_k]
        except Exception:
            return vector_results
