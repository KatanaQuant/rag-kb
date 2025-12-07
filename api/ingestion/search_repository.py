import sqlite3
from pathlib import Path
from typing import List, Dict, Optional
import numpy as np

class SearchRepository:
    """Vector and hybrid search operations.

    Single Responsibility: Execute search queries only.
    Uses vectorlite knn_search for fast HNSW-based approximate nearest neighbor.
    """

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def vector_search(self, embedding: List[float], top_k: int, threshold: float = None) -> List[Dict]:
        """Search for similar vectors using vectorlite HNSW index"""
        blob = self._to_blob(embedding)
        results = self._execute_vector_search(blob, top_k)
        return self._format_results(results, threshold)

    def _execute_vector_search(self, blob: bytes, top_k: int, ef: int = 150):
        """Execute vectorlite knn_search query

        vectorlite knn_search returns (rowid, distance) pairs.
        We then JOIN with chunks/documents to get metadata.

        Args:
            blob: Query embedding as bytes
            top_k: Number of results to return
            ef: Search quality parameter (higher = more accurate but slower)
                ef=10 (default): ~31% recall, ~35µs
                ef=100: ~88% recall, ~168µs
                ef=150: ~95% recall, ~310µs
        """
        # First get the k nearest neighbors from vectorlite
        # ef parameter controls HNSW search quality - default 10 is too low!
        cursor = self.conn.execute("""
            SELECT v.rowid, v.distance
            FROM vec_chunks v
            WHERE knn_search(v.embedding, knn_param(?, ?, ?))
        """, (blob, top_k, ef))
        vector_results = cursor.fetchall()

        if not vector_results:
            return []

        # Then fetch metadata for those chunk IDs
        chunk_ids = [r[0] for r in vector_results]
        distances = {r[0]: r[1] for r in vector_results}

        placeholders = ','.join('?' * len(chunk_ids))
        cursor = self.conn.execute(f"""
            SELECT c.id, c.content, d.file_path, c.page
            FROM chunks c
            JOIN documents d ON c.document_id = d.id
            WHERE c.id IN ({placeholders})
        """, chunk_ids)
        metadata_results = cursor.fetchall()

        # Combine results with distances, preserving order by distance
        combined = []
        for row in metadata_results:
            chunk_id = row[0]
            combined.append((row[1], row[2], row[3], distances[chunk_id]))

        # Sort by distance (ascending)
        combined.sort(key=lambda x: x[3])
        return combined

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
