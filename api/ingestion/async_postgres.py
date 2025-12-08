"""
Async PostgreSQL database layer using asyncpg.

Replaces the aiosqlite + vectorlite async layer with PostgreSQL + pgvector.
Uses asyncpg for native async PostgreSQL support.

Key benefits over aiosqlite:
- Native async PostgreSQL driver (not SQLite wrapper)
- Better connection pooling
- Full ACID compliance
- Works on all platforms including ARM64
"""
import asyncio
import logging
from typing import List, Dict, Optional
from pathlib import Path

import asyncpg

from config import default_config

logger = logging.getLogger(__name__)


class AsyncPostgresConnection:
    """Manages async PostgreSQL connection with pgvector extension."""

    def __init__(self, config=default_config.database):
        self.config = config
        self.conn: Optional[asyncpg.Connection] = None

    async def connect(self) -> asyncpg.Connection:
        """Establish async database connection."""
        self.conn = await asyncpg.connect(
            host=self.config.host,
            port=self.config.port,
            user=self.config.user,
            password=self.config.password,
            database=self.config.database,
        )
        await self._ensure_pgvector()
        return self.conn

    async def _ensure_pgvector(self):
        """Ensure pgvector extension is installed."""
        await self.conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        logger.debug("pgvector extension ready (async)")

    async def close(self):
        """Close connection."""
        if self.conn:
            await self.conn.close()
            self.conn = None


class AsyncPostgresSchemaManager:
    """Manages PostgreSQL database schema asynchronously."""

    def __init__(self, conn: asyncpg.Connection, config=default_config.database):
        self.conn = conn
        self.config = config

    async def create_schema(self):
        """Create all required tables."""
        await self._create_documents_table()
        await self._create_chunks_table()
        await self._create_vector_table()
        await self._create_fts_table()
        await self._create_processing_progress_table()
        await self._create_graph_tables()
        await self._create_security_scan_cache_table()
        logger.info("PostgreSQL schema initialized (async)")

    async def _create_documents_table(self):
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id SERIAL PRIMARY KEY,
                file_path TEXT UNIQUE NOT NULL,
                file_hash TEXT NOT NULL,
                indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                extraction_method TEXT
            )
        """)

    async def _create_chunks_table(self):
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                id SERIAL PRIMARY KEY,
                document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                content TEXT NOT NULL,
                page INTEGER,
                chunk_index INTEGER
            )
        """)
        await self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id)"
        )

    async def _create_vector_table(self):
        await self.conn.execute(f"""
            CREATE TABLE IF NOT EXISTS vec_chunks (
                rowid INTEGER PRIMARY KEY REFERENCES chunks(id) ON DELETE CASCADE,
                embedding vector({self.config.embedding_dim})
            )
        """)
        await self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_vec_chunks_hnsw
            ON vec_chunks USING hnsw (embedding vector_cosine_ops)
            WITH (m=16, ef_construction=64)
        """)

    async def _create_fts_table(self):
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS fts_chunks (
                chunk_id INTEGER PRIMARY KEY REFERENCES chunks(id) ON DELETE CASCADE,
                content TEXT NOT NULL,
                tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED
            )
        """)
        await self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_fts_chunks_tsv
            ON fts_chunks USING GIN(tsv)
        """)

    async def _create_processing_progress_table(self):
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
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS graph_edges (
                id SERIAL PRIMARY KEY,
                source_id TEXT NOT NULL REFERENCES graph_nodes(node_id) ON DELETE CASCADE,
                target_id TEXT NOT NULL REFERENCES graph_nodes(node_id) ON DELETE CASCADE,
                edge_type TEXT NOT NULL,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_edges_source ON graph_edges(source_id)"
        )
        await self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_edges_target ON graph_edges(target_id)"
        )
        await self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_edges_type ON graph_edges(edge_type)"
        )
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS graph_metadata (
                node_id TEXT PRIMARY KEY REFERENCES graph_nodes(node_id) ON DELETE CASCADE,
                pagerank_score REAL,
                in_degree INTEGER,
                out_degree INTEGER,
                last_computed TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS chunk_graph_links (
                id SERIAL PRIMARY KEY,
                chunk_id INTEGER NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
                node_id TEXT NOT NULL REFERENCES graph_nodes(node_id) ON DELETE CASCADE,
                link_type TEXT DEFAULT 'primary'
            )
        """)
        await self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_chunk_graph_chunk ON chunk_graph_links(chunk_id)"
        )
        await self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_chunk_graph_node ON chunk_graph_links(node_id)"
        )

    async def _create_security_scan_cache_table(self):
        await self.conn.execute("""
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
        await self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_security_scan_scanned_at
            ON security_scan_cache(scanned_at)
        """)


