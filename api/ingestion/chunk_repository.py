import sqlite3
import logging
from typing import List, Dict, Optional
import numpy as np

logger = logging.getLogger(__name__)

class ChunkRepository:
    """CRUD operations for chunks table.

    Single Responsibility: Manage text chunks only.
    """

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def add(self, doc_id: int, content: str, page: Optional[int], chunk_index: int) -> int:
        """Insert single chunk and return chunk ID"""
        cursor = self.conn.execute(
            """INSERT INTO chunks (document_id, content, page, chunk_index)
               VALUES (?, ?, ?, ?)""",
            (doc_id, content, page, chunk_index)
        )
        return cursor.lastrowid

    def add_batch(self, doc_id: int, chunks: List[Dict]) -> List[int]:
        """Insert multiple chunks and return their IDs"""
        chunk_ids = []
        for idx, chunk in enumerate(chunks):
            chunk_id = self.add(
                doc_id,
                chunk['content'],
                chunk.get('page'),
                idx
            )
            chunk_ids.append(chunk_id)
        return chunk_ids

    def get(self, chunk_id: int) -> Optional[Dict]:
        """Get chunk by ID"""
        cursor = self.conn.execute(
            "SELECT id, document_id, content, page, chunk_index FROM chunks WHERE id = ?",
            (chunk_id,)
        )
        result = cursor.fetchone()
        if not result:
            return None

        return {
            'id': result[0],
            'document_id': result[1],
            'content': result[2],
            'page': result[3],
            'chunk_index': result[4]
        }

    def get_by_document(self, doc_id: int) -> List[Dict]:
        """Get all chunks for a document"""
        cursor = self.conn.execute(
            "SELECT id, document_id, content, page, chunk_index FROM chunks WHERE document_id = ? ORDER BY chunk_index",
            (doc_id,)
        )
        results = []
        for row in cursor.fetchall():
            results.append({
                'id': row[0],
                'document_id': row[1],
                'content': row[2],
                'page': row[3],
                'chunk_index': row[4]
            })
        return results

    def count_by_document(self, doc_id: int) -> int:
        """Count chunks for a document"""
        cursor = self.conn.execute(
            "SELECT COUNT(*) FROM chunks WHERE document_id = ?",
            (doc_id,)
        )
        return cursor.fetchone()[0]

    def delete_by_document(self, doc_id: int) -> int:
        """Delete all chunks for a document and return count deleted"""
        count = self.count_by_document(doc_id)
        self.conn.execute("DELETE FROM chunks WHERE document_id = ?", (doc_id,))
        return count

    def update(self, chunk_id: int, content: str = None, page: int = None):
        """Update chunk content or page"""
        if content is not None:
            self.conn.execute(
                "UPDATE chunks SET content = ? WHERE id = ?",
                (content, chunk_id)
            )
        if page is not None:
            self.conn.execute(
                "UPDATE chunks SET page = ? WHERE id = ?",
                (page, chunk_id)
            )

    def count(self) -> int:
        """Count total chunks across all documents"""
        cursor = self.conn.execute("SELECT COUNT(*) FROM chunks")
        return cursor.fetchone()[0]

    def exists(self, chunk_id: int) -> bool:
        """Check if chunk exists"""
        cursor = self.conn.execute(
            "SELECT 1 FROM chunks WHERE id = ? LIMIT 1",
            (chunk_id,)
        )
        return cursor.fetchone() is not None

class VectorChunkRepository:
    """CRUD operations for vector embeddings.

    Single Responsibility: Manage vector embeddings for chunks.
    Separated from ChunkRepository to follow Interface Segregation.

    Uses vectorlite HNSW index for O(log n) approximate nearest neighbor search.
    Note: vectorlite uses 'rowid' as the primary key, which we map to chunk_id.
    """

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def add(self, chunk_id: int, embedding: List[float]):
        """Insert vector embedding for a chunk

        vectorlite requires explicit rowid - we use chunk_id as rowid.
        """
        blob = self._to_blob(embedding)
        try:
            self.conn.execute(
                "INSERT INTO vec_chunks (rowid, embedding) VALUES (?, ?)",
                (chunk_id, blob)
            )
        except Exception as e:
            print(f"[HNSW] FAILED chunk_id={chunk_id}: {e}")
            raise

    def add_batch(self, chunk_ids: List[int], embeddings: List[List[float]]):
        """Insert multiple vector embeddings"""
        logger.info(f"[HNSW] Indexing batch of {len(chunk_ids)} chunks")
        for chunk_id, embedding in zip(chunk_ids, embeddings):
            self.add(chunk_id, embedding)
        logger.info(f"[HNSW] Batch complete: {len(chunk_ids)} chunks indexed")

    def delete_by_chunk(self, chunk_id: int):
        """Delete vector for a chunk"""
        self.conn.execute(
            "DELETE FROM vec_chunks WHERE rowid = ?",
            (chunk_id,)
        )

    @staticmethod
    def _to_blob(embedding: List[float]) -> bytes:
        """Convert embedding list to binary blob"""
        arr = np.array(embedding, dtype=np.float32)
        return arr.tobytes()

class FTSChunkRepository:
    """CRUD operations for full-text search index.

    Single Responsibility: Manage FTS5 index for chunks.
    """

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def add(self, chunk_id: int, content: str):
        """Insert chunk into FTS5 index"""
        try:
            self.conn.execute(
                "INSERT INTO fts_chunks (chunk_id, content) VALUES (?, ?)",
                (chunk_id, content)
            )
        except Exception:
            pass  # FTS errors are non-fatal

    def add_batch(self, chunk_ids: List[int], contents: List[str]):
        """Insert multiple chunks into FTS5 index"""
        for chunk_id, content in zip(chunk_ids, contents):
            self.add(chunk_id, content)

    def delete_by_chunk(self, chunk_id: int):
        """Delete chunk from FTS5 index"""
        try:
            self.conn.execute(
                "DELETE FROM fts_chunks WHERE chunk_id = ?",
                (chunk_id,)
            )
        except Exception:
            pass  # FTS errors are non-fatal
