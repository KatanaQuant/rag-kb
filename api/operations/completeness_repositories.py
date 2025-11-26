"""Repository classes for completeness/integrity checking

These repositories are designed for read-only API queries and manage
their own database connections. They support batch preloading to
avoid N+1 query problems.

Note: These are separate from ingestion/document_repository.py and
ingestion/chunk_repository.py which take an existing connection for
transaction management during writes.
"""
import sqlite3
from typing import Dict, List, Optional


class DocumentRepository:
    """Read-only repository for document queries

    Used by CompletenessReporter to list documents.
    Manages its own database connection.
    """

    def __init__(self, db_path: str):
        self.db_path = db_path

    def list_all(self) -> List[Dict]:
        """List all documents"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("""
            SELECT id, file_path, file_hash, indexed_at
            FROM documents
            ORDER BY indexed_at DESC
        """)
        documents = [self._row_to_dict(row) for row in cursor.fetchall()]
        conn.close()
        return documents

    def find_by_path(self, file_path: str) -> Optional[Dict]:
        """Find document by path"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "SELECT id, file_path, file_hash, indexed_at FROM documents WHERE file_path = ?",
            (file_path,)
        )
        row = cursor.fetchone()
        conn.close()
        return self._row_to_dict(row) if row else None

    @staticmethod
    def _row_to_dict(row) -> Dict:
        """Convert row to dict"""
        return {
            'id': row[0],
            'file_path': row[1],
            'file_hash': row[2],
            'indexed_at': row[3]
        }


class ChunkRepository:
    """Read-only repository for chunk queries with caching

    Used by CompletenessReporter to count chunks.
    Supports batch preloading to fix N+1 query problem.
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._chunk_counts_cache: dict = None

    def count_by_document(self, document_id: int) -> int:
        """Count chunks for document (uses cache if available)"""
        if self._chunk_counts_cache is not None:
            return self._chunk_counts_cache.get(document_id, 0)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "SELECT COUNT(*) FROM chunks WHERE document_id = ?",
            (document_id,)
        )
        count = cursor.fetchone()[0]
        conn.close()
        return count

    def preload_all_counts(self) -> None:
        """Preload all chunk counts in single query (fixes N+1)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("""
            SELECT document_id, COUNT(*) as chunk_count
            FROM chunks
            GROUP BY document_id
        """)
        self._chunk_counts_cache = {row[0]: row[1] for row in cursor.fetchall()}
        conn.close()

    def clear_cache(self) -> None:
        """Clear the chunk counts cache"""
        self._chunk_counts_cache = None
