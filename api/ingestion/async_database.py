"""
Async database layer for non-blocking API operations.

Architecture:
- AsyncDatabaseConnection: Connection management (async_connection.py)
- AsyncSchemaManager: Schema management (async_schema.py)
- AsyncVectorRepository: Async facade delegating to async repositories
- AsyncVectorStore: Main async facade for vector storage operations

Vector Search: Uses vectorlite HNSW index for O(log n) approximate nearest
neighbor search. No in-memory loading required - index persists on disk.
"""

import aiosqlite
from pathlib import Path
from typing import List, Dict, Optional
import numpy as np
import logging

from config import default_config
from domain_models import ChunkData, DocumentFile, ExtractionResult
from .async_connection import AsyncDatabaseConnection
from .async_schema import AsyncSchemaManager

# Centralized logging configuration - import triggers suppression
from . import logging_config  # noqa: F401


class AsyncVectorRepository:
    """Async facade that delegates to focused repositories.

    Mirrors VectorRepository from database.py but uses async operations.
    Maintains same interface for compatibility.
    """

    def __init__(self, conn: aiosqlite.Connection):
        from ingestion.async_repositories import (
            AsyncDocumentRepository,
            AsyncChunkRepository,
            AsyncVectorChunkRepository,
            AsyncFTSChunkRepository,
            AsyncSearchRepository
        )

        self.conn = conn
        self.documents = AsyncDocumentRepository(conn)
        self.chunks = AsyncChunkRepository(conn)
        self.vectors = AsyncVectorChunkRepository(conn)
        self.fts = AsyncFTSChunkRepository(conn)
        self.search_repo = AsyncSearchRepository(conn)

    async def is_indexed(self, path: str, hash_val: str) -> bool:
        """Check if document indexed by hash (allows file moves without reindex)"""
        doc = await self.documents.find_by_hash(hash_val)
        if not doc:
            return False

        stored_path = doc['file_path']
        if stored_path != path:
            from pathlib import Path
            if Path(stored_path).exists():
                pass  # Duplicate file
            else:
                await self._update_path_after_move(hash_val, stored_path, path)
                print(f"File moved: {stored_path} -> {path}")

        return True

    async def _update_path_after_move(self, hash_val: str, old_path: str, new_path: str):
        """Update file path after move (preserves chunks/embeddings)

        Handles case where new_path already exists in DB (duplicate/conflict):
        - If new_path exists, delete the old record (old_path) instead of updating
        - This keeps the existing record at new_path intact
        """
        try:
            # Check if new_path already exists in the database
            existing_at_new_path = await self.documents.find_by_path(new_path)
            if existing_at_new_path:
                # new_path already has a document - delete the OLD record instead
                # The document at new_path is already correct (same content, new location)
                await self.documents.delete(old_path)
                await self.conn.execute(
                    "DELETE FROM processing_progress WHERE file_path = ?",
                    (old_path,)
                )
                await self.conn.commit()
                print(f"  Removed stale record: {old_path} (superseded by {new_path})")
                return

            # Normal case: new_path doesn't exist, update the path
            import uuid
            temp_path = f"__temp_move_{uuid.uuid4().hex}__"

            await self.documents.update_path_by_hash(hash_val, temp_path)
            await self.conn.execute(
                "UPDATE processing_progress SET file_path = ? WHERE file_hash = ?",
                (temp_path, hash_val)
            )

            await self.documents.update_path_by_hash(hash_val, new_path)
            await self.conn.execute(
                "UPDATE processing_progress SET file_path = ? WHERE file_hash = ?",
                (new_path, hash_val)
            )

            await self.conn.commit()
        except Exception as e:
            print(f"Warning: Failed to update path after move: {e}")
            await self.conn.rollback()

    async def get_extraction_method(self, path: str) -> str:
        """Get extraction method used for a document"""
        return await self.documents.get_extraction_method(path)

    async def add_document(self, path: str, hash_val: str,
                          chunks: List[Dict], embeddings: List) -> int:
        """Add document with chunks - delegates to repositories"""
        extraction_method = None
        if chunks and '_extraction_method' in chunks[0]:
            extraction_method = chunks[0]['_extraction_method']

        await self._delete_old(path)
        doc_id = await self.documents.add(path, hash_val, extraction_method)
        await self._insert_chunks_delegated(doc_id, chunks, embeddings)
        await self.conn.commit()
        return doc_id

    async def _delete_old(self, path: str):
        """Remove existing document AND clean up graph nodes"""
        # Note: GraphRepository is still sync, skip for now
        # from ingestion.graph_repository import GraphRepository
        # graph_repo = GraphRepository(self.conn)
        # graph_repo.delete_note_nodes(path)
        await self.documents.delete(path)

    async def _insert_chunks_delegated(self, doc_id: int, chunks: List[Dict], embeddings: List):
        """Insert chunks using async repositories"""
        for idx, (chunk, emb) in enumerate(zip(chunks, embeddings)):
            chunk_id = await self.chunks.add(doc_id, chunk['content'], chunk.get('page'), idx)
            await self.vectors.add(chunk_id, emb)
            await self.fts.add(chunk_id, chunk['content'])

    async def search(self, embedding: List, top_k: int,
                    threshold: float = None) -> List[Dict]:
        """Search for similar vectors - delegates to SearchRepository"""
        return await self.search_repo.vector_search(embedding, top_k, threshold)

    async def get_stats(self) -> Dict:
        """Get database statistics - delegates to repositories"""
        return {
            'indexed_documents': await self.documents.count(),
            'total_chunks': await self.chunks.count()
        }


