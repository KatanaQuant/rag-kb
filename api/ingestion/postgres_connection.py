"""
PostgreSQL connection management for pgvector.

Replaces the SQLite + vectorlite connection layer with PostgreSQL + pgvector.
This provides ACID compliance, proper crash recovery, and ARM64 support.
"""
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Optional
import logging

from config import default_config
from ingestion.interfaces import DatabaseConnection, SchemaManager

logger = logging.getLogger(__name__)


class PostgresConnection(DatabaseConnection):
    """Manages PostgreSQL connection with pgvector extension.

    Unlike the SQLite + vectorlite approach, PostgreSQL:
    - Has full ACID compliance
    - Automatically persists on commit (no flush needed)
    - Handles concurrent access properly
    - Works on all platforms including ARM64
    """

    def __init__(self, config=default_config.database):
        self.config = config
        self.conn: Optional[psycopg2.extensions.connection] = None

    def connect(self) -> psycopg2.extensions.connection:
        """Establish database connection and ensure pgvector extension exists."""
        self.conn = psycopg2.connect(
            host=self.config.host,
            port=self.config.port,
            user=self.config.user,
            password=self.config.password,
            database=self.config.database,
        )
        # Enable autocommit for extension creation
        self.conn.autocommit = True
        self._ensure_pgvector()
        self.conn.autocommit = False
        return self.conn

    def _ensure_pgvector(self):
        """Ensure pgvector extension is installed."""
        with self.conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            logger.debug("pgvector extension ready")

    def close(self):
        """Close connection."""
        if self.conn:
            self.conn.close()
            self.conn = None


class PostgresSchemaManager(SchemaManager):
    """Manages PostgreSQL database schema with pgvector.

    Creates tables:
    - documents: File metadata
    - chunks: Text chunks with page info
    - vec_chunks: Vector embeddings with HNSW index
    - fts_chunks: Full-text search with tsvector
    - graph_nodes, graph_edges, etc.: Knowledge graph
    """

    def __init__(self, conn: psycopg2.extensions.connection, config=default_config.database):
        self.conn = conn
        self.config = config

    def create_schema(self):
        """Create all required tables."""
        with self.conn.cursor() as cur:
            self._create_documents_table(cur)
            self._create_chunks_table(cur)
            self._create_vector_table(cur)
            self._create_fts_table(cur)
            self._create_processing_progress_table(cur)
            self._create_graph_tables(cur)
            self._create_security_scan_cache_table(cur)
        self.conn.commit()
        logger.info("PostgreSQL schema initialized")

    def _create_documents_table(self, cur):
        """Create documents table."""
        cur.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id SERIAL PRIMARY KEY,
                file_path TEXT UNIQUE NOT NULL,
                file_hash TEXT NOT NULL,
                indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                extraction_method TEXT
            )
        """)

    def _create_chunks_table(self, cur):
        """Create chunks table with foreign key to documents."""
        cur.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                id SERIAL PRIMARY KEY,
                document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                content TEXT NOT NULL,
                page INTEGER,
                chunk_index INTEGER
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id)")

    def _create_vector_table(self, cur):
        """Create vector embeddings table with pgvector HNSW index.

        pgvector HNSW parameters:
        - m=16: Number of connections per node (default 16)
        - ef_construction=64: Build-time search factor (default 64)

        These are reasonable defaults. For 50k vectors, query time ~1ms.
        """
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS vec_chunks (
                rowid INTEGER PRIMARY KEY REFERENCES chunks(id) ON DELETE CASCADE,
                embedding vector({self.config.embedding_dim})
            )
        """)
        # Create HNSW index for cosine distance
        # Note: vector_cosine_ops is for <=> operator (cosine distance)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_vec_chunks_hnsw
            ON vec_chunks USING hnsw (embedding vector_cosine_ops)
            WITH (m=16, ef_construction=64)
        """)
        logger.info(f"vec_chunks table ready with HNSW index (dim={self.config.embedding_dim})")

    def _create_fts_table(self, cur):
        """Create full-text search table with tsvector.

        Uses generated column for automatic tsvector update.
        GIN index for fast text search.
        """
        cur.execute("""
            CREATE TABLE IF NOT EXISTS fts_chunks (
                chunk_id INTEGER PRIMARY KEY REFERENCES chunks(id) ON DELETE CASCADE,
                content TEXT NOT NULL,
                tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_fts_chunks_tsv
            ON fts_chunks USING GIN(tsv)
        """)
        logger.info("fts_chunks table ready with GIN index")

    def _create_processing_progress_table(self, cur):
        """Create processing progress tracking table."""
        cur.execute("""
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

    def _create_graph_tables(self, cur):
        """Create knowledge graph tables for Graph-RAG."""
        # Graph nodes
        cur.execute("""
            CREATE TABLE IF NOT EXISTS graph_nodes (
                node_id TEXT PRIMARY KEY,
                node_type TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Graph edges
        cur.execute("""
            CREATE TABLE IF NOT EXISTS graph_edges (
                id SERIAL PRIMARY KEY,
                source_id TEXT NOT NULL REFERENCES graph_nodes(node_id) ON DELETE CASCADE,
                target_id TEXT NOT NULL REFERENCES graph_nodes(node_id) ON DELETE CASCADE,
                edge_type TEXT NOT NULL,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_edges_source ON graph_edges(source_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_edges_target ON graph_edges(target_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_edges_type ON graph_edges(edge_type)")
        # Graph metadata
        cur.execute("""
            CREATE TABLE IF NOT EXISTS graph_metadata (
                node_id TEXT PRIMARY KEY REFERENCES graph_nodes(node_id) ON DELETE CASCADE,
                pagerank_score REAL,
                in_degree INTEGER,
                out_degree INTEGER,
                last_computed TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Chunk-graph links
        cur.execute("""
            CREATE TABLE IF NOT EXISTS chunk_graph_links (
                id SERIAL PRIMARY KEY,
                chunk_id INTEGER NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
                node_id TEXT NOT NULL REFERENCES graph_nodes(node_id) ON DELETE CASCADE,
                link_type TEXT DEFAULT 'primary'
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_chunk_graph_chunk ON chunk_graph_links(chunk_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_chunk_graph_node ON chunk_graph_links(node_id)")
        logger.info("Graph-RAG tables initialized")

    def _create_security_scan_cache_table(self, cur):
        """Create security scan cache table."""
        cur.execute("""
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
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_security_scan_scanned_at
            ON security_scan_cache(scanned_at)
        """)
