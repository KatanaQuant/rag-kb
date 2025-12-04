"""
NumPy-based in-memory vector index for fast similarity search.

Performance comparison (59K 1024-dim vectors):
- sqlite-vec: ~78 seconds per query
- NumPy: ~0.26 seconds per query (300x faster)

The index is loaded into memory on startup and provides O(n) brute-force
cosine similarity search using NumPy's vectorized operations.
"""
import logging
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional
import aiosqlite

logger = logging.getLogger(__name__)


class NumpyVectorIndex:
    """In-memory vector index using NumPy for fast similarity search.

    Pre-loads all embeddings into memory on initialization for sub-second
    query performance. Uses ~240MB RAM for 59K 1024-dim vectors.

    Usage:
        index = NumpyVectorIndex(db_path)
        await index.load()
        results = await index.search(query_embedding, top_k=5)
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.embeddings: Optional[np.ndarray] = None
        self.chunk_ids: Optional[List[int]] = None
        self.norms: Optional[np.ndarray] = None  # Pre-computed for cosine
        self._loaded = False

    async def load(self) -> None:
        """Load all embeddings into memory from SQLite.

        This is a one-time operation during startup (~45s for 59K vectors).
        After loading, searches complete in ~0.3 seconds.
        """
        if self._loaded:
            return

        logger.info("Loading vector index into memory...")

        async with aiosqlite.connect(self.db_path) as conn:
            # Load sqlite-vec extension
            await conn.enable_load_extension(True)
            import sqlite_vec
            await conn.load_extension(sqlite_vec.loadable_path())

            # Fetch all embeddings
            cursor = await conn.execute(
                "SELECT chunk_id, embedding FROM vec_chunks"
            )
            rows = await cursor.fetchall()

        if not rows:
            logger.warning("No embeddings found in database")
            self.embeddings = np.array([], dtype=np.float32)
            self.chunk_ids = []
            self.norms = np.array([], dtype=np.float32)
            self._loaded = True
            return

        # Convert to numpy arrays
        self.chunk_ids = [r[0] for r in rows]
        self.embeddings = np.array(
            [np.frombuffer(r[1], dtype=np.float32) for r in rows],
            dtype=np.float32
        )

        # Pre-compute norms for cosine similarity
        self.norms = np.linalg.norm(self.embeddings, axis=1)

        self._loaded = True
        logger.info(
            f"Vector index loaded: {len(self.chunk_ids)} vectors, "
            f"shape={self.embeddings.shape}, "
            f"memory={self.embeddings.nbytes / 1024 / 1024:.1f}MB"
        )

    async def search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        threshold: Optional[float] = None
    ) -> List[Dict]:
        """Search for similar vectors using NumPy cosine similarity.

        Args:
            query_embedding: Query vector (list of floats)
            top_k: Number of results to return
            threshold: Minimum similarity score (0-1)

        Returns:
            List of dicts with chunk_id and score
        """
        if not self._loaded:
            await self.load()

        if len(self.chunk_ids) == 0:
            return []

        query = np.array(query_embedding, dtype=np.float32)
        query_norm = np.linalg.norm(query)

        if query_norm == 0:
            return []

        # Cosine similarity: dot(a,b) / (norm(a) * norm(b))
        similarities = np.dot(self.embeddings, query) / (self.norms * query_norm)

        # Get top-k indices
        if top_k >= len(similarities):
            top_indices = np.argsort(similarities)[::-1]
        else:
            # Partial sort is faster for top-k
            top_indices = np.argpartition(similarities, -top_k)[-top_k:]
            top_indices = top_indices[np.argsort(similarities[top_indices])[::-1]]

        # Build results
        results = []
        for idx in top_indices:
            score = float(similarities[idx])
            if threshold is not None and score < threshold:
                continue
            results.append({
                'chunk_id': self.chunk_ids[idx],
                'score': score
            })
            if len(results) >= top_k:
                break

        return results

    async def search_with_metadata(
        self,
        conn: aiosqlite.Connection,
        query_embedding: List[float],
        top_k: int = 5,
        threshold: Optional[float] = None
    ) -> List[Dict]:
        """Search and fetch chunk metadata from SQLite.

        This is the main entry point for query execution.
        Uses NumPy for similarity search, SQLite for metadata.
        """
        # Fast NumPy search
        search_results = await self.search(query_embedding, top_k, threshold)

        if not search_results:
            return []

        # Fetch metadata for top chunks
        chunk_ids = [r['chunk_id'] for r in search_results]
        scores = {r['chunk_id']: r['score'] for r in search_results}

        placeholders = ','.join(['?'] * len(chunk_ids))
        cursor = await conn.execute(f"""
            SELECT c.id, c.content, d.file_path, c.page
            FROM chunks c
            JOIN documents d ON c.document_id = d.id
            WHERE c.id IN ({placeholders})
        """, chunk_ids)

        rows = await cursor.fetchall()

        # Build results with metadata
        results = []
        for row in rows:
            chunk_id, content, file_path, page = row
            results.append({
                'content': content,
                'source': Path(file_path).name,
                'page': page,
                'score': scores[chunk_id]
            })

        # Sort by score (descending) since SQLite may return unordered
        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:top_k]

    def is_loaded(self) -> bool:
        """Check if index is loaded into memory."""
        return self._loaded

    def stats(self) -> Dict:
        """Get index statistics."""
        if not self._loaded:
            return {'loaded': False}
        return {
            'loaded': True,
            'num_vectors': len(self.chunk_ids),
            'dimensions': self.embeddings.shape[1] if len(self.embeddings) > 0 else 0,
            'memory_mb': self.embeddings.nbytes / 1024 / 1024
        }
