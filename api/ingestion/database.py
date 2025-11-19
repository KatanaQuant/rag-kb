import sqlite3
from pathlib import Path
from typing import List, Dict, Tuple, Optional
import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
import logging
import sys
import warnings

from pypdf import PdfReader
from docx import Document
import markdown
import numpy as np

from config import default_config
from hybrid_search import HybridSearcher
from domain_models import ChunkData, DocumentFile, ExtractionResult

# Suppress verbose Docling/PDF warnings and errors
logging.getLogger('pdfminer').setLevel(logging.CRITICAL)
logging.getLogger('PIL').setLevel(logging.CRITICAL)
logging.getLogger('docling').setLevel(logging.CRITICAL)
logging.getLogger('docling_parse').setLevel(logging.CRITICAL)
logging.getLogger('docling_core').setLevel(logging.CRITICAL)
logging.getLogger('pdfium').setLevel(logging.CRITICAL)
warnings.filterwarnings('ignore', category=UserWarning, module='pypdf')

try:
    from docling.document_converter import DocumentConverter
    DOCLING_AVAILABLE = True
except ImportError as e:
    DOCLING_AVAILABLE = False
    print(f"Warning: Docling not available, falling back to pypdf ({e})")

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


@dataclass


class DatabaseConnection:
    """Manages SQLite connection and extensions"""

    def __init__(self, config=default_config.database):
        self.config = config
        self.conn = None

    def connect(self) -> sqlite3.Connection:
        """Establish database connection"""
        self.conn = self._create_connection()
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
        self.conn.enable_load_extension(True)
        self._try_load()

    def _try_load(self):
        """Try loading extension"""
        try:
            self.conn.load_extension("vec0")
        except Exception:
            self._load_python_bindings()

    def _load_python_bindings(self):
        """Fallback to Python bindings"""
        try:
            import sqlite_vec
            sqlite_vec.load(self.conn)
        except Exception as e:
            raise RuntimeError(f"sqlite-vec failed: {e}")

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
        """Create vector embeddings table"""
        try:
            self._execute_create_vec_table()
        except Exception as e:
            print(f"Note: vec_chunks exists: {e}")

    def _execute_create_vec_table(self):
        """Execute vector table creation"""
        self.conn.execute(f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks
            USING vec0(
                chunk_id INTEGER PRIMARY KEY,
                embedding FLOAT[{self.config.embedding_dim}]
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
        """Create knowledge graph tables for Obsidian Graph-RAG

        GRACEFUL MIGRATION: Creates tables if they don't exist.
        Does NOT touch existing data in documents/chunks/vectors.
        """
        # Graph nodes table (notes, tags, headers, concepts)
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

        # Graph edges table (wikilinks, tags, headers, concepts)
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

        # Index for fast edge lookups
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_edges_source ON graph_edges(source_id)
        """)

        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_edges_target ON graph_edges(target_id)
        """)

        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_edges_type ON graph_edges(edge_type)
        """)

        # Graph metadata table (PageRank scores, etc.)
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

        # Chunk-to-graph mapping (connects chunks to graph nodes)
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

        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_chunk_graph_chunk ON chunk_graph_links(chunk_id)
        """)

        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_chunk_graph_node ON chunk_graph_links(node_id)
        """)

        print("Graph-RAG tables initialized (existing data preserved)")


class VectorRepository:
    """Handles vector CRUD operations"""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def is_indexed(self, path: str, hash_val: str) -> bool:
        """Check if document indexed by hash (allows file moves without reindex)

        First checks if hash exists anywhere in database.
        If hash found but path changed:
        - If stored path still exists: This is a duplicate file, skip it
        - If stored path missing: File was moved, update the path
        Returns True if document with this hash is already indexed.
        """
        result = self._fetch_by_hash(hash_val)
        if not result:
            return False

        # Hash exists - check if path changed
        stored_path = result[0]
        if stored_path != path:
            # Check if stored path still exists (duplicate) or was moved
            from pathlib import Path
            if Path(stored_path).exists():
                # Duplicate file - different path, same content
                print(f"Skipping duplicate: {path} (same content as {stored_path})")
            else:
                # File was actually moved
                self._update_path(hash_val, stored_path, path)
                print(f"File moved: {stored_path} -> {path}")

        return True

    def _fetch_hash(self, path: str):
        """Fetch stored hash by path"""
        cursor = self.conn.execute(
            "SELECT file_hash FROM documents WHERE file_path = ?",
            (path,)
        )
        return cursor.fetchone()

    def _fetch_by_hash(self, hash_val: str):
        """Fetch stored path by hash"""
        cursor = self.conn.execute(
            "SELECT file_path FROM documents WHERE file_hash = ?",
            (hash_val,)
        )
        return cursor.fetchone()

    def _update_path(self, hash_val: str, old_path: str, new_path: str):
        """Update file path after move (preserves chunks/embeddings)"""
        try:
            import uuid
            temp_path = f"__temp_move_{uuid.uuid4().hex}__"

            # Use temporary path to avoid UNIQUE constraint conflicts during swaps
            # Step 1: Move to temp path
            self.conn.execute(
                "UPDATE documents SET file_path = ? WHERE file_hash = ?",
                (temp_path, hash_val)
            )
            self.conn.execute(
                "UPDATE processing_progress SET file_path = ? WHERE file_hash = ?",
                (temp_path, hash_val)
            )

            # Step 2: Move to final path
            self.conn.execute(
                "UPDATE documents SET file_path = ? WHERE file_hash = ?",
                (new_path, hash_val)
            )
            self.conn.execute(
                "UPDATE processing_progress SET file_path = ? WHERE file_hash = ?",
                (new_path, hash_val)
            )

            # Update graph nodes for Obsidian notes (if applicable)
            from ingestion.graph_repository import GraphRepository
            graph_repo = GraphRepository(self.conn)
            graph_repo.update_note_path(old_path, new_path)

            self.conn.commit()
        except Exception as e:
            print(f"Warning: Failed to update path after move: {e}")
            self.conn.rollback()

    def get_extraction_method(self, path: str) -> str:
        """Get extraction method used for a document"""
        cursor = self.conn.execute(
            "SELECT extraction_method FROM documents WHERE file_path = ?",
            (path,)
        )
        result = cursor.fetchone()
        return result[0] if result and result[0] else 'unknown'

    def add_document(self, path: str, hash_val: str,
                    chunks: List[Dict], embeddings: List) -> int:
        """Add document with chunks"""
        # Extract extraction_method from first chunk if available
        extraction_method = None
        if chunks and '_extraction_method' in chunks[0]:
            extraction_method = chunks[0]['_extraction_method']

        self._delete_old(path)
        doc_id = self._insert_doc(path, hash_val, extraction_method)
        self._insert_chunks(doc_id, chunks, embeddings)
        self.conn.commit()
        return doc_id

    def _delete_old(self, path: str):
        """Remove existing document AND clean up graph nodes

        For Obsidian notes: Cleans up graph nodes intelligently
        - Deletes note-specific nodes (note, headers)
        - Cleans up orphaned shared nodes (tags, placeholders)
        - Preserves shared nodes still referenced by other notes

        For other files: No graph impact
        """
        # Clean up graph nodes if this is an Obsidian note
        # (GraphRepository handles the intelligence)
        from ingestion.graph_repository import GraphRepository
        graph_repo = GraphRepository(self.conn)
        graph_repo.delete_note_nodes(path)

        # Delete document (CASCADE deletes chunks, vectors, fts, chunk_graph_links)
        self.conn.execute(
            "DELETE FROM documents WHERE file_path = ?",
            (path,)
        )

    def _insert_doc(self, path: str, hash_val: str, extraction_method: str = None) -> int:
        """Insert document record"""
        cursor = self.conn.execute(
            "INSERT INTO documents (file_path, file_hash, extraction_method) VALUES (?, ?, ?)",
            (path, hash_val, extraction_method)
        )
        return cursor.lastrowid

    def _insert_chunks(self, doc_id: int, chunks: List[Dict],
                      embeddings: List):
        """Insert all chunks and vectors"""
        for idx, (chunk, emb) in enumerate(zip(chunks, embeddings)):
            self._insert_chunk_pair(doc_id, chunk, emb, idx)

    def _insert_chunk_pair(self, doc_id, chunk, emb, idx):
        """Insert chunk and its vector"""
        chunk_id = self._insert_chunk(doc_id, chunk, idx)
        self._insert_vector(chunk_id, emb)
        self._insert_fts(chunk_id, chunk['content'])

    def _insert_chunk(self, doc_id: int, chunk: Dict, idx: int) -> int:
        """Insert single chunk"""
        cursor = self.conn.execute(
            """INSERT INTO chunks
               (document_id, content, page, chunk_index)
               VALUES (?, ?, ?, ?)""",
            (doc_id, chunk['content'], chunk.get('page'), idx)
        )
        return cursor.lastrowid

    def _insert_vector(self, chunk_id: int, embedding: List):
        """Insert vector embedding"""
        blob = self._to_blob(embedding)
        self.conn.execute(
            "INSERT INTO vec_chunks (chunk_id, embedding) VALUES (?, ?)",
            (chunk_id, blob)
        )

    def _insert_fts(self, chunk_id: int, content: str):
        """Insert into FTS5 index"""
        try:
            self.conn.execute(
                "INSERT INTO fts_chunks (chunk_id, content) VALUES (?, ?)",
                (chunk_id, content)
            )
        except Exception:
            pass

    @staticmethod
    def _to_blob(embedding: List) -> bytes:
        """Convert embedding to binary"""
        arr = np.array(embedding, dtype=np.float32)
        return arr.tobytes()

    def search(self, embedding: List, top_k: int,
              threshold: float = None) -> List[Dict]:
        """Search for similar vectors"""
        blob = self._to_blob(embedding)
        results = self._execute_search(blob, top_k)
        return self._format_results(results, threshold)

    def _execute_search(self, blob: bytes, top_k: int):
        """Execute vector search"""
        cursor = self.conn.execute("""
            SELECT c.content, d.file_path, c.page,
                   vec_distance_cosine(v.embedding, ?) as dist
            FROM vec_chunks v
            JOIN chunks c ON v.chunk_id = c.id
            JOIN documents d ON c.document_id = d.id
            ORDER BY dist ASC
            LIMIT ?
        """, (blob, top_k))
        return cursor.fetchall()

    def _format_results(self, rows, threshold: float) -> List[Dict]:
        """Format search results"""
        results = []
        for row in rows:
            self._add_if_valid(results, row, threshold)
        return results

    def _add_if_valid(self, results, row, threshold):
        """Add result if meets threshold"""
        score = 1 - row[3]
        if threshold is None or score >= threshold:
            results.append(self._make_result(row, score))

    @staticmethod
    def _make_result(row, score: float) -> Dict:
        """Create result dictionary"""
        return {
            'content': row[0],
            'source': Path(row[1]).name,
            'page': row[2],
            'score': float(score)
        }

    def get_stats(self) -> Dict:
        """Get database statistics"""
        return {
            'indexed_documents': self._count_docs(),
            'total_chunks': self._count_chunks()
        }

    def _count_docs(self) -> int:
        """Count total documents"""
        cursor = self.conn.execute("SELECT COUNT(*) FROM documents")
        return cursor.fetchone()[0]

    def _count_chunks(self) -> int:
        """Count total chunks"""
        cursor = self.conn.execute("SELECT COUNT(*) FROM chunks")
        return cursor.fetchone()[0]


class VectorStore:
    """Facade for vector storage operations"""

    def __init__(self, config=default_config.database):
        self.db_conn = DatabaseConnection(config)
        self.conn = self.db_conn.connect()
        self._init_schema()
        self.repo = VectorRepository(self.conn)
        self.hybrid = HybridSearcher(self.conn)

    def _init_schema(self):
        """Initialize database schema"""
        schema = SchemaManager(self.conn)
        schema.create_schema()

    def is_document_indexed(self, path: str, hash_val: str) -> bool:
        """Check if document is indexed"""
        return self.repo.is_indexed(path, hash_val)

    def add_document(self, file_path: str, file_hash: str,
                    chunks: List[Dict], embeddings: List):
        """Add document to store"""
        self.repo.add_document(file_path, file_hash, chunks, embeddings)

    def search(self, query_embedding: List, top_k: int = 5,
              threshold: float = None, query_text: Optional[str] = None,
              use_hybrid: bool = True) -> List[Dict]:
        """Search for similar chunks"""
        vector_results = self.repo.search(query_embedding, top_k, threshold)

        if use_hybrid and query_text:
            return self.hybrid.search(query_text, vector_results, top_k)
        return vector_results

    def get_stats(self) -> Dict:
        """Get statistics"""
        return self.repo.get_stats()

    def get_document_info(self, filename: str) -> Dict:
        """Get document information including extraction method"""
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

    def close(self):
        """Close connection"""
        self.db_conn.close()

