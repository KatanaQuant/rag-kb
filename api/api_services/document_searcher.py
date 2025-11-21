from typing import List
from hybrid_search import HybridSearcher


class DocumentSearcher:
    """Searches for documents in database"""

    def search(self, pattern: str = None) -> dict:
        """Search documents by pattern"""
        results = self._query_documents(pattern)
        documents = self._format_results(results)
        return self._build_response(pattern, documents)

    def _query_documents(self, pattern: str = None):
        """Query documents with optional pattern"""
        import sqlite3
        conn = sqlite3.connect(default_config.database.path)

        if pattern:
            results = self._search_with_pattern(conn, pattern)
        else:
            results = self._list_all_documents(conn)

        conn.close()
        return results

    def _search_with_pattern(self, conn, pattern: str):
        """Search with pattern filter"""
        cursor = conn.execute("""
            SELECT d.id, d.file_path, d.file_hash, d.indexed_at, COUNT(c.id) as chunk_count
            FROM documents d
            LEFT JOIN chunks c ON d.id = c.document_id
            WHERE d.file_path LIKE ?
            GROUP BY d.id
            ORDER BY d.indexed_at DESC
        """, (f"%{pattern}%",))
        return cursor.fetchall()

    def _list_all_documents(self, conn):
        """List all documents"""
        cursor = conn.execute("""
            SELECT d.id, d.file_path, d.file_hash, d.indexed_at, COUNT(c.id) as chunk_count
            FROM documents d
            LEFT JOIN chunks c ON d.id = c.document_id
            GROUP BY d.id
            ORDER BY d.indexed_at DESC
        """)
        return cursor.fetchall()

    def _format_results(self, results):
        """Format query results"""
        return [self._format_row(row) for row in results]

    def _format_row(self, row) -> dict:
        """Format single row"""
        return {
            "id": row[0],
            "file_path": row[1],
            "file_name": row[1].split('/')[-1],
            "file_hash": row[2],
            "indexed_at": row[3],
            "chunk_count": row[4]
        }

    def _build_response(self, pattern, documents):
        """Build search response"""
        return {
            "pattern": pattern,
            "total_matches": len(documents),
            "documents": documents
        }

