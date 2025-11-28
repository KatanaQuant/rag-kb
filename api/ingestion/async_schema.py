"""Async database schema management."""

import aiosqlite
from config import default_config


class AsyncSchemaManager:
    """Manages database schema asynchronously.

    Single responsibility: Database schema creation and migrations
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
