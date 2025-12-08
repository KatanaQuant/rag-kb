"""
PostgreSQL + pgvector database layer.

This module provides a clean PostgreSQL implementation replacing SQLite + vectorlite.
Key benefits:
- Full ACID compliance with automatic persistence
- No periodic flush needed (PostgreSQL handles durability)
- Works on all platforms including ARM64
- Built-in connection pooling support
- Proper concurrent access handling

Architecture:
- PostgresConnection: Manages connection lifecycle
- PostgresSchemaManager: Creates/migrates schema
- PostgresVectorRepository: Facade delegating to focused repositories
- PostgresVectorStore: High-level facade for the application
"""
import threading
import logging
from typing import List, Dict, Optional
from pathlib import Path

from config import default_config
from ingestion.interfaces import VectorStore as VectorStoreInterface
from ingestion.postgres_connection import PostgresConnection, PostgresSchemaManager
from ingestion.postgres_repositories import (
    PostgresDocumentRepository,
    PostgresChunkRepository,
    PostgresVectorChunkRepository,
    PostgresFTSChunkRepository,
    PostgresSearchRepository,
    PostgresGraphRepository,
)

logger = logging.getLogger(__name__)


class PostgresVectorRepository:
    """Facade that delegates to focused PostgreSQL repositories.

    Same interface as the SQLite VectorRepository for compatibility.
    """

    def __init__(self, conn):
        self.conn = conn
        self.documents = PostgresDocumentRepository(conn)
        self.chunks = PostgresChunkRepository(conn)
        self.vectors = PostgresVectorChunkRepository(conn)
        self.fts = PostgresFTSChunkRepository(conn)
        self.search_repo = PostgresSearchRepository(conn)
        self.graph = PostgresGraphRepository(conn)

    def is_indexed(self, path: str, hash_val: str) -> bool:
        """Check if document indexed by hash (allows file moves without reindex)"""
        doc = self.documents.find_by_hash(hash_val)
        if not doc:
            return False

        stored_path = doc['file_path']
        if stored_path != path:
            if Path(stored_path).exists():
                pass  # Duplicate file
            else:
                self._update_path_after_move(hash_val, stored_path, path)
                logger.info(f"File moved: {stored_path} -> {path}")

        return True

    def _update_path_after_move(self, hash_val: str, old_path: str, new_path: str):
        """Update file path after move (preserves chunks/embeddings)."""
        try:
            if self._handle_path_conflict(old_path, new_path):
                return
            self._perform_path_update(hash_val, old_path, new_path)
        except Exception as e:
            logger.warning(f"Failed to update path after move: {e}")
            self.conn.rollback()

    def _handle_path_conflict(self, old_path: str, new_path: str) -> bool:
        """Handle case where new_path already exists in DB."""
        existing_at_new_path = self.documents.find_by_path(new_path)
        if not existing_at_new_path:
            return False

        self.graph.delete_note_nodes(old_path)
        self.documents.delete(old_path)
        with self.conn.cursor() as cur:
            cur.execute("DELETE FROM processing_progress WHERE file_path = %s", (old_path,))
        self.conn.commit()
        logger.info(f"Removed stale record: {old_path} (superseded by {new_path})")
        return True

    def _perform_path_update(self, hash_val: str, old_path: str, new_path: str):
        """Perform the actual path update via temp path to avoid UNIQUE constraint."""
        import uuid
        temp_path = f"__temp_move_{uuid.uuid4().hex}__"

        self.documents.update_path_by_hash(hash_val, temp_path)
        with self.conn.cursor() as cur:
            cur.execute(
                "UPDATE processing_progress SET file_path = %s WHERE file_hash = %s",
                (temp_path, hash_val)
            )

        self.documents.update_path_by_hash(hash_val, new_path)
        with self.conn.cursor() as cur:
            cur.execute(
                "UPDATE processing_progress SET file_path = %s WHERE file_hash = %s",
                (new_path, hash_val)
            )

        self.graph.update_note_path(old_path, new_path)
        self.conn.commit()

    def get_extraction_method(self, path: str) -> str:
        """Get extraction method used for a document"""
        return self.documents.get_extraction_method(path)

    def add_document(self, path: str, hash_val: str,
                     chunks: List[Dict], embeddings: List) -> int:
        """Add document with chunks - delegates to repositories"""
        extraction_method = None
        if chunks and '_extraction_method' in chunks[0]:
            extraction_method = chunks[0]['_extraction_method']

        self._delete_old(path)
        doc_id = self.documents.add(path, hash_val, extraction_method)
        self._insert_chunks_delegated(doc_id, chunks, embeddings)
        self.conn.commit()
        return doc_id

    def _delete_old(self, path: str):
        """Remove existing document AND clean up graph nodes"""
        self.graph.delete_note_nodes(path)
        self.documents.delete(path)

    def _insert_chunks_delegated(self, doc_id: int, chunks: List[Dict], embeddings: List):
        """Insert chunks using repositories"""
        for idx, (chunk, emb) in enumerate(zip(chunks, embeddings)):
            chunk_id = self.chunks.add(doc_id, chunk['content'], chunk.get('page'), idx)
            self.vectors.add(chunk_id, emb)
            self.fts.add(chunk_id, chunk['content'])
        logger.info(f"[pgvector] Indexed {len(chunks)} chunks for doc_id={doc_id}")

    def search(self, embedding: List, top_k: int,
               threshold: float = None) -> List[Dict]:
        """Search for similar vectors - delegates to SearchRepository"""
        return self.search_repo.vector_search(embedding, top_k, threshold)

    def get_stats(self) -> Dict:
        """Get database statistics - delegates to repositories"""
        return {
            'indexed_documents': self.documents.count(),
            'total_chunks': self.chunks.count()
        }


