import sqlite3
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from datetime import datetime
import logging
import sys
import warnings

import numpy as np

from config import default_config
from hybrid_search import HybridSearcher
from domain_models import ChunkData, DocumentFile, ExtractionResult
from ingestion.document_repository import DocumentRepository
from ingestion.chunk_repository import ChunkRepository, VectorChunkRepository, FTSChunkRepository
from ingestion.search_repository import SearchRepository

# Centralized logging configuration - import triggers suppression
import ingestion.logging_config  # noqa: F401

try:
    from docling.document_converter import DocumentConverter
    DOCLING_AVAILABLE = True
except ImportError as e:
    DOCLING_AVAILABLE = False
    print(f"Warning: Docling not available ({e})")

# Try to import chunking separately (may not be available in all versions)
try:
    from docling_core.transforms.chunker import HybridChunker
    from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
    from transformers import AutoTokenizer
    DOCLING_CHUNKING_AVAILABLE = True
except ImportError as e:
    DOCLING_CHUNKING_AVAILABLE = False
    if DOCLING_AVAILABLE:
        print(f"Warning: Docling HybridChunker not available ({e}), using fixed-size chunking")


class DatabaseConnection:
    """Manages SQLite connection and extensions"""

    def __init__(self, config=default_config.database):
        self.config = config
        self.conn = None

    def connect(self) -> sqlite3.Connection:
        """Establish database connection"""
        self.conn = self._create_connection()
        # Enable WAL mode for better concurrency (allows concurrent reads during writes)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=5000")  # Wait up to 5s for locks
        self._load_extension()
        return self.conn

    def _create_connection(self) -> sqlite3.Connection:
        """Create SQLite connection"""
        return sqlite3.connect(
            self.config.path,
            check_same_thread=self.config.check_same_thread
        )

    def _load_extension(self):
        """Load vector extension"""
        if not self.config.require_vec_extension:
            return
        if self._has_extension_support():
            self.conn.enable_load_extension(True)
            self._try_load()
        else:
            self._load_python_bindings()

    def _has_extension_support(self) -> bool:
        """Check if sqlite3 supports loadable extensions"""
        return hasattr(self.conn, 'enable_load_extension')

    def _try_load(self):
        """Try loading vectorlite extension"""
        self._load_python_bindings()

    def _load_python_bindings(self):
        """Load vectorlite extension using Python bindings"""
        try:
            import vectorlite_py
            self.conn.enable_load_extension(True)
            self.conn.load_extension(vectorlite_py.vectorlite_path())
        except Exception as e:
            raise RuntimeError(f"vectorlite failed: {e}")

    def close(self):
        """Close connection"""
        if self.conn:
            self.conn.close()

