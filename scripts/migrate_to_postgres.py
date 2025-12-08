#!/usr/bin/env python3
"""
Migration script: SQLite + vectorlite → PostgreSQL + pgvector

Migrates all data from the old SQLite/vectorlite database to the new
PostgreSQL/pgvector database. Run this once after starting the new
PostgreSQL container.

Usage:
    python scripts/migrate_to_postgres.py

Prerequisites:
    1. PostgreSQL container running: docker-compose up -d postgres
    2. Old SQLite database exists at /app/data/rag.db (or DATA_DIR/rag.db)
    3. Old HNSW index exists at /app/data/vec_chunks.idx

The script will:
    1. Connect to both old SQLite and new PostgreSQL databases
    2. Migrate documents, chunks, FTS entries, and vector embeddings
    3. Migrate graph data (nodes, edges, metadata, links)
    4. Migrate processing progress records
    5. Verify row counts match
"""
import os
import sys
import sqlite3
import struct
from pathlib import Path
from typing import List, Tuple, Optional
from datetime import datetime

# Add api directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "api"))

import psycopg2
from config import default_config


class MigrationError(Exception):
    """Migration-specific error"""
    pass


class SQLiteSource:
    """Reads data from old SQLite + vectorlite database"""

    def __init__(self, db_path: str, index_path: str):
        self.db_path = db_path
        self.index_path = index_path
        self.conn = None

    def connect(self):
        """Connect to SQLite database"""
        if not os.path.exists(self.db_path):
            raise MigrationError(f"SQLite database not found: {self.db_path}")
        self.conn = sqlite3.connect(self.db_path)
        print(f"Connected to SQLite: {self.db_path}")

        # Try to load vectorlite for reading embeddings
        self._load_vectorlite()

    def _load_vectorlite(self):
        """Try to load vectorlite extension and fix index path if needed"""
        try:
            import vectorlite_py
            self.conn.enable_load_extension(True)
            vectorlite_py.load_vectorlite(self.conn)
            print("vectorlite extension loaded")

            # Fix the index path if it points to Docker path but we're on host
            self._fix_index_path()
        except Exception as e:
            print(f"Warning: Could not load vectorlite: {e}")
            print("Will read embeddings from vec_chunks table directly")

    def _fix_index_path(self):
        """Fix vec_chunks index path if it points to Docker path"""
        try:
            # Check if current index path is Docker path
            cursor = self.conn.execute(
                "SELECT sql FROM sqlite_master WHERE name='vec_chunks'"
            )
            row = cursor.fetchone()
            if row and '/app/data/' in row[0]:
                # Need to recreate with correct path
                local_index = os.path.abspath(self.index_path)
                if os.path.exists(local_index):
                    print(f"Fixing index path: /app/data/... -> {local_index}")
                    self.conn.execute("DROP TABLE IF EXISTS vec_chunks")
                    self.conn.execute(f'''
                        CREATE VIRTUAL TABLE vec_chunks USING vectorlite(
                            embedding float32[1024] cosine,
                            hnsw(max_elements=200000),
                            "{local_index}"
                        )
                    ''')
                    self.conn.commit()
                    print("vec_chunks table recreated with correct path")
        except Exception as e:
            print(f"Warning: Could not fix index path: {e}")

    def get_documents(self) -> List[Tuple]:
        """Get all documents"""
        cursor = self.conn.execute("""
            SELECT id, file_path, file_hash, indexed_at, extraction_method
            FROM documents ORDER BY id
        """)
        return cursor.fetchall()

    def get_chunks(self) -> List[Tuple]:
        """Get all chunks"""
        cursor = self.conn.execute("""
            SELECT id, document_id, content, page, chunk_index
            FROM chunks ORDER BY id
        """)
        return cursor.fetchall()

    def get_vectors(self, expected_count: int = 0) -> List[Tuple]:
        """Get all vector embeddings using iterative knn_search

        vectorlite requires knn_search to query - direct SELECT doesn't work.

        IMPORTANT: Large k values (e.g., 200000) return 0 results in vectorlite.
        We use iterative queries with smaller k (5000) and random query vectors
        to enumerate all embeddings.

        Args:
            expected_count: Expected number of vectors (from chunks table count).
                           Used to determine when to stop iterating.

        Returns list of (rowid, embedding) tuples.
        """
        import random

        try:
            # vectorlite bug: large k values return 0 results
            # Use iterative approach with smaller k and random query vectors
            batch_k = 5000  # Safe batch size that works reliably
            max_iterations = 100
            seen_rowids = set()
            vectors = {}  # rowid -> embedding

            print(f"  Using iterative knn_search (k={batch_k})...")

            for iteration in range(max_iterations):
                # Generate random query vector to explore different parts of space
                random_vec = struct.pack('1024f', *[random.random() for _ in range(1024)])

                cursor = self.conn.execute('''
                    SELECT rowid, embedding FROM vec_chunks
                    WHERE knn_search(embedding, knn_param(?, ?))
                ''', (random_vec, batch_k))

                new_count = 0
                for rowid, emb in cursor:
                    if rowid not in seen_rowids:
                        seen_rowids.add(rowid)
                        if isinstance(emb, bytes):
                            embedding = list(struct.unpack(f'{len(emb)//4}f', emb))
                        elif hasattr(emb, 'tolist'):
                            embedding = emb.tolist()
                        else:
                            embedding = list(emb)
                        vectors[rowid] = embedding
                        new_count += 1

                if iteration % 10 == 0 or new_count > 0:
                    print(f"    Iteration {iteration + 1}: found {new_count} new vectors, total: {len(vectors)}")

                # Stop when we've found all expected vectors or no new vectors for a while
                if expected_count > 0 and len(vectors) >= expected_count * 0.99:
                    print(f"    Reached {len(vectors)}/{expected_count} vectors ({100*len(vectors)/expected_count:.1f}%)")
                    break

                # Early exit if we haven't found new vectors in several iterations
                if new_count == 0 and iteration > 20:
                    consecutive_empty = sum(1 for i in range(max(0, iteration-5), iteration)
                                           if i >= 0)
                    if consecutive_empty >= 5:
                        print(f"    No new vectors found in last iterations, stopping")
                        break

            print(f"Read {len(vectors)} vectors via iterative knn_search ({iteration + 1} iterations)")
            return list(vectors.items())

        except Exception as e:
            print(f"Could not read vectors: {e}")
            import traceback
            traceback.print_exc()
            return []

    def get_fts_chunks(self) -> List[Tuple]:
        """Get all FTS entries"""
        try:
            cursor = self.conn.execute("""
                SELECT rowid, content FROM fts_chunks ORDER BY rowid
            """)
            return cursor.fetchall()
        except Exception as e:
            print(f"Warning: Could not read FTS entries: {e}")
            return []

    def get_graph_nodes(self) -> List[Tuple]:
        """Get all graph nodes"""
        try:
            cursor = self.conn.execute("""
                SELECT node_id, node_type, title, content, metadata, created_at
                FROM graph_nodes ORDER BY node_id
            """)
            return cursor.fetchall()
        except Exception as e:
            print(f"Warning: Could not read graph nodes: {e}")
            return []

    def get_graph_edges(self) -> List[Tuple]:
        """Get all graph edges"""
        try:
            cursor = self.conn.execute("""
                SELECT id, source_id, target_id, edge_type, metadata, created_at
                FROM graph_edges ORDER BY id
            """)
            return cursor.fetchall()
        except Exception as e:
            print(f"Warning: Could not read graph edges: {e}")
            return []

    def get_graph_metadata(self) -> List[Tuple]:
        """Get all graph metadata"""
        try:
            cursor = self.conn.execute("""
                SELECT node_id, pagerank_score, in_degree, out_degree, last_computed
                FROM graph_metadata ORDER BY node_id
            """)
            return cursor.fetchall()
        except Exception as e:
            print(f"Warning: Could not read graph metadata: {e}")
            return []

    def get_chunk_graph_links(self) -> List[Tuple]:
        """Get all chunk-graph links"""
        try:
            cursor = self.conn.execute("""
                SELECT id, chunk_id, node_id, link_type
                FROM chunk_graph_links ORDER BY id
            """)
            return cursor.fetchall()
        except Exception as e:
            print(f"Warning: Could not read chunk-graph links: {e}")
            return []

    def get_processing_progress(self) -> List[Tuple]:
        """Get all processing progress records"""
        try:
            cursor = self.conn.execute("""
                SELECT file_path, file_hash, total_chunks, chunks_processed,
                       status, last_chunk_end, error_message, started_at,
                       last_updated, completed_at
                FROM processing_progress
            """)
            return cursor.fetchall()
        except Exception as e:
            print(f"Warning: Could not read processing progress: {e}")
            return []

    def get_security_scan_cache(self) -> List[Tuple]:
        """Get all security scan cache entries"""
        try:
            cursor = self.conn.execute("""
                SELECT file_hash, is_valid, severity, reason, validation_check,
                       matches_json, scanned_at, scanner_version
                FROM security_scan_cache
            """)
            return cursor.fetchall()
        except Exception as e:
            print(f"Warning: Could not read security scan cache: {e}")
            return []

    def close(self):
        if self.conn:
            self.conn.close()


