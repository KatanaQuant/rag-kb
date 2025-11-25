"""
Async repository classes for non-blocking database operations.

These classes mirror the synchronous repositories from document_repository.py,
chunk_repository.py, and search_repository.py but use aiosqlite for async I/O.

Following POODR principles:
- Single Responsibility: Each repository handles one table/concern
- Dependency Injection: Accept connection in constructor
- Interface Segregation: Separate repositories for different operations
"""

import aiosqlite
from pathlib import Path
from typing import Optional, List, Dict
import numpy as np


class AsyncDocumentRepository:
    """CRUD operations for documents table (async version).

    Single Responsibility: Manage document records only.
    Mirrors DocumentRepository from document_repository.py
    """

    def __init__(self, conn: aiosqlite.Connection):
        self.conn = conn

    async def add(self, path: str, hash_val: str, extraction_method: str = None) -> int:
        """Insert document record and return document ID"""
        cursor = await self.conn.execute(
            "INSERT INTO documents (file_path, file_hash, extraction_method) VALUES (?, ?, ?)",
            (path, hash_val, extraction_method)
        )
        return cursor.lastrowid

    async def get(self, doc_id: int) -> Optional[Dict]:
        """Get document by ID"""
        cursor = await self.conn.execute(
            "SELECT id, file_path, file_hash, indexed_at, extraction_method FROM documents WHERE id = ?",
            (doc_id,)
        )
        result = await cursor.fetchone()
        if not result:
            return None

        return {
            'id': result[0],
            'file_path': result[1],
            'file_hash': result[2],
            'indexed_at': result[3],
            'extraction_method': result[4]
        }

    async def find_by_path(self, path: str) -> Optional[Dict]:
        """Get document by file path"""
        cursor = await self.conn.execute(
            "SELECT id, file_path, file_hash, indexed_at, extraction_method FROM documents WHERE file_path = ?",
            (path,)
        )
        result = await cursor.fetchone()
        if not result:
            return None

        return {
            'id': result[0],
            'file_path': result[1],
            'file_hash': result[2],
            'indexed_at': result[3],
            'extraction_method': result[4]
        }

    async def find_by_hash(self, hash_val: str) -> Optional[Dict]:
        """Get document by content hash"""
        try:
            cursor = await self.conn.execute(
                "SELECT id, file_path, file_hash, indexed_at, extraction_method FROM documents WHERE file_hash = ?",
                (hash_val,)
            )
            result = await cursor.fetchone()
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
            cursor = await self.conn.execute(
                "SELECT id, file_path, file_hash FROM documents WHERE file_hash = ?",
                (hash_val,)
            )
            result = await cursor.fetchone()
            if not result:
                return None

            return {
                'id': result[0],
                'file_path': result[1],
                'file_hash': result[2],
                'indexed_at': None,
                'extraction_method': None
            }

    async def exists(self, path: str) -> bool:
        """Check if document exists by path"""
        cursor = await self.conn.execute(
            "SELECT 1 FROM documents WHERE file_path = ? LIMIT 1",
            (path,)
        )
        result = await cursor.fetchone()
        return result is not None

    async def hash_exists(self, hash_val: str) -> bool:
        """Check if document with this hash exists"""
        cursor = await self.conn.execute(
            "SELECT 1 FROM documents WHERE file_hash = ? LIMIT 1",
            (hash_val,)
        )
        result = await cursor.fetchone()
        return result is not None

    async def update_path(self, old_path: str, new_path: str):
        """Update file path (for file moves)"""
        await self.conn.execute(
            "UPDATE documents SET file_path = ? WHERE file_path = ?",
            (new_path, old_path)
        )

    async def update_path_by_hash(self, hash_val: str, new_path: str):
        """Update file path by hash (for file moves)"""
        await self.conn.execute(
            "UPDATE documents SET file_path = ? WHERE file_hash = ?",
            (new_path, hash_val)
        )

    async def delete(self, path: str):
        """Delete document by path (CASCADE deletes chunks)"""
        await self.conn.execute(
            "DELETE FROM documents WHERE file_path = ?",
            (path,)
        )

    async def delete_by_id(self, doc_id: int):
        """Delete document by ID (CASCADE deletes chunks)"""
        await self.conn.execute(
            "DELETE FROM documents WHERE id = ?",
            (doc_id,)
        )

    async def list_all(self) -> List[Dict]:
        """Get all documents"""
        cursor = await self.conn.execute(
            "SELECT id, file_path, file_hash, indexed_at, extraction_method FROM documents"
        )
        results = []
        async for row in cursor:
            results.append({
                'id': row[0],
                'file_path': row[1],
                'file_hash': row[2],
                'indexed_at': row[3],
                'extraction_method': row[4]
            })
        return results

    async def count(self) -> int:
        """Count total documents"""
        cursor = await self.conn.execute("SELECT COUNT(*) FROM documents")
        result = await cursor.fetchone()
        return result[0]

    async def get_extraction_method(self, path: str) -> str:
        """Get extraction method used for a document"""
        cursor = await self.conn.execute(
            "SELECT extraction_method FROM documents WHERE file_path = ?",
            (path,)
        )
        result = await cursor.fetchone()
        return result[0] if result and result[0] else 'unknown'

    async def search_by_pattern(self, pattern: str) -> List[Dict]:
        """Search documents by filename pattern"""
        cursor = await self.conn.execute("""
            SELECT id, file_path, file_hash, indexed_at, extraction_method
            FROM documents
            WHERE file_path LIKE ?
            ORDER BY indexed_at DESC
        """, (f"%{pattern}%",))

        results = []
        async for row in cursor:
            results.append({
                'id': row[0],
                'file_path': row[1],
                'file_hash': row[2],
                'indexed_at': row[3],
                'extraction_method': row[4]
            })
        return results


