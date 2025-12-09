import sqlite3
import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import numpy as np

logger = logging.getLogger(__name__)


class NumpyVectorSearch:
    """In-memory vector search using numpy for fast cosine similarity.

    Trades startup time (~42s for 50k vectors) for fast queries (~2s vs 20s bruteforce).
    Loads all vectors into RAM at initialization for O(1) vectorized search.

    Performance:
    - Startup: ~42s to load 50k vectors (one-time cost)
    - Query: ~2s vs 20s with sqlite-vec bruteforce
    - Memory: ~250MB for 50k vectors @ 1024 dimensions
    """

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self._chunk_ids: List[int] = []
        self._embeddings: Optional[np.ndarray] = None  # Shape: (n_vectors, dim)
        self._chunk_metadata: Dict[int, Tuple[str, str, int]] = {}  # chunk_id -> (content, file_path, page)
        self._load_all_vectors()

    def _load_all_vectors(self):
        """Load all vectors and metadata into memory at startup."""
        logger.info("Loading vectors into memory for fast search...")

        # Load embeddings from vec_chunks
        cursor = self.conn.execute("""
            SELECT chunk_id, embedding FROM vec_chunks ORDER BY chunk_id
        """)

        embeddings_list = []
        for row in cursor:
            chunk_id = row[0]
            embedding = np.frombuffer(row[1], dtype=np.float32)
            self._chunk_ids.append(chunk_id)
            embeddings_list.append(embedding)

        if embeddings_list:
            self._embeddings = np.vstack(embeddings_list)
            # Normalize for cosine similarity (dot product of unit vectors)
            norms = np.linalg.norm(self._embeddings, axis=1, keepdims=True)
            # Avoid division by zero
            norms = np.where(norms == 0, 1, norms)
            self._embeddings = self._embeddings / norms

        # Load metadata
        cursor = self.conn.execute("""
            SELECT c.id, c.content, d.file_path, c.page
            FROM chunks c
            JOIN documents d ON c.document_id = d.id
        """)
        for row in cursor:
            self._chunk_metadata[row[0]] = (row[1], row[2], row[3])

        logger.info(f"Loaded {len(self._chunk_ids)} vectors into memory ({self._memory_usage_mb():.1f}MB)")

    def _memory_usage_mb(self) -> float:
        """Estimate memory usage in MB."""
        if self._embeddings is None:
            return 0.0
        # Embeddings array + metadata overhead
        return self._embeddings.nbytes / (1024 * 1024)

    def search(self, embedding: List[float], top_k: int, threshold: float = None) -> List[Dict]:
        """Fast vectorized cosine similarity search.

        Uses numpy dot product for O(n) vectorized search instead of
        sqlite-vec's O(n) row-by-row bruteforce.
        """
        if self._embeddings is None or len(self._embeddings) == 0:
            return []

        # Normalize query
        query = np.array(embedding, dtype=np.float32)
        query_norm = np.linalg.norm(query)
        if query_norm == 0:
            return []
        query = query / query_norm

        # Vectorized cosine similarity (dot product of normalized vectors)
        similarities = np.dot(self._embeddings, query)

        # Get top-k indices (argsort is ascending, so reverse)
        top_indices = np.argsort(similarities)[::-1][:top_k]

        results = []
        for idx in top_indices:
            score = float(similarities[idx])
            if threshold is not None and score < threshold:
                continue
            chunk_id = self._chunk_ids[idx]
            if chunk_id in self._chunk_metadata:
                content, file_path, page = self._chunk_metadata[chunk_id]
                results.append({
                    'content': content,
                    'source': Path(file_path).name,
                    'page': page,
                    'score': score
                })
        return results

    def refresh(self):
        """Reload vectors after documents are added/removed."""
        logger.info("Refreshing in-memory vector index...")
        self._chunk_ids = []
        self._chunk_metadata = {}
        self._embeddings = None
        self._load_all_vectors()


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
