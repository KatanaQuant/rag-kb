"""Integration tests for sqlite-vec to vectorlite migration.

These tests verify that the migration script correctly converts databases
and that the API layer works with migrated databases.

NOTE: These tests require both sqlite-vec and vectorlite extensions.
They are skipped when extensions are not available.
"""

import sqlite3
from pathlib import Path

import numpy as np
import pytest


def _has_sqlite_vec():
    """Check if sqlite-vec is available and loadable."""
    try:
        import sqlite_vec
        import sqlite3
        conn = sqlite3.connect(':memory:')
        sqlite_vec.load(conn)
        conn.close()
        return True
    except (ImportError, AttributeError, Exception):
        return False


def _has_vectorlite():
    """Check if vectorlite is available and loadable."""
    try:
        import vectorlite_py
        import sqlite3
        conn = sqlite3.connect(':memory:')
        conn.enable_load_extension(True)
        conn.load_extension(vectorlite_py.vectorlite_path())
        conn.close()
        return True
    except (ImportError, AttributeError, Exception):
        return False


# Skip all tests if required extensions are not available
pytestmark = pytest.mark.skipif(
    not (_has_sqlite_vec() and _has_vectorlite()),
    reason="sqlite-vec and/or vectorlite extensions not available"
)

from ingestion.vector_migration import migrate_to_vectorlite, verify_migration


EMBEDDING_DIM = 1024


@pytest.fixture
def pre_migration_db(tmp_path):
    """Create a sqlite-vec format database with sample data.

    This simulates a v2.1.x database that needs migration to vectorlite.
    """
    import sqlite_vec

    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)

    # Create schema matching production (sqlite-vec format)
    conn.execute("""
        CREATE TABLE documents (
            id INTEGER PRIMARY KEY,
            file_path TEXT UNIQUE NOT NULL,
            file_hash TEXT NOT NULL,
            indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE chunks (
            id INTEGER PRIMARY KEY,
            document_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            page INTEGER,
            FOREIGN KEY (document_id) REFERENCES documents(id)
        )
    """)
    # sqlite-vec virtual table (old format with chunk_id column)
    conn.execute(f"""
        CREATE VIRTUAL TABLE vec_chunks USING vec0(
            chunk_id INTEGER PRIMARY KEY,
            embedding FLOAT[{EMBEDDING_DIM}]
        )
    """)

    # FTS table for completeness
    conn.execute("""
        CREATE VIRTUAL TABLE fts_chunks USING fts5(
            content,
            content_rowid=id
        )
    """)

    # Insert sample documents
    conn.execute("INSERT INTO documents (file_path, file_hash) VALUES ('doc1.txt', 'hash1')")
    conn.execute("INSERT INTO documents (file_path, file_hash) VALUES ('doc2.txt', 'hash2')")

    # Insert chunks
    conn.execute("INSERT INTO chunks (document_id, content) VALUES (1, 'First document content about Python')")
    conn.execute("INSERT INTO chunks (document_id, content) VALUES (1, 'More content about testing')")
    conn.execute("INSERT INTO chunks (document_id, content) VALUES (2, 'Second document about databases')")

    # Insert embeddings (normalized random vectors)
    for chunk_id in [1, 2, 3]:
        embedding = np.random.randn(EMBEDDING_DIM).astype(np.float32)
        embedding = embedding / np.linalg.norm(embedding)  # Normalize
        conn.execute(
            "INSERT INTO vec_chunks (chunk_id, embedding) VALUES (?, ?)",
            (chunk_id, embedding.tobytes())
        )

    # Insert into FTS
    conn.execute("INSERT INTO fts_chunks (rowid, content) VALUES (1, 'First document content about Python')")
    conn.execute("INSERT INTO fts_chunks (rowid, content) VALUES (2, 'More content about testing')")
    conn.execute("INSERT INTO fts_chunks (rowid, content) VALUES (3, 'Second document about databases')")

    conn.commit()
    conn.close()

    return db_path


class TestMigrationScript:
    """Tests for the migrate_to_vectorlite() function."""

    def test_migration_converts_database(self, pre_migration_db):
        """Migration script converts sqlite-vec to vectorlite format."""
        result = migrate_to_vectorlite(str(pre_migration_db), EMBEDDING_DIM)

        assert result["success"] is True
        assert result["vectors_migrated"] == 3
        assert result["final_count"] == 3
        assert len(result["errors"]) == 0

    def test_migration_creates_index_file(self, pre_migration_db):
        """Migration creates persistent HNSW index file."""
        migrate_to_vectorlite(str(pre_migration_db), EMBEDDING_DIM)

        index_path = pre_migration_db.parent / "vec_chunks.idx"
        assert index_path.exists()
        assert index_path.stat().st_size > 0

    def test_migration_verification_passes(self, pre_migration_db):
        """verify_migration() confirms successful migration."""
        migrate_to_vectorlite(str(pre_migration_db), EMBEDDING_DIM)

        result = verify_migration(str(pre_migration_db), EMBEDDING_DIM)

        assert result["valid"] is True
        assert result["test_results"] > 0
        assert result["chunk_count"] == 3