class AsyncChunkRepository:
    """CRUD operations for chunks table (async version).

    Single Responsibility: Manage text chunks only.
    Mirrors ChunkRepository from chunk_repository.py
    """

    def __init__(self, conn: aiosqlite.Connection):
        self.conn = conn

    async def add(self, doc_id: int, content: str, page: Optional[int], chunk_index: int) -> int:
        """Insert single chunk and return chunk ID"""
        cursor = await self.conn.execute(
            """INSERT INTO chunks (document_id, content, page, chunk_index)
               VALUES (?, ?, ?, ?)""",
            (doc_id, content, page, chunk_index)
        )
        return cursor.lastrowid

    async def add_batch(self, doc_id: int, chunks: List[Dict]) -> List[int]:
        """Insert multiple chunks and return their IDs"""
        chunk_ids = []
        for idx, chunk in enumerate(chunks):
            chunk_id = await self.add(
                doc_id,
                chunk['content'],
                chunk.get('page'),
                idx
            )
            chunk_ids.append(chunk_id)
        return chunk_ids

    async def get(self, chunk_id: int) -> Optional[Dict]:
        """Get chunk by ID"""
        cursor = await self.conn.execute(
            "SELECT id, document_id, content, page, chunk_index FROM chunks WHERE id = ?",
            (chunk_id,)
        )
        result = await cursor.fetchone()
        if not result:
            return None

        return {
            'id': result[0],
            'document_id': result[1],
            'content': result[2],
            'page': result[3],
            'chunk_index': result[4]
        }

    async def get_by_document(self, doc_id: int) -> List[Dict]:
        """Get all chunks for a document"""
        cursor = await self.conn.execute(
            "SELECT id, document_id, content, page, chunk_index FROM chunks WHERE document_id = ? ORDER BY chunk_index",
            (doc_id,)
        )
        results = []
        async for row in cursor:
            results.append({
                'id': row[0],
                'document_id': row[1],
                'content': row[2],
                'page': row[3],
                'chunk_index': row[4]
            })
        return results

    async def count_by_document(self, doc_id: int) -> int:
        """Count chunks for a document"""
        cursor = await self.conn.execute(
            "SELECT COUNT(*) FROM chunks WHERE document_id = ?",
            (doc_id,)
        )
        result = await cursor.fetchone()
        return result[0]

    async def delete_by_document(self, doc_id: int) -> int:
        """Delete all chunks for a document and return count deleted"""
        count = await self.count_by_document(doc_id)
        await self.conn.execute("DELETE FROM chunks WHERE document_id = ?", (doc_id,))
        return count

    async def update(self, chunk_id: int, content: str = None, page: int = None):
        """Update chunk content or page"""
        if content is not None:
            await self.conn.execute(
                "UPDATE chunks SET content = ? WHERE id = ?",
                (content, chunk_id)
            )
        if page is not None:
            await self.conn.execute(
                "UPDATE chunks SET page = ? WHERE id = ?",
                (page, chunk_id)
            )

    async def count(self) -> int:
        """Count total chunks across all documents"""
        cursor = await self.conn.execute("SELECT COUNT(*) FROM chunks")
        result = await cursor.fetchone()
        return result[0]

    async def exists(self, chunk_id: int) -> bool:
        """Check if chunk exists"""
        cursor = await self.conn.execute(
            "SELECT 1 FROM chunks WHERE id = ? LIMIT 1",
            (chunk_id,)
        )
        result = await cursor.fetchone()
        return result is not None


