import sqlite3
from pathlib import Path
from typing import List, Dict, Optional
import numpy as np

class SearchRepository:
    """Vector and hybrid search operations.

    Single Responsibility: Execute search queries only.
    """

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def vector_search(self, embedding: List[float], top_k: int, threshold: float = None) -> List[Dict]:
        """Search for similar vectors using cosine similarity"""
        blob = self._to_blob(embedding)
        results = self._execute_vector_search(blob, top_k)
        return self._format_results(results, threshold)

    def _execute_vector_search(self, blob: bytes, top_k: int):
        """Execute vector similarity query"""
        cursor = self.conn.execute("""
            SELECT c.content, d.file_path, c.page,
                   vec_distance_cosine(v.embedding, ?) as dist
            FROM vec_chunks v
            JOIN chunks c ON v.chunk_id = c.id
            JOIN documents d ON c.document_id = d.id
            ORDER BY dist ASC
            LIMIT ?
        """, (blob, top_k))
        return cursor.fetchall()

    def _format_results(self, rows, threshold: float) -> List[Dict]:
        """Format search results and apply threshold"""
        results = []
        for row in rows:
            score = 1 - row[3]  # Convert distance to similarity
            if threshold is None or score >= threshold:
                results.append({
                    'content': row[0],
                    'source': Path(row[1]).name,
                    'page': row[2],
                    'score': float(score)
                })
        return results

    @staticmethod
    def _to_blob(embedding: List[float]) -> bytes:
        """Convert embedding list to binary blob"""
        arr = np.array(embedding, dtype=np.float32)
        return arr.tobytes()
