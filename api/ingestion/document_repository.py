import sqlite3
from pathlib import Path
from typing import Optional, List, Dict
from datetime import datetime

class DocumentRepository:
    """CRUD operations for documents table.

    Single Responsibility: Manage document records only.
    """

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def add(self, path: str, hash_val: str, extraction_method: str = None) -> int:
        """Insert document record and return document ID"""
        cursor = self.conn.execute(
            "INSERT INTO documents (file_path, file_hash, extraction_method) VALUES (?, ?, ?)",
            (path, hash_val, extraction_method)
        )
        return cursor.lastrowid

    def get(self, doc_id: int) -> Optional[Dict]:
        """Get document by ID"""
        cursor = self.conn.execute(
            "SELECT id, file_path, file_hash, indexed_at, extraction_method FROM documents WHERE id = ?",
            (doc_id,)
        )
        result = cursor.fetchone()
        if not result:
            return None

        return {
            'id': result[0],
            'file_path': result[1],
            'file_hash': result[2],
            'indexed_at': result[3],
            'extraction_method': result[4]
        }

    def find_by_path(self, path: str) -> Optional[Dict]:
        """Get document by file path"""
        cursor = self.conn.execute(
            "SELECT id, file_path, file_hash, indexed_at, extraction_method FROM documents WHERE file_path = ?",
            (path,)
        )
        result = cursor.fetchone()
        if not result:
            return None

        return {
            'id': result[0],
            'file_path': result[1],
            'file_hash': result[2],
            'indexed_at': result[3],
            'extraction_method': result[4]
        }

    def find_by_hash(self, hash_val: str) -> Optional[Dict]:
        """Get document by content hash"""
        try:
            cursor = self.conn.execute(
                "SELECT id, file_path, file_hash, indexed_at, extraction_method FROM documents WHERE file_hash = ?",
                (hash_val,)
            )
            result = cursor.fetchone()
            if not result:
                return None

            return {
                'id': result[0],
                'file_path': result[1],
                'file_hash': result[2],
                'indexed_at': result[3],
                'extraction_method': result[4]
            }
        except Exception:
            # Fallback for test databases without all columns
            cursor = self.conn.execute(
                "SELECT id, file_path, file_hash FROM documents WHERE file_hash = ?",
                (hash_val,)
            )
            result = cursor.fetchone()
            if not result:
                return None

            return {
                'id': result[0],
                'file_path': result[1],
                'file_hash': result[2],
                'indexed_at': None,
                'extraction_method': None
            }

    def exists(self, path: str) -> bool:
        """Check if document exists by path"""
        cursor = self.conn.execute(
            "SELECT 1 FROM documents WHERE file_path = ? LIMIT 1",
            (path,)
        )
        return cursor.fetchone() is not None

    def hash_exists(self, hash_val: str) -> bool:
        """Check if document with this hash exists"""
        cursor = self.conn.execute(
            "SELECT 1 FROM documents WHERE file_hash = ? LIMIT 1",
            (hash_val,)
        )
        return cursor.fetchone() is not None

    def update_path(self, old_path: str, new_path: str):
        """Update file path (for file moves)"""
        self.conn.execute(
            "UPDATE documents SET file_path = ? WHERE file_path = ?",
            (new_path, old_path)
        )

    def update_path_by_hash(self, hash_val: str, new_path: str):
        """Update file path by hash (for file moves)"""
        self.conn.execute(
            "UPDATE documents SET file_path = ? WHERE file_hash = ?",
            (new_path, hash_val)
        )

    def delete(self, path: str):
        """Delete document by path (CASCADE deletes chunks)"""
        self.conn.execute(
            "DELETE FROM documents WHERE file_path = ?",
            (path,)
        )

    def delete_by_id(self, doc_id: int):
        """Delete document by ID (CASCADE deletes chunks)"""
        self.conn.execute(
            "DELETE FROM documents WHERE id = ?",
            (doc_id,)
        )

    def list_all(self) -> List[Dict]:
        """Get all documents"""
        cursor = self.conn.execute(
            "SELECT id, file_path, file_hash, indexed_at, extraction_method FROM documents"
        )
        results = []
        for row in cursor.fetchall():
            results.append({
                'id': row[0],
                'file_path': row[1],
                'file_hash': row[2],
                'indexed_at': row[3],
                'extraction_method': row[4]
            })
        return results

    def count(self) -> int:
        """Count total documents"""
        cursor = self.conn.execute("SELECT COUNT(*) FROM documents")
        return cursor.fetchone()[0]

    def get_extraction_method(self, path: str) -> str:
        """Get extraction method used for a document"""
        cursor = self.conn.execute(
            "SELECT extraction_method FROM documents WHERE file_path = ?",
            (path,)
        )
        result = cursor.fetchone()
        return result[0] if result and result[0] else 'unknown'

    def search_by_pattern(self, pattern: str) -> List[Dict]:
        """Search documents by filename pattern"""
        cursor = self.conn.execute("""
            SELECT id, file_path, file_hash, indexed_at, extraction_method
            FROM documents
            WHERE file_path LIKE ?
            ORDER BY indexed_at DESC
        """, (f"%{pattern}%",))

        results = []
        for row in cursor.fetchall():
            results.append({
                'id': row[0],
                'file_path': row[1],
                'file_hash': row[2],
                'indexed_at': row[3],
                'extraction_method': row[4]
            })
        return results