class AsyncVectorChunkRepository:
    """CRUD operations for vector embeddings (async version).

    Single Responsibility: Manage vector embeddings for chunks.
    Mirrors VectorChunkRepository from chunk_repository.py
    """

    def __init__(self, conn: aiosqlite.Connection):
        self.conn = conn

    async def add(self, chunk_id: int, embedding: List[float]):
        """Insert vector embedding for a chunk"""
        blob = self._to_blob(embedding)
        await self.conn.execute(
            "INSERT INTO vec_chunks (chunk_id, embedding) VALUES (?, ?)",
            (chunk_id, blob)
        )

    async def add_batch(self, chunk_ids: List[int], embeddings: List[List[float]]):
        """Insert multiple vector embeddings"""
        for chunk_id, embedding in zip(chunk_ids, embeddings):
            await self.add(chunk_id, embedding)

    async def delete_by_chunk(self, chunk_id: int):
        """Delete vector for a chunk"""
        await self.conn.execute(
            "DELETE FROM vec_chunks WHERE chunk_id = ?",
            (chunk_id,)
        )

    @staticmethod
    def _to_blob(embedding: List[float]) -> bytes:
        """Convert embedding list to binary blob"""
        arr = np.array(embedding, dtype=np.float32)
        return arr.tobytes()


class AsyncFTSChunkRepository:
    """CRUD operations for full-text search index (async version).

    Single Responsibility: Manage FTS5 index for chunks.
    Mirrors FTSChunkRepository from chunk_repository.py
    """

    def __init__(self, conn: aiosqlite.Connection):
        self.conn = conn

    async def add(self, chunk_id: int, content: str):
        """Insert chunk into FTS5 index"""
        try:
            await self.conn.execute(
                "INSERT INTO fts_chunks (chunk_id, content) VALUES (?, ?)",
                (chunk_id, content)
            )
        except Exception:
            pass  # FTS errors are non-fatal

    async def add_batch(self, chunk_ids: List[int], contents: List[str]):
        """Insert multiple chunks into FTS5 index"""
        for chunk_id, content in zip(chunk_ids, contents):
            await self.add(chunk_id, content)

    async def delete_by_chunk(self, chunk_id: int):
        """Delete chunk from FTS5 index"""
        try:
            await self.conn.execute(
                "DELETE FROM fts_chunks WHERE chunk_id = ?",
                (chunk_id,)
            )
        except Exception:
            pass  # FTS errors are non-fatal


class AsyncSearchRepository:
    """Vector and hybrid search operations (async version).

    Single Responsibility: Execute search queries only.
    Mirrors SearchRepository from search_repository.py
    """

    def __init__(self, conn: aiosqlite.Connection):
        self.conn = conn

    async def vector_search(self, embedding: List[float], top_k: int, threshold: float = None) -> List[Dict]:
        """Search for similar vectors using cosine similarity"""
        blob = self._to_blob(embedding)
        results = await self._execute_vector_search(blob, top_k)
        return self._format_results(results, threshold)

    async def _execute_vector_search(self, blob: bytes, top_k: int):
        """Execute vector similarity query"""
        cursor = await self.conn.execute("""
            SELECT c.content, d.file_path, c.page,
                   vec_distance_cosine(v.embedding, ?) as dist
            FROM vec_chunks v
            JOIN chunks c ON v.chunk_id = c.id
            JOIN documents d ON c.document_id = d.id
            ORDER BY dist ASC
            LIMIT ?
        """, (blob, top_k))
        return await cursor.fetchall()

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