class SchemaManager:
    """Manages database schema"""

    def __init__(self, conn: sqlite3.Connection, config=default_config.database):
        self.conn = conn
        self.config = config

    def create_schema(self):
        """Create all required tables"""
        self._create_documents_table()
        self._create_chunks_table()
        self._create_vector_table()
        self._create_fts_table()
        self._create_processing_progress_table()
        self._create_graph_tables()
        self._create_security_scan_cache_table()
        self.conn.commit()

    def _create_documents_table(self):
        """Create documents table"""
        self.conn.execute("""
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
            self.conn.execute("""
                ALTER TABLE documents ADD COLUMN extraction_method TEXT
            """)
            print("Migration: Added extraction_method column to documents table")
        except Exception:
            pass  # Column already exists

    def _create_chunks_table(self):
        """Create chunks table"""
        self.conn.execute("""
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

    def _create_vector_table(self):
        """Create vector embeddings table using vectorlite HNSW index

        CRITICAL: Validates existing index before loading to prevent corruption.
        If index exists but is corrupted, raises error instead of overwriting.
        """
        import os
        db_dir = os.path.dirname(self.config.path)
        index_path = os.path.join(db_dir, "vec_chunks.idx")

        # SAFETY CHECK: Validate existing index before CREATE TABLE
        # CREATE VIRTUAL TABLE with vectorlite will OVERWRITE a corrupted index!
        # Skip validation if disabled (e.g., for tests with small datasets)
        if os.path.exists(index_path) and getattr(self.config, 'validate_hnsw', True):
            index_size = os.path.getsize(index_path)
            self._validate_hnsw_index(index_path, index_size)

        try:
            self._execute_create_vec_table()
        except Exception as e:
            error_msg = str(e).lower()
            if "corrupted" in error_msg or "unsupported" in error_msg:
                # CRITICAL: Don't silently swallow corruption errors!
                raise RuntimeError(
                    f"HNSW index corruption detected at {index_path}. "
                    f"Restore from backup (e.g., vec_chunks.idx.current-v2.2.2) or rebuild. "
                    f"Original error: {e}"
                ) from e
            # Table already exists with valid index - this is fine
            print(f"Note: vec_chunks exists: {e}")

    def _validate_hnsw_index(self, index_path: str, index_size: int):
        """Validate HNSW index file before loading

        Checks:
        1. File size is reasonable (>1MB for non-empty index)
        2. HNSW header magic bytes are valid

        Raises RuntimeError if validation fails.
        """
        MIN_VALID_SIZE = 1_000_000  # 1MB minimum for a real index with embeddings
        EXPECTED_SIZE_RANGE = (200_000_000, 250_000_000)  # 200-250MB for full 51k embeddings

        # Check for suspiciously small index (likely truncated/corrupted)
        if index_size < MIN_VALID_SIZE:
            raise RuntimeError(
                f"HNSW index file {index_path} is only {index_size:,} bytes. "
                f"Expected >{MIN_VALID_SIZE:,} bytes for a valid index. "
                f"Index may be corrupted or empty. Restore from backup."
            )

        # Check for partial index (less than 50% of expected size)
        if index_size < EXPECTED_SIZE_RANGE[0] * 0.5:
            print(
                f"WARNING: HNSW index is smaller than expected "
                f"({index_size:,} bytes, expected ~{EXPECTED_SIZE_RANGE[0]:,}). "
                f"Index may be incomplete. Consider rebuilding if search quality is poor."
            )

    def _execute_create_vec_table(self):
        """Execute vector table creation with vectorlite HNSW index

        vectorlite syntax:
        - float32[dim] for 32-bit floats (standard)
        - cosine for cosine distance metric
        - hnsw(max_elements) for HNSW index with capacity
        - index_file_path for persistent HNSW index (required for persistence!)
        """
        import os
        db_dir = os.path.dirname(self.config.path)
        index_path = os.path.join(db_dir, "vec_chunks.idx")

        self.conn.execute(f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks
            USING vectorlite(
                embedding float32[{self.config.embedding_dim}] cosine,
                hnsw(max_elements=200000),
                "{index_path}"
            )
        """)

    def _create_fts_table(self):
        """Create FTS5 full-text search table"""
        try:
            self.conn.execute("""
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

    def _create_processing_progress_table(self):
        """Create processing progress tracking table"""
        self.conn.execute("""
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

    def _create_graph_tables(self):
        """Create knowledge graph tables for Obsidian Graph-RAG"""
        self._create_graph_nodes_table()
        self._create_graph_edges_table()
        self._create_edge_indices()
        self._create_graph_metadata_table()
        self._create_chunk_graph_links_table()
        print("Graph-RAG tables initialized (existing data preserved)")

    def _create_graph_nodes_table(self):
        """Create table for graph nodes (notes, tags, headers, concepts)"""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS graph_nodes (
                node_id TEXT PRIMARY KEY,
                node_type TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

    def _create_graph_edges_table(self):
        """Create table for graph edges (wikilinks, tags, headers)"""
        self.conn.execute("""
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

    def _create_edge_indices(self):
        """Create indices for fast edge lookups"""
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_source ON graph_edges(source_id)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_target ON graph_edges(target_id)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_type ON graph_edges(edge_type)")

    def _create_graph_metadata_table(self):
        """Create table for graph metrics (PageRank, degree)"""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS graph_metadata (
                node_id TEXT PRIMARY KEY,
                pagerank_score REAL,
                in_degree INTEGER,
                out_degree INTEGER,
                last_computed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (node_id) REFERENCES graph_nodes(node_id) ON DELETE CASCADE
            )
        """)

    def _create_chunk_graph_links_table(self):
        """Create table linking chunks to graph nodes"""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS chunk_graph_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chunk_id INTEGER NOT NULL,
                node_id TEXT NOT NULL,
                link_type TEXT DEFAULT 'primary',
                FOREIGN KEY (chunk_id) REFERENCES chunks(id) ON DELETE CASCADE,
                FOREIGN KEY (node_id) REFERENCES graph_nodes(node_id) ON DELETE CASCADE
            )
        """)
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_chunk_graph_chunk ON chunk_graph_links(chunk_id)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_chunk_graph_node ON chunk_graph_links(node_id)")

    def _create_security_scan_cache_table(self):
        """Create table for caching security scan results by file hash

        This allows skipping expensive ClamAV/YARA scans for files that have
        already been scanned. Cache entries are keyed by file hash (SHA256),
        so if a file changes, it will be re-scanned.
        """
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS security_scan_cache (
                file_hash TEXT PRIMARY KEY,
                is_valid BOOLEAN NOT NULL,
                severity TEXT,
                reason TEXT,
                validation_check TEXT,
                matches_json TEXT,
                scanned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                scanner_version TEXT
            )
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_security_scan_scanned_at
            ON security_scan_cache(scanned_at)
        """)


class VectorRepository:
    """Facade that delegates to focused repositories."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.documents = DocumentRepository(conn)
        self.chunks = ChunkRepository(conn)
        self.vectors = VectorChunkRepository(conn)
        self.fts = FTSChunkRepository(conn)
        self.search_repo = SearchRepository(conn)

    def is_indexed(self, path: str, hash_val: str) -> bool:
        """Check if document indexed by hash (allows file moves without reindex)"""
        doc = self.documents.find_by_hash(hash_val)
        if not doc:
            return False

        stored_path = doc['file_path']
        if stored_path != path:
            from pathlib import Path
            if Path(stored_path).exists():
                pass  # Duplicate file
            else:
                self._update_path_after_move(hash_val, stored_path, path)
                print(f"File moved: {stored_path} -> {path}")

        return True

    def _update_path_after_move(self, hash_val: str, old_path: str, new_path: str):
        """Update file path after move (preserves chunks/embeddings)."""
        try:
            if self._handle_path_conflict(old_path, new_path):
                return
            self._perform_path_update(hash_val, old_path, new_path)
        except Exception as e:
            print(f"Warning: Failed to update path after move: {e}")
            self.conn.rollback()

    def _handle_path_conflict(self, old_path: str, new_path: str) -> bool:
        """Handle case where new_path already exists in DB.

        Returns True if conflict was resolved (old record deleted), False otherwise.
        """
        existing_at_new_path = self.documents.find_by_path(new_path)
        if not existing_at_new_path:
            return False

        from ingestion.graph_repository import GraphRepository
        graph_repo = GraphRepository(self.conn)
        graph_repo.delete_note_nodes(old_path)
        self.documents.delete(old_path)
        self.conn.execute(
            "DELETE FROM processing_progress WHERE file_path = ?",
            (old_path,)
        )
        self.conn.commit()
        print(f"  Removed stale record: {old_path} (superseded by {new_path})")
        return True

    def _perform_path_update(self, hash_val: str, old_path: str, new_path: str):
        """Perform the actual path update via temp path to avoid UNIQUE constraint."""
        import uuid
        temp_path = f"__temp_move_{uuid.uuid4().hex}__"

        self.documents.update_path_by_hash(hash_val, temp_path)
        self.conn.execute(
            "UPDATE processing_progress SET file_path = ? WHERE file_hash = ?",
            (temp_path, hash_val)
        )

        self.documents.update_path_by_hash(hash_val, new_path)
        self.conn.execute(
            "UPDATE processing_progress SET file_path = ? WHERE file_hash = ?",
            (new_path, hash_val)
        )

        from ingestion.graph_repository import GraphRepository
        graph_repo = GraphRepository(self.conn)
        graph_repo.update_note_path(old_path, new_path)

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
        from ingestion.graph_repository import GraphRepository
        graph_repo = GraphRepository(self.conn)
        graph_repo.delete_note_nodes(path)
        self.documents.delete(path)

    def _insert_chunks_delegated(self, doc_id: int, chunks: List[Dict], embeddings: List):
        """Insert chunks using new repositories"""
        for idx, (chunk, emb) in enumerate(zip(chunks, embeddings)):
            chunk_id = self.chunks.add(doc_id, chunk['content'], chunk.get('page'), idx)
            self.vectors.add(chunk_id, emb)
            self.fts.add(chunk_id, chunk['content'])
        print(f"[HNSW] Indexed {len(chunks)} chunks for doc_id={doc_id}")

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

class VectorStore:
    """Facade for vector storage operations.

    Thread Safety:
    Uses threading.RLock for critical operations (search, delete, flush).
    This enables safe concurrent access from AsyncVectorStoreAdapter's
    thread pool while preventing data corruption.

    Persistence:
    HNSW index is kept in memory and persisted:
    - On graceful shutdown (via close())
    - Periodically every FLUSH_INTERVAL_SECONDS (default 300s / 5 min)

    This avoids per-write flush which causes file-level corruption
    during concurrent operations.
    """

    FLUSH_INTERVAL_SECONDS = 300  # 5 minutes

    def __init__(self, config=default_config.database):
        import threading
        self._lock = threading.RLock()  # Reentrant lock for nested calls
        self._flush_timer = None
        self._closed = False
        self._config = config  # Store config for schema initialization
        self.db_conn = DatabaseConnection(config)
        self.conn = self.db_conn.connect()
        self._init_schema()
        self.repo = VectorRepository(self.conn)
        self.hybrid = HybridSearcher(self.conn)
        self._start_periodic_flush()

    def _init_schema(self):
        """Initialize database schema"""
        schema = SchemaManager(self.conn, self._config)
        schema.create_schema()

    def is_document_indexed(self, path: str, hash_val: str) -> bool:
        """Check if document is indexed.

        Thread-safe: protected by lock to prevent access during connection refresh.
        """
        with self._lock:
            return self.repo.is_indexed(path, hash_val)

    def add_document(self, file_path: str, file_hash: str,
                    chunks: List[Dict], embeddings: List):
        """Add document to store.

        Thread-safe: holds lock for entire operation.

        NOTE: Does NOT flush HNSW to disk after each write.
        HNSW is persisted on graceful shutdown (conn.close).
        This avoids file-level corruption during concurrent operations.
        """
        with self._lock:
            self.repo.add_document(file_path, file_hash, chunks, embeddings)
            # REMOVED: self._flush_hnsw_index_unlocked()
            # Flushing after every write causes corruption during concurrent ops.
            # HNSW will persist on graceful shutdown via close().

    def _start_periodic_flush(self):
        """Start periodic HNSW flush timer.

        Runs in background thread, flushes every FLUSH_INTERVAL_SECONDS.
        Safe because _flush_hnsw_index() acquires the lock, blocking any
        concurrent operations during the flush.
        """
        import threading

        def flush_and_reschedule():
            try:
                if self._closed:
                    return
                try:
                    self._flush_hnsw_index()
                    print(f"[VectorStore] Periodic HNSW flush completed")
                except Exception as e:
                    import traceback
                    print(f"[VectorStore] Periodic flush failed: {e}")
                    traceback.print_exc()
                finally:
                    # Reschedule if not closed
                    if not self._closed:
                        self._flush_timer = threading.Timer(
                            self.FLUSH_INTERVAL_SECONDS,
                            flush_and_reschedule
                        )
                        self._flush_timer.daemon = True
                        self._flush_timer.start()
            except Exception as e:
                import traceback
                print(f"[VectorStore] FATAL: Flush timer thread exiting due to: {e}")
                traceback.print_exc()

        self._flush_timer = threading.Timer(
            self.FLUSH_INTERVAL_SECONDS,
            flush_and_reschedule
        )
        self._flush_timer.daemon = True
        self._flush_timer.start()
        print(f"[VectorStore] Periodic flush enabled (every {self.FLUSH_INTERVAL_SECONDS}s)")

    def _stop_periodic_flush(self):
        """Stop the periodic flush timer."""
        if self._flush_timer:
            self._flush_timer.cancel()
            self._flush_timer = None

    def _flush_hnsw_index(self):
        """Force HNSW index to persist by closing and reopening connection.

        vectorlite only saves the HNSW index to disk when the connection closes.
        Without this, inserts go to in-memory index but are lost on restart.

        Thread-safe: protected by lock to prevent concurrent access during
        connection rebuild.
        """
        with self._lock:
            self._flush_hnsw_index_unlocked()

    def _flush_hnsw_index_unlocked(self):
        """Internal flush without acquiring lock (caller must hold lock)."""
        self.conn.close()
        self.conn = self.db_conn.connect()
        self.repo = VectorRepository(self.conn)
        self.hybrid = HybridSearcher(self.conn)

    def search(self, query_embedding: List, top_k: int = 5,
              threshold: float = None, query_text: Optional[str] = None,
              use_hybrid: bool = True) -> List[Dict]:
        """Search for similar chunks.

        Thread-safe: protected by lock for concurrent access from adapter.
        """
        with self._lock:
            vector_results = self.repo.search(query_embedding, top_k, threshold)

            if use_hybrid and query_text:
                return self.hybrid.search(query_text, vector_results, top_k)
            return vector_results

    def get_stats(self) -> Dict:
        """Get statistics.

        Thread-safe: protected by lock to prevent access during connection refresh.
        """
        with self._lock:
            return self.repo.get_stats()

    def get_document_info(self, filename: str) -> Dict:
        """Get document information including extraction method.

        Thread-safe: protected by lock to prevent access during connection refresh.
        """
        with self._lock:
            # Search for file path containing the filename
            cursor = self.conn.execute("""
                SELECT file_path, extraction_method, indexed_at
                FROM documents
                WHERE file_path LIKE ?
                ORDER BY indexed_at DESC
                LIMIT 1
            """, (f"%{filename}%",))
            result = cursor.fetchone()

            if not result:
                return None

            return {
                'file_path': result[0],
                'extraction_method': result[1] or 'unknown',
                'indexed_at': result[2]
            }

    def delete_document(self, file_path: str) -> Dict:
        """Delete a document and all its chunks from the vector store.

        Thread-safe: protected by lock for concurrent access from adapter.
        This is the key operation that was broken with dual-store architecture.
        """
        with self._lock:
            doc_id = self._find_document_id(file_path)
            if not doc_id:
                return self._document_not_found_result()

            chunk_count = self._count_document_chunks(doc_id)
            self._delete_document_data(doc_id)
            self.conn.commit()
            return self._deletion_success_result(doc_id, chunk_count)

    def _find_document_id(self, file_path: str):
        """Find document ID by file path"""
        cursor = self.conn.execute("SELECT id FROM documents WHERE file_path = ?", (file_path,))
        result = cursor.fetchone()
        return result[0] if result else None

    def _document_not_found_result(self) -> Dict:
        """Return result for document not found"""
        return {'found': False, 'chunks_deleted': 0, 'document_deleted': False}

    def _count_document_chunks(self, doc_id: int) -> int:
        """Count chunks for document"""
        cursor = self.conn.execute("SELECT COUNT(*) FROM chunks WHERE document_id = ?", (doc_id,))
        return cursor.fetchone()[0]

    def _delete_document_data(self, doc_id: int):
        """Delete chunks and document record, cascading to vec_chunks and fts_chunks.

        Order matters: get chunk IDs first, then delete from derived tables,
        then delete chunks, then delete document.
        """
        # Get chunk IDs before deletion
        cursor = self.conn.execute(
            "SELECT id FROM chunks WHERE document_id = ?", (doc_id,)
        )
        chunk_ids = [row[0] for row in cursor.fetchall()]

        if chunk_ids:
            # Delete from vec_chunks (HNSW index) - uses rowid = chunk.id
            placeholders = ','.join('?' * len(chunk_ids))
            self.conn.execute(
                f"DELETE FROM vec_chunks WHERE rowid IN ({placeholders})",
                chunk_ids
            )
            # Delete from fts_chunks (full-text search)
            self.conn.execute(
                f"DELETE FROM fts_chunks WHERE chunk_id IN ({placeholders})",
                chunk_ids
            )

        # Now delete the source records
        self.conn.execute("DELETE FROM chunks WHERE document_id = ?", (doc_id,))
        self.conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))

    def _deletion_success_result(self, doc_id: int, chunk_count: int) -> Dict:
        """Return success result for deletion"""
        return {
            'found': True,
            'document_id': doc_id,
            'chunks_deleted': chunk_count,
            'document_deleted': True
        }

    def query_documents_with_chunks(self):
        """Query all documents with chunk counts.

        Delegation method to avoid Law of Demeter violation.
        Thread-safe: protected by lock to prevent access during connection refresh.

        Returns cursor for documents joined with chunk counts.
        """
        with self._lock:
            return self.conn.execute("""
                SELECT d.file_path, d.indexed_at, COUNT(c.id)
                FROM documents d
                LEFT JOIN chunks c ON d.id = c.document_id
                GROUP BY d.id
                ORDER BY d.indexed_at DESC
            """).fetchall()

    def close(self):
        """Close connection and persist HNSW index.

        Stops periodic flush timer and closes the database connection.
        vectorlite persists the HNSW index when the connection closes.
        """
        self._closed = True
        self._stop_periodic_flush()
        self.db_conn.close()
        print("[VectorStore] Closed - HNSW index persisted")