class TestMigratedDatabaseQueries:
    """Tests for querying migrated databases directly."""

    def test_knn_search_returns_results(self, pre_migration_db):
        """knn_search works on migrated database."""
        import vectorlite_py

        migrate_to_vectorlite(str(pre_migration_db), EMBEDDING_DIM)

        # Open migrated database
        conn = sqlite3.connect(str(pre_migration_db))
        conn.enable_load_extension(True)
        conn.load_extension(vectorlite_py.vectorlite_path())

        # Create query embedding
        query = np.random.randn(EMBEDDING_DIM).astype(np.float32)
        query = query / np.linalg.norm(query)

        # Execute knn_search
        cursor = conn.execute("""
            SELECT rowid, distance FROM vec_chunks
            WHERE knn_search(embedding, knn_param(?, 5))
        """, (query.tobytes(),))

        results = cursor.fetchall()
        conn.close()

        assert len(results) == 3  # All 3 vectors returned
        assert all(isinstance(r[0], int) for r in results)  # rowids are ints
        assert all(isinstance(r[1], float) for r in results)  # distances are floats

    def test_knn_search_respects_top_k(self, pre_migration_db):
        """knn_search returns correct number of results."""
        import vectorlite_py

        migrate_to_vectorlite(str(pre_migration_db), EMBEDDING_DIM)

        conn = sqlite3.connect(str(pre_migration_db))
        conn.enable_load_extension(True)
        conn.load_extension(vectorlite_py.vectorlite_path())

        query = np.random.randn(EMBEDDING_DIM).astype(np.float32)
        query = query / np.linalg.norm(query)

        # Request only top 2
        cursor = conn.execute("""
            SELECT rowid, distance FROM vec_chunks
            WHERE knn_search(embedding, knn_param(?, 2))
        """, (query.tobytes(),))

        results = cursor.fetchall()
        conn.close()

        assert len(results) == 2


class TestAPIIntegration:
    """Tests for API layer working with migrated databases."""

    def test_search_repository_works_after_migration(self, pre_migration_db):
        """SearchRepository.vector_search() works on migrated DB."""
        import vectorlite_py
        from ingestion.search_repository import SearchRepository

        migrate_to_vectorlite(str(pre_migration_db), EMBEDDING_DIM)

        conn = sqlite3.connect(str(pre_migration_db))
        conn.enable_load_extension(True)
        conn.load_extension(vectorlite_py.vectorlite_path())

        repo = SearchRepository(conn)

        # Create query embedding
        query = np.random.randn(EMBEDDING_DIM).astype(np.float32)
        query = query / np.linalg.norm(query)

        results = repo.vector_search(query.tolist(), top_k=5)
        conn.close()

        assert len(results) > 0
        # Results should have chunk content and metadata
        for result in results:
            assert "content" in result or hasattr(result, "content")

    def test_can_insert_new_vectors_after_migration(self, pre_migration_db):
        """New vectors can be inserted after migration."""
        import vectorlite_py

        migrate_to_vectorlite(str(pre_migration_db), EMBEDDING_DIM)

        conn = sqlite3.connect(str(pre_migration_db))
        conn.enable_load_extension(True)
        conn.load_extension(vectorlite_py.vectorlite_path())

        # Insert new chunk
        conn.execute("INSERT INTO documents (file_path, file_hash) VALUES ('new.txt', 'newhash')")
        conn.execute("INSERT INTO chunks (document_id, content) VALUES (3, 'Brand new content')")

        # Insert new embedding
        new_embedding = np.random.randn(EMBEDDING_DIM).astype(np.float32)
        new_embedding = new_embedding / np.linalg.norm(new_embedding)
        conn.execute(
            "INSERT INTO vec_chunks (rowid, embedding) VALUES (?, ?)",
            (4, new_embedding.tobytes())
        )
        conn.commit()

        # Verify it's searchable
        cursor = conn.execute("""
            SELECT rowid, distance FROM vec_chunks
            WHERE knn_search(embedding, knn_param(?, 10))
        """, (new_embedding.tobytes(),))

        results = cursor.fetchall()
        conn.close()

        assert len(results) == 4  # Original 3 + new 1
        # The exact match should be first with distance ~0
        assert results[0][0] == 4
        assert results[0][1] < 0.01  # Very small distance for exact match