# Async Repository implementations

class AsyncPostgresDocumentRepository:
    """Async document repository for PostgreSQL."""

    def __init__(self, conn: asyncpg.Connection):
        self.conn = conn

    async def add(self, path: str, hash_val: str, extraction_method: str = None) -> int:
        row = await self.conn.fetchrow(
            "INSERT INTO documents (file_path, file_hash, extraction_method) VALUES ($1, $2, $3) RETURNING id",
            path, hash_val, extraction_method
        )
        return row['id']

    async def find_by_path(self, path: str) -> Optional[Dict]:
        row = await self.conn.fetchrow(
            "SELECT id, file_path, file_hash, indexed_at, extraction_method FROM documents WHERE file_path = $1",
            path
        )
        if not row:
            return None
        return dict(row)

    async def find_by_hash(self, hash_val: str) -> Optional[Dict]:
        row = await self.conn.fetchrow(
            "SELECT id, file_path, file_hash, indexed_at, extraction_method FROM documents WHERE file_hash = $1",
            hash_val
        )
        if not row:
            return None
        return dict(row)

    async def delete(self, path: str):
        await self.conn.execute("DELETE FROM documents WHERE file_path = $1", path)

    async def delete_by_id(self, doc_id: int):
        await self.conn.execute("DELETE FROM documents WHERE id = $1", doc_id)

    async def update_path_by_hash(self, hash_val: str, new_path: str):
        await self.conn.execute(
            "UPDATE documents SET file_path = $1 WHERE file_hash = $2",
            new_path, hash_val
        )

    async def count(self) -> int:
        row = await self.conn.fetchrow("SELECT COUNT(*) FROM documents")
        return row[0]

    async def get_extraction_method(self, path: str) -> str:
        row = await self.conn.fetchrow(
            "SELECT extraction_method FROM documents WHERE file_path = $1",
            path
        )
        return row[0] if row and row[0] else 'unknown'

    async def search_by_pattern(self, pattern: str) -> List[Dict]:
        rows = await self.conn.fetch(
            """SELECT id, file_path, file_hash, indexed_at, extraction_method
               FROM documents WHERE file_path LIKE $1 ORDER BY indexed_at DESC""",
            f"%{pattern}%"
        )
        return [dict(row) for row in rows]


class AsyncPostgresChunkRepository:
    """Async chunk repository for PostgreSQL."""

    def __init__(self, conn: asyncpg.Connection):
        self.conn = conn

    async def add(self, document_id: int, content: str, page: int = None, chunk_index: int = None) -> int:
        row = await self.conn.fetchrow(
            "INSERT INTO chunks (document_id, content, page, chunk_index) VALUES ($1, $2, $3, $4) RETURNING id",
            document_id, content, page, chunk_index
        )
        return row['id']

    async def count(self) -> int:
        row = await self.conn.fetchrow("SELECT COUNT(*) FROM chunks")
        return row[0]

    async def count_by_document(self, document_id: int) -> int:
        row = await self.conn.fetchrow(
            "SELECT COUNT(*) FROM chunks WHERE document_id = $1",
            document_id
        )
        return row[0]