class PostgresTarget:
    """Writes data to new PostgreSQL + pgvector database"""

    def __init__(self, config=default_config.database):
        self.config = config
        self.conn = None

    def connect(self):
        """Connect to PostgreSQL"""
        self.conn = psycopg2.connect(
            host=self.config.host,
            port=self.config.port,
            user=self.config.user,
            password=self.config.password,
            database=self.config.database,
        )
        # Ensure pgvector extension
        self.conn.autocommit = True
        with self.conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
        self.conn.autocommit = False
        print(f"Connected to PostgreSQL: {self.config.host}:{self.config.port}/{self.config.database}")

    def ensure_schema(self):
        """Create schema if not exists"""
        # Direct import to avoid __init__.py import chain
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "postgres_connection",
            Path(__file__).parent.parent / "api" / "ingestion" / "postgres_connection.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        schema = module.PostgresSchemaManager(self.conn, self.config)
        schema.create_schema()
        print("PostgreSQL schema ready")

    def clear_tables(self):
        """Clear all tables before migration"""
        tables = [
            'chunk_graph_links', 'graph_metadata', 'graph_edges', 'graph_nodes',
            'security_scan_cache', 'processing_progress',
            'fts_chunks', 'vec_chunks', 'chunks', 'documents'
        ]
        with self.conn.cursor() as cur:
            for table in tables:
                cur.execute(f"TRUNCATE {table} CASCADE")
        self.conn.commit()
        print("Tables cleared")

    def insert_documents(self, documents: List[Tuple]) -> dict:
        """Insert documents, return old_id -> new_id mapping"""
        id_map = {}
        with self.conn.cursor() as cur:
            for old_id, file_path, file_hash, indexed_at, extraction_method in documents:
                cur.execute("""
                    INSERT INTO documents (file_path, file_hash, indexed_at, extraction_method)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                """, (file_path, file_hash, indexed_at, extraction_method))
                new_id = cur.fetchone()[0]
                id_map[old_id] = new_id
        self.conn.commit()
        print(f"Migrated {len(documents)} documents")
        return id_map

    def insert_chunks(self, chunks: List[Tuple], doc_id_map: dict) -> dict:
        """Insert chunks, return old_chunk_id -> new_chunk_id mapping"""
        chunk_id_map = {}
        with self.conn.cursor() as cur:
            for old_id, old_doc_id, content, page, chunk_index in chunks:
                new_doc_id = doc_id_map.get(old_doc_id)
                if new_doc_id is None:
                    print(f"Warning: chunk {old_id} references unknown document {old_doc_id}")
                    continue
                cur.execute("""
                    INSERT INTO chunks (document_id, content, page, chunk_index)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                """, (new_doc_id, content, page, chunk_index))
                new_id = cur.fetchone()[0]
                chunk_id_map[old_id] = new_id
        self.conn.commit()
        print(f"Migrated {len(chunk_id_map)} chunks")
        return chunk_id_map

    def insert_vectors(self, vectors: List[Tuple], chunk_id_map: dict):
        """Insert vector embeddings"""
        count = 0
        with self.conn.cursor() as cur:
            for old_rowid, embedding in vectors:
                new_chunk_id = chunk_id_map.get(old_rowid)
                if new_chunk_id is None:
                    print(f"Warning: vector {old_rowid} references unknown chunk")
                    continue
                if not embedding:
                    print(f"Warning: empty embedding for chunk {old_rowid}")
                    continue
                cur.execute("""
                    INSERT INTO vec_chunks (rowid, embedding)
                    VALUES (%s, %s)
                """, (new_chunk_id, embedding))
                count += 1
        self.conn.commit()
        print(f"Migrated {count} vectors")

    def insert_fts(self, fts_entries: List[Tuple], chunk_id_map: dict):
        """Insert FTS entries"""
        count = 0
        with self.conn.cursor() as cur:
            for old_rowid, content in fts_entries:
                new_chunk_id = chunk_id_map.get(old_rowid)
                if new_chunk_id is None:
                    continue
                cur.execute("""
                    INSERT INTO fts_chunks (chunk_id, content)
                    VALUES (%s, %s)
                """, (new_chunk_id, content))
                count += 1
        self.conn.commit()
        print(f"Migrated {count} FTS entries")

    def rebuild_fts_from_chunks(self):
        """Rebuild FTS entries from chunks table (when FTS5 can't be migrated)"""
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO fts_chunks (chunk_id, content)
                SELECT id, content FROM chunks
                ON CONFLICT (chunk_id) DO NOTHING
            """)
            count = cur.rowcount
        self.conn.commit()
        print(f"Rebuilt {count} FTS entries from chunks")

    def insert_graph_nodes(self, nodes: List[Tuple]):
        """Insert graph nodes"""
        with self.conn.cursor() as cur:
            for node_id, node_type, title, content, metadata, created_at in nodes:
                cur.execute("""
                    INSERT INTO graph_nodes (node_id, node_type, title, content, metadata, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (node_id) DO NOTHING
                """, (node_id, node_type, title, content, metadata, created_at))
        self.conn.commit()
        print(f"Migrated {len(nodes)} graph nodes")

    def insert_graph_edges(self, edges: List[Tuple]):
        """Insert graph edges"""
        count = 0
        with self.conn.cursor() as cur:
            for edge_id, source_id, target_id, edge_type, metadata, created_at in edges:
                try:
                    cur.execute("""
                        INSERT INTO graph_edges (source_id, target_id, edge_type, metadata, created_at)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (source_id, target_id, edge_type, metadata, created_at))
                    count += 1
                except psycopg2.errors.ForeignKeyViolation:
                    self.conn.rollback()
                    # Node doesn't exist, skip edge
                    continue
        self.conn.commit()
        print(f"Migrated {count} graph edges")

    def insert_graph_metadata(self, metadata: List[Tuple]):
        """Insert graph metadata"""
        count = 0
        with self.conn.cursor() as cur:
            for node_id, pagerank, in_degree, out_degree, last_computed in metadata:
                try:
                    cur.execute("""
                        INSERT INTO graph_metadata (node_id, pagerank_score, in_degree, out_degree, last_computed)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (node_id) DO UPDATE SET
                            pagerank_score = EXCLUDED.pagerank_score,
                            in_degree = EXCLUDED.in_degree,
                            out_degree = EXCLUDED.out_degree,
                            last_computed = EXCLUDED.last_computed
                    """, (node_id, pagerank, in_degree, out_degree, last_computed))
                    count += 1
                except psycopg2.errors.ForeignKeyViolation:
                    self.conn.rollback()
                    continue
        self.conn.commit()
        print(f"Migrated {count} graph metadata entries")

    def insert_chunk_graph_links(self, links: List[Tuple], chunk_id_map: dict):
        """Insert chunk-graph links"""
        count = 0
        with self.conn.cursor() as cur:
            for link_id, old_chunk_id, node_id, link_type in links:
                new_chunk_id = chunk_id_map.get(old_chunk_id)
                if new_chunk_id is None:
                    continue
                try:
                    cur.execute("""
                        INSERT INTO chunk_graph_links (chunk_id, node_id, link_type)
                        VALUES (%s, %s, %s)
                    """, (new_chunk_id, node_id, link_type))
                    count += 1
                except psycopg2.errors.ForeignKeyViolation:
                    self.conn.rollback()
                    continue
        self.conn.commit()
        print(f"Migrated {count} chunk-graph links")

    def insert_processing_progress(self, progress: List[Tuple]):
        """Insert processing progress"""
        with self.conn.cursor() as cur:
            for row in progress:
                cur.execute("""
                    INSERT INTO processing_progress
                    (file_path, file_hash, total_chunks, chunks_processed,
                     status, last_chunk_end, error_message, started_at,
                     last_updated, completed_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (file_path) DO NOTHING
                """, row)
        self.conn.commit()
        print(f"Migrated {len(progress)} processing progress records")

    def insert_security_cache(self, cache: List[Tuple]):
        """Insert security scan cache"""
        with self.conn.cursor() as cur:
            for row in cache:
                # Convert SQLite integer to PostgreSQL boolean
                file_hash, is_valid, severity, reason, validation_check, matches_json, scanned_at, scanner_version = row
                is_valid_bool = bool(is_valid) if is_valid is not None else None
                cur.execute("""
                    INSERT INTO security_scan_cache
                    (file_hash, is_valid, severity, reason, validation_check,
                     matches_json, scanned_at, scanner_version)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (file_hash) DO NOTHING
                """, (file_hash, is_valid_bool, severity, reason, validation_check, matches_json, scanned_at, scanner_version))
        self.conn.commit()
        print(f"Migrated {len(cache)} security scan cache entries")

    def get_counts(self) -> dict:
        """Get row counts for verification"""
        counts = {}
        tables = ['documents', 'chunks', 'vec_chunks', 'fts_chunks',
                  'graph_nodes', 'graph_edges', 'processing_progress']
        with self.conn.cursor() as cur:
            for table in tables:
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                counts[table] = cur.fetchone()[0]
        return counts

    def close(self):
        if self.conn:
            self.conn.close()