class AsyncVectorStore:
    """Async facade for vector storage operations.

    Mirrors VectorStore from database.py but uses async operations.
    Must call initialize() after construction since __init__ can't be async.

    Performance: Uses vectorlite HNSW index for O(log n) approximate nearest
    neighbor search. Index persists on disk - no memory loading required.
    Startup: ~1s (was 42s with NumPy workaround)
    Query: ~0.3s (same as NumPy, but without memory overhead)
    """

    def __init__(self, config=default_config.database):
        self.config = config
        self.db_conn = None
        self.conn = None
        self.repo = None
        self.hybrid = None

    async def initialize(self):
        """Initialize async connections and repositories.

        Must be called after construction since __init__ can't be async.
        vectorlite uses persistent HNSW index - no memory loading required.
        """
        self.db_conn = AsyncDatabaseConnection(self.config)
        self.conn = await self.db_conn.connect()
        await self._init_schema()
        self.repo = AsyncVectorRepository(self.conn)
        # Note: HybridSearcher needs async version too
        # self.hybrid = AsyncHybridSearcher(self.conn)

    async def _init_schema(self):
        """Initialize database schema"""
        schema = AsyncSchemaManager(self.conn, self.config)
        await schema.create_schema()

    async def is_document_indexed(self, path: str, hash_val: str) -> bool:
        """Check if document is indexed"""
        return await self.repo.is_indexed(path, hash_val)

    async def add_document(self, file_path: str, file_hash: str,
                          chunks: List[Dict], embeddings: List):
        """Add document to store"""
        await self.repo.add_document(file_path, file_hash, chunks, embeddings)

    async def search(self, query_embedding: List, top_k: int = 5,
                    threshold: float = None, query_text: Optional[str] = None,
                    use_hybrid: bool = True) -> List[Dict]:
        """Search for similar chunks using vectorlite HNSW index.

        Performance: ~0.3s per query with O(log n) approximate nearest neighbor.
        """
        return await self.repo.search(query_embedding, top_k, threshold)

    async def get_stats(self) -> Dict:
        """Get statistics"""
        return await self.repo.get_stats()

    async def get_document_info(self, filename: str) -> Dict:
        """Get document information including extraction method"""
        cursor = await self.conn.execute("""
            SELECT file_path, extraction_method, indexed_at
            FROM documents
            WHERE file_path LIKE ?
            ORDER BY indexed_at DESC
            LIMIT 1
        """, (f"%{filename}%",))
        result = await cursor.fetchone()

        if not result:
            return None

        return {
            'file_path': result[0],
            'extraction_method': result[1] or 'unknown',
            'indexed_at': result[2]
        }

    async def delete_document(self, file_path: str) -> Dict:
        """Delete a document and all its chunks from the vector store"""
        doc_id = await self._find_document_id(file_path)
        if not doc_id:
            return self._document_not_found_result()

        chunk_count = await self._count_document_chunks(doc_id)
        await self._delete_document_data(doc_id)
        await self.conn.commit()
        return self._deletion_success_result(doc_id, chunk_count)

    async def _find_document_id(self, file_path: str):
        """Find document ID by file path"""
        cursor = await self.conn.execute("SELECT id FROM documents WHERE file_path = ?", (file_path,))
        result = await cursor.fetchone()
        return result[0] if result else None

    def _document_not_found_result(self) -> Dict:
        """Return result for document not found"""
        return {'found': False, 'chunks_deleted': 0, 'document_deleted': False}

    async def _count_document_chunks(self, doc_id: int) -> int:
        """Count chunks for document"""
        cursor = await self.conn.execute("SELECT COUNT(*) FROM chunks WHERE document_id = ?", (doc_id,))
        result = await cursor.fetchone()
        return result[0]

    async def _delete_document_data(self, doc_id: int):
        """Delete chunks and document record"""
        await self.conn.execute("DELETE FROM chunks WHERE document_id = ?", (doc_id,))
        await self.conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))

    def _deletion_success_result(self, doc_id: int, chunk_count: int) -> Dict:
        """Return success result for deletion"""
        return {
            'found': True,
            'document_id': doc_id,
            'chunks_deleted': chunk_count,
            'document_deleted': True
        }

    async def query_documents_with_chunks(self):
        """Query all documents with chunk counts.

        Delegation method to avoid Law of Demeter violation.
        Returns cursor for documents joined with chunk counts.
        """
        return await self.conn.execute("""
            SELECT d.file_path, d.indexed_at, COUNT(c.id)
            FROM documents d
            LEFT JOIN chunks c ON d.id = c.document_id
            GROUP BY d.id
            ORDER BY d.indexed_at DESC
        """)

    async def close(self):
        """Close connection"""
        if self.db_conn:
            await self.db_conn.close()