class AsyncPostgresVectorChunkRepository:
    """Async vector embeddings repository for PostgreSQL."""

    def __init__(self, conn: asyncpg.Connection):
        self.conn = conn

    async def add(self, chunk_id: int, embedding: List[float]) -> None:
        # asyncpg needs the vector as a string for pgvector
        vec_str = f"[{','.join(str(x) for x in embedding)}]"
        await self.conn.execute(
            "INSERT INTO vec_chunks (rowid, embedding) VALUES ($1, $2::vector)",
            chunk_id, vec_str
        )


class AsyncPostgresFTSChunkRepository:
    """Async FTS repository for PostgreSQL."""

    def __init__(self, conn: asyncpg.Connection):
        self.conn = conn

    async def add(self, chunk_id: int, content: str) -> None:
        await self.conn.execute(
            "INSERT INTO fts_chunks (chunk_id, content) VALUES ($1, $2)",
            chunk_id, content
        )


class AsyncPostgresSearchRepository:
    """Async vector search repository for PostgreSQL."""

    def __init__(self, conn: asyncpg.Connection):
        self.conn = conn

    async def vector_search(self, embedding: List[float], top_k: int,
                            threshold: float = None) -> List[Dict]:
        # Convert embedding to pgvector string format
        vec_str = f"[{','.join(str(x) for x in embedding)}]"

        # Get vector results
        rows = await self.conn.fetch("""
            SELECT v.rowid, (v.embedding <=> $1::vector) AS distance
            FROM vec_chunks v
            ORDER BY v.embedding <=> $1::vector
            LIMIT $2
        """, vec_str, top_k)

        if not rows:
            return []

        chunk_ids = [row['rowid'] for row in rows]
        distances = {row['rowid']: row['distance'] for row in rows}

        # Get chunk metadata
        metadata_rows = await self.conn.fetch("""
            SELECT c.id, c.content, d.file_path, c.page
            FROM chunks c
            JOIN documents d ON c.document_id = d.id
            WHERE c.id = ANY($1)
        """, chunk_ids)

        chunk_data = {row['id']: row for row in metadata_rows}

        # Format results
        results = []
        for chunk_id in chunk_ids:
            if chunk_id in chunk_data:
                row = chunk_data[chunk_id]
                distance = distances[chunk_id]
                similarity = 1 - (distance / 2)

                if threshold is not None and similarity < threshold:
                    continue

                results.append({
                    'chunk_id': chunk_id,
                    'content': row['content'],
                    'file_path': row['file_path'],
                    'page': row['page'],
                    'score': similarity,
                    'filename': Path(row['file_path']).name if row['file_path'] else None
                })

        return results


class AsyncPostgresVectorRepository:
    """Async facade for PostgreSQL repositories."""

    def __init__(self, conn: asyncpg.Connection):
        self.conn = conn
        self.documents = AsyncPostgresDocumentRepository(conn)
        self.chunks = AsyncPostgresChunkRepository(conn)
        self.vectors = AsyncPostgresVectorChunkRepository(conn)
        self.fts = AsyncPostgresFTSChunkRepository(conn)
        self.search_repo = AsyncPostgresSearchRepository(conn)

    async def is_indexed(self, path: str, hash_val: str) -> bool:
        doc = await self.documents.find_by_hash(hash_val)
        if not doc:
            return False

        stored_path = doc['file_path']
        if stored_path != path:
            if Path(stored_path).exists():
                pass  # Duplicate file
            else:
                await self._update_path_after_move(hash_val, stored_path, path)
                logger.info(f"File moved: {stored_path} -> {path}")

        return True

    async def _update_path_after_move(self, hash_val: str, old_path: str, new_path: str):
        try:
            existing = await self.documents.find_by_path(new_path)
            if existing:
                await self.documents.delete(old_path)
                await self.conn.execute(
                    "DELETE FROM processing_progress WHERE file_path = $1",
                    old_path
                )
                logger.info(f"Removed stale record: {old_path}")
                return

            import uuid
            temp_path = f"__temp_move_{uuid.uuid4().hex}__"
            await self.documents.update_path_by_hash(hash_val, temp_path)
            await self.conn.execute(
                "UPDATE processing_progress SET file_path = $1 WHERE file_hash = $2",
                temp_path, hash_val
            )
            await self.documents.update_path_by_hash(hash_val, new_path)
            await self.conn.execute(
                "UPDATE processing_progress SET file_path = $1 WHERE file_hash = $2",
                new_path, hash_val
            )
        except Exception as e:
            logger.warning(f"Failed to update path after move: {e}")

    async def add_document(self, path: str, hash_val: str,
                           chunks: List[Dict], embeddings: List) -> int:
        extraction_method = None
        if chunks and '_extraction_method' in chunks[0]:
            extraction_method = chunks[0]['_extraction_method']

        await self.documents.delete(path)
        doc_id = await self.documents.add(path, hash_val, extraction_method)

        for idx, (chunk, emb) in enumerate(zip(chunks, embeddings)):
            chunk_id = await self.chunks.add(doc_id, chunk['content'], chunk.get('page'), idx)
            await self.vectors.add(chunk_id, emb)
            await self.fts.add(chunk_id, chunk['content'])

        logger.info(f"[pgvector] Indexed {len(chunks)} chunks for doc_id={doc_id}")
        return doc_id

    async def search(self, embedding: List, top_k: int,
                     threshold: float = None) -> List[Dict]:
        return await self.search_repo.vector_search(embedding, top_k, threshold)

    async def get_stats(self) -> Dict:
        return {
            'indexed_documents': await self.documents.count(),
            'total_chunks': await self.chunks.count()
        }


