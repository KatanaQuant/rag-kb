"""
Async database layer for non-blocking API operations.

This module provides async versions of database classes using aiosqlite.
The design mirrors the synchronous database.py to maintain consistency.

Architecture:
- AsyncDatabaseConnection: Manages async SQLite connection and extensions
- AsyncSchemaManager: Creates database schema asynchronously
- AsyncVectorRepository: Async facade delegating to async repositories
- AsyncVectorStore: Main async facade for vector storage operations

All classes follow the same POODR principles as their synchronous counterparts.
"""

import aiosqlite
from pathlib import Path
from typing import List, Dict, Optional
import numpy as np
import logging

from config import default_config
from domain_models import ChunkData, DocumentFile, ExtractionResult

# Suppress verbose warnings
logging.getLogger('pdfminer').setLevel(logging.CRITICAL)
logging.getLogger('PIL').setLevel(logging.CRITICAL)
logging.getLogger('docling').setLevel(logging.CRITICAL)


class AsyncDatabaseConnection:
    """Manages async SQLite connection and extensions.

    Mirrors DatabaseConnection from database.py but uses aiosqlite.
    """

    def __init__(self, config=default_config.database):
        self.config = config
        self.conn = None

    async def connect(self) -> aiosqlite.Connection:
        """Establish async database connection"""
        self.conn = await self._create_connection()
        # Enable WAL mode for better concurrency (allows concurrent reads during writes)
        await self.conn.execute("PRAGMA journal_mode=WAL")
        await self.conn.execute("PRAGMA busy_timeout=5000")  # Wait up to 5s for locks
        await self._load_extension()
        return self.conn

    async def _create_connection(self) -> aiosqlite.Connection:
        """Create async SQLite connection"""
        return await aiosqlite.connect(
            self.config.path,
            check_same_thread=False  # aiosqlite handles threading
        )

    async def _load_extension(self):
        """Load vector extension"""
        if not self.config.require_vec_extension:
            return
        await self._load_python_bindings()

    async def _load_python_bindings(self):
        """Load sqlite-vec using Python bindings

        Note: aiosqlite doesn't support enable_load_extension() directly,
        so we use the Python bindings which are already in use.
        """
        try:
            import sqlite_vec
            # Access underlying sqlite3.Connection to load extension
            # aiosqlite wraps sqlite3.Connection as ._conn
            sqlite_vec.load(self.conn._conn)
        except Exception as e:
            raise RuntimeError(f"sqlite-vec failed: {e}")

    async def close(self):
        """Close connection"""
        if self.conn:
            await self.conn.close()