class PostgresVectorStore(VectorStoreInterface):
    """Facade for PostgreSQL + pgvector vector storage operations.

    Thread Safety:
    Uses threading.RLock for critical operations. PostgreSQL handles
    concurrent access properly, but we still need the lock for Python-level
    consistency during complex operations.

    Persistence:
    Unlike vectorlite, PostgreSQL persists automatically on commit.
    No periodic flush needed - ACID compliance built-in!

    This dramatically simplifies the code compared to the SQLite version:
    - No flush timer infrastructure
    - No connection cycling
    - No HNSW index file management
    """

    def __init__(self, config=default_config.database):
        self._lock = threading.RLock()
        self._closed = False
        self.config = config
        self.db_conn = PostgresConnection(config)
        self.conn = self.db_conn.connect()
        self._init_schema()
        self.repo = PostgresVectorRepository(self.conn)
        # Import here to avoid circular imports
        from hybrid_search import PostgresHybridSearcher
        self.hybrid = PostgresHybridSearcher(self.conn)
        logger.info("[PostgresVectorStore] Initialized with pgvector")

    def _init_schema(self):
        """Initialize database schema"""
        schema = PostgresSchemaManager(self.conn, self.config)
        schema.create_schema()

    def is_document_indexed(self, path: str, hash_val: str) -> bool:
        """Check if document is indexed."""
        with self._lock:
            return self.repo.is_indexed(path, hash_val)

    def add_document(self, file_path: str, file_hash: str,
                     chunks: List[Dict], embeddings: List):
        """Add document to store.

        PostgreSQL commits automatically persist - no flush needed!
        """
        with self._lock:
            self.repo.add_document(file_path, file_hash, chunks, embeddings)

    def search(self, query_embedding: List, top_k: int = 5,
               threshold: float = None, query_text: Optional[str] = None,
               use_hybrid: bool = True) -> List[Dict]:
        """Search for similar chunks."""
        with self._lock:
            vector_results = self.repo.search(query_embedding, top_k, threshold)

            if use_hybrid and query_text:
                return self.hybrid.search(query_text, vector_results, top_k)
            return vector_results

    def get_stats(self) -> Dict:
        """Get statistics."""
        with self._lock:
            return self.repo.get_stats()

    def get_document_info(self, filename: str) -> Optional[Dict]:
        """Get document information including extraction method."""
        with self._lock:
            docs = self.repo.documents.search_by_pattern(filename)
            if not docs:
                return None
            doc = docs[0]  # Most recent
            return {
                'file_path': doc['file_path'],
                'extraction_method': doc['extraction_method'] or 'unknown',
                'indexed_at': doc['indexed_at']
            }

    def delete_document(self, file_path: str) -> Dict:
        """Delete a document and all its chunks.

        PostgreSQL CASCADE handles vec_chunks and fts_chunks automatically!
        """
        with self._lock:
            doc = self.repo.documents.find_by_path(file_path)
            if not doc:
                return {'found': False, 'chunks_deleted': 0, 'document_deleted': False}

            doc_id = doc['id']
            chunk_count = self.repo.chunks.count_by_document(doc_id)

            # CASCADE handles vec_chunks and fts_chunks
            self.repo.documents.delete_by_id(doc_id)
            self.conn.commit()

            return {
                'found': True,
                'document_id': doc_id,
                'chunks_deleted': chunk_count,
                'document_deleted': True
            }

    def query_documents_with_chunks(self):
        """Query all documents with chunk counts."""
        with self._lock:
            with self.conn.cursor() as cur:
                cur.execute("""
                    SELECT d.file_path, d.indexed_at, COUNT(c.id)
                    FROM documents d
                    LEFT JOIN chunks c ON d.id = c.document_id
                    GROUP BY d.id
                    ORDER BY d.indexed_at DESC
                """)
                return cur.fetchall()

    def close(self):
        """Close connection.

        Unlike vectorlite, no special persistence step needed on close.
        PostgreSQL already persisted everything on commit.
        """
        self._closed = True
        self.db_conn.close()
        logger.info("[PostgresVectorStore] Closed")


# Alias for compatibility - use this as the default VectorStore
VectorStore = PostgresVectorStore