class AsyncPostgresVectorStore:
    """Async VectorStore facade for PostgreSQL + pgvector."""

    def __init__(self, config=default_config.database):
        self.config = config
        self.db_conn = AsyncPostgresConnection(config)
        self.conn: Optional[asyncpg.Connection] = None
        self.repo: Optional[AsyncPostgresVectorRepository] = None
        self._initialized = False

    async def initialize(self):
        """Initialize connection and schema."""
        if self._initialized:
            return
        self.conn = await self.db_conn.connect()
        schema = AsyncPostgresSchemaManager(self.conn, self.config)
        await schema.create_schema()
        self.repo = AsyncPostgresVectorRepository(self.conn)
        self._initialized = True
        logger.info("[AsyncPostgresVectorStore] Initialized")

    async def is_document_indexed(self, path: str, hash_val: str) -> bool:
        return await self.repo.is_indexed(path, hash_val)

    async def add_document(self, file_path: str, file_hash: str,
                           chunks: List[Dict], embeddings: List):
        await self.repo.add_document(file_path, file_hash, chunks, embeddings)

    async def search(self, query_embedding: List, top_k: int = 5,
                     threshold: float = None, query_text: Optional[str] = None,
                     use_hybrid: bool = True) -> List[Dict]:
        vector_results = await self.repo.search(query_embedding, top_k, threshold)
        # Note: Hybrid search would need async BM25 - for now just return vector results
        # TODO: Implement async hybrid search if needed
        return vector_results

    async def get_stats(self) -> Dict:
        return await self.repo.get_stats()

    async def get_document_info(self, filename: str) -> Optional[Dict]:
        docs = await self.repo.documents.search_by_pattern(filename)
        if not docs:
            return None
        doc = docs[0]
        return {
            'file_path': doc['file_path'],
            'extraction_method': doc.get('extraction_method') or 'unknown',
            'indexed_at': doc.get('indexed_at')
        }

    async def delete_document(self, file_path: str) -> Dict:
        doc = await self.repo.documents.find_by_path(file_path)
        if not doc:
            return {'found': False, 'chunks_deleted': 0, 'document_deleted': False}

        doc_id = doc['id']
        chunk_count = await self.repo.chunks.count_by_document(doc_id)
        await self.repo.documents.delete_by_id(doc_id)

        return {
            'found': True,
            'document_id': doc_id,
            'chunks_deleted': chunk_count,
            'document_deleted': True
        }

    async def close(self):
        """Close connection."""
        await self.db_conn.close()
        self._initialized = False
        logger.info("[AsyncPostgresVectorStore] Closed")