class AsyncSchemaManager:
    """Manages database schema asynchronously.

    Mirrors SchemaManager from database.py but uses async operations.
    """

    def __init__(self, conn: aiosqlite.Connection, config=default_config.database):
        self.conn = conn
        self.config = config

    async def create_schema(self):
        """Create all required tables"""
        await self._create_documents_table()
        await self._create_chunks_table()
        await self._create_vector_table()
        await self._create_fts_table()
        await self._create_processing_progress_table()
        await self._create_graph_tables()
        await self.conn.commit()

    async def _create_documents_table(self):
        """Create documents table"""
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT UNIQUE NOT NULL,
                file_hash TEXT NOT NULL,
                indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                extraction_method TEXT
            )
        """)

        # Migration: Add extraction_method column if it doesn't exist
        try:
            await self.conn.execute("""
                ALTER TABLE documents ADD COLUMN extraction_method TEXT
            """)
            print("Migration: Added extraction_method column to documents table")
        except Exception:
            pass  # Column already exists

    async def _create_chunks_table(self):
        """Create chunks table"""
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                page INTEGER,
                chunk_index INTEGER,
                FOREIGN KEY (document_id)
                    REFERENCES documents(id)
                    ON DELETE CASCADE
            )
        """)

    async def _create_vector_table(self):
        """Create vector embeddings table"""
        try:
            await self._execute_create_vec_table()
        except Exception as e:
            print(f"Note: vec_chunks exists: {e}")

    async def _execute_create_vec_table(self):
        """Execute vector table creation"""
        await self.conn.execute(f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks
            USING vec0(
                chunk_id INTEGER PRIMARY KEY,
                embedding FLOAT[{self.config.embedding_dim}]
            )
        """)

    async def _create_fts_table(self):
        """Create FTS5 full-text search table"""
        try:
            await self.conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS fts_chunks
                USING fts5(
                    chunk_id UNINDEXED,
                    content,
                    content='',
                    contentless_delete=1
                )
            """)
        except Exception as e:
            print(f"Note: fts_chunks exists: {e}")

    async def _create_processing_progress_table(self):
        """Create processing progress tracking table"""
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS processing_progress (
                file_path TEXT PRIMARY KEY,
                file_hash TEXT,
                total_chunks INTEGER DEFAULT 0,
                chunks_processed INTEGER DEFAULT 0,
                status TEXT DEFAULT 'in_progress',
                last_chunk_end INTEGER DEFAULT 0,
                error_message TEXT,
                started_at TEXT,
                last_updated TEXT,
                completed_at TEXT
            )
        """)

    async def _create_graph_tables(self):
        """Create knowledge graph tables for Obsidian Graph-RAG"""
        await self._create_graph_nodes_table()
        await self._create_graph_edges_table()
        await self._create_edge_indices()
        await self._create_graph_metadata_table()
        await self._create_chunk_graph_links_table()
        print("Graph-RAG tables initialized (existing data preserved)")

    async def _create_graph_nodes_table(self):
        """Create table for graph nodes (notes, tags, headers, concepts)"""
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS graph_nodes (
                node_id TEXT PRIMARY KEY,
                node_type TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

    async def _create_graph_edges_table(self):
        """Create table for graph edges (wikilinks, tags, headers)"""
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS graph_edges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                edge_type TEXT NOT NULL,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (source_id) REFERENCES graph_nodes(node_id) ON DELETE CASCADE,
                FOREIGN KEY (target_id) REFERENCES graph_nodes(node_id) ON DELETE CASCADE
            )
        """)

    async def _create_edge_indices(self):
        """Create indices for fast edge lookups"""
        await self.conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_source ON graph_edges(source_id)")
        await self.conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_target ON graph_edges(target_id)")
        await self.conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_type ON graph_edges(edge_type)")

    async def _create_graph_metadata_table(self):
        """Create table for graph metrics (PageRank, degree)"""
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS graph_metadata (
                node_id TEXT PRIMARY KEY,
                pagerank_score REAL,
                in_degree INTEGER,
                out_degree INTEGER,
                last_computed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (node_id) REFERENCES graph_nodes(node_id) ON DELETE CASCADE
            )
        """)

    async def _create_chunk_graph_links_table(self):
        """Create table linking chunks to graph nodes"""
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS chunk_graph_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chunk_id INTEGER NOT NULL,
                node_id TEXT NOT NULL,
                link_type TEXT DEFAULT 'primary',
                FOREIGN KEY (chunk_id) REFERENCES chunks(id) ON DELETE CASCADE,
                FOREIGN KEY (node_id) REFERENCES graph_nodes(node_id) ON DELETE CASCADE
            )
        """)
        await self.conn.execute("CREATE INDEX IF NOT EXISTS idx_chunk_graph_chunk ON chunk_graph_links(chunk_id)")
        await self.conn.execute("CREATE INDEX IF NOT EXISTS idx_chunk_graph_node ON chunk_graph_links(node_id)")


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
        """Update file path after move (preserves chunks/embeddings)"""
        try:
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

            # Note: GraphRepository is still sync, skip for now
            # from ingestion.graph_repository import GraphRepository
            # graph_repo = GraphRepository(self.conn)
            # graph_repo.update_note_path(old_path, new_path)

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
        """Search for similar chunks"""
        vector_results = await self.repo.search(query_embedding, top_k, threshold)

        # if use_hybrid and query_text and self.hybrid:
        #     return await self.hybrid.search(query_text, vector_results, top_k)
        return vector_results

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