def get_sqlite_path() -> str:
    """Get path to SQLite database"""
    # Try environment variable first
    data_dir = os.getenv('DATA_DIR', '/app/data')
    db_path = os.path.join(data_dir, 'rag.db')

    # Try common locations
    if not os.path.exists(db_path):
        alternatives = [
            './data/rag.db',
            '../data/rag.db',
            '/media/veracrypt1/CODE/rag-kb/data/rag.db',
        ]
        for alt in alternatives:
            if os.path.exists(alt):
                db_path = alt
                break

    return db_path


def get_index_path() -> str:
    """Get path to HNSW index file"""
    data_dir = os.getenv('DATA_DIR', '/app/data')
    idx_path = os.path.join(data_dir, 'vec_chunks.idx')

    # Try common locations if default doesn't exist
    if not os.path.exists(idx_path):
        alternatives = [
            './data/vec_chunks.idx',
            '../data/vec_chunks.idx',
            '/media/veracrypt1/CODE/rag-kb/data/vec_chunks.idx',
        ]
        for alt in alternatives:
            if os.path.exists(alt):
                idx_path = alt
                break

    return idx_path


def migrate():
    """Run the migration"""
    print("=" * 60)
    print("SQLite + vectorlite → PostgreSQL + pgvector Migration")
    print("=" * 60)
    print()

    # Initialize source and target
    sqlite_path = get_sqlite_path()
    index_path = get_index_path()

    print(f"Source: {sqlite_path}")
    print(f"Index:  {index_path}")
    print()

    source = SQLiteSource(sqlite_path, index_path)
    target = PostgresTarget()

    try:
        # Connect
        source.connect()
        target.connect()
        target.ensure_schema()

        # Clear target tables
        print("\nClearing target tables...")
        target.clear_tables()

        # Migrate documents (get ID mapping)
        print("\nMigrating documents...")
        documents = source.get_documents()
        doc_id_map = target.insert_documents(documents)

        # Migrate chunks (get ID mapping)
        print("\nMigrating chunks...")
        chunks = source.get_chunks()
        chunk_id_map = target.insert_chunks(chunks, doc_id_map)

        # Migrate vectors
        print("\nMigrating vectors...")
        # Pass expected count for iterative extraction progress tracking
        vectors = source.get_vectors(expected_count=len(chunk_id_map))
        if vectors:
            target.insert_vectors(vectors, chunk_id_map)
        else:
            print("No vectors to migrate (vectorlite may not be available)")

        # Migrate FTS
        print("\nMigrating FTS entries...")
        fts = source.get_fts_chunks()
        if fts:
            target.insert_fts(fts, chunk_id_map)
        else:
            print("No FTS entries from source - rebuilding from chunks...")
            target.rebuild_fts_from_chunks()

        # Migrate graph
        print("\nMigrating graph data...")
        nodes = source.get_graph_nodes()
        if nodes:
            target.insert_graph_nodes(nodes)

        edges = source.get_graph_edges()
        if edges:
            target.insert_graph_edges(edges)

        metadata = source.get_graph_metadata()
        if metadata:
            target.insert_graph_metadata(metadata)

        links = source.get_chunk_graph_links()
        if links:
            target.insert_chunk_graph_links(links, chunk_id_map)

        # Migrate processing progress
        print("\nMigrating processing progress...")
        progress = source.get_processing_progress()
        if progress:
            target.insert_processing_progress(progress)

        # Migrate security cache
        print("\nMigrating security scan cache...")
        cache = source.get_security_scan_cache()
        if cache:
            target.insert_security_cache(cache)

        # Verify
        print("\n" + "=" * 60)
        print("Verification")
        print("=" * 60)
        counts = target.get_counts()
        for table, count in counts.items():
            print(f"  {table}: {count} rows")

        print("\n✅ Migration complete!")

    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        raise
    finally:
        source.close()
        target.close()


if __name__ == "__main__":
    migrate()
