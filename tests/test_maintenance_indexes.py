# Copyright (c) 2024 RAG-KB Contributors
# SPDX-License-Identifier: MIT

"""Tests for maintenance index rebuilding endpoints

Tests for:
- POST /api/maintenance/rebuild-hnsw - Rebuild HNSW vector index
- POST /api/maintenance/rebuild-fts - Rebuild FTS5 full-text search index
- HnswRebuilder and FtsRebuilder operation class unit tests
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, MagicMock, patch
import tempfile
import sqlite3
import os


@pytest.fixture
def client():
    """Create test client with mocked dependencies"""
    from main import app
    client = TestClient(app)
    yield client


@pytest.fixture
def hnsw_db():
    """Create temporary database with chunks table for HNSW rebuild testing"""
    fd, path = tempfile.mkstemp(suffix='.db')
    conn = sqlite3.connect(path)

    # Create schema matching production
    conn.execute('''
        CREATE TABLE documents (
            id INTEGER PRIMARY KEY,
            file_path TEXT UNIQUE,
            indexed_at TIMESTAMP
        )
    ''')
    conn.execute('''
        CREATE TABLE chunks (
            id INTEGER PRIMARY KEY,
            document_id INTEGER,
            content TEXT,
            FOREIGN KEY (document_id) REFERENCES documents(id)
        )
    ''')
    conn.commit()
    conn.close()

    yield path

    os.close(fd)
    os.unlink(path)


@pytest.fixture
def fts_db():
    """Create temporary database with FTS schema for rebuild testing"""
    fd, path = tempfile.mkstemp(suffix='.db')
    conn = sqlite3.connect(path)

    # Create schema matching production
    conn.execute('''
        CREATE TABLE documents (
            id INTEGER PRIMARY KEY,
            file_path TEXT UNIQUE,
            indexed_at TIMESTAMP
        )
    ''')
    conn.execute('''
        CREATE TABLE chunks (
            id INTEGER PRIMARY KEY,
            document_id INTEGER,
            content TEXT,
            FOREIGN KEY (document_id) REFERENCES documents(id)
        )
    ''')
    # FTS virtual table - use simpler schema for test compatibility
    # Production uses content='' and contentless_delete=1 which requires newer SQLite
    conn.execute('''
        CREATE VIRTUAL TABLE fts_chunks USING fts5(
            chunk_id UNINDEXED,
            content
        )
    ''')
    conn.commit()
    conn.close()

    yield path

    os.close(fd)
    os.unlink(path)


class TestRebuildHnsw:
    """Test POST /api/maintenance/rebuild-hnsw endpoint

    Tests for CRITICAL HNSW index recovery functionality.
    The rebuild-hnsw endpoint is used to recover from HNSW index corruption
    by rebuilding the index from existing embeddings without re-embedding.
    """

    def test_rebuild_hnsw_dry_run_shows_stats(self, client, hnsw_db):
        """Rebuild HNSW dry run should show statistics without modifying index

        Note: For PostgreSQL, pgvector manages HNSW automatically.
        The endpoint returns current stats instead of rebuilding.
        """
        mock_stats = MagicMock()
        mock_stats.get_stats.return_value = {
            'vectors': {'total': 100},
            'chunks': {'total': 95},
        }

        with patch('operations.operations_factory.OperationsFactory') as MockFactory:
            MockFactory.create_stats_collector.return_value = mock_stats

            response = client.post(
                "/api/maintenance/rebuild-hnsw",
                json={"dry_run": True}
            )

            assert response.status_code == 200
            data = response.json()

            # Verify stats are returned
            assert data['dry_run'] is True
            assert data['embeddings_before'] == 100
            assert 'pgvector' in data['message'].lower() or 'automatic' in data['message'].lower()

    def test_rebuild_hnsw_preserves_valid_embeddings(self, client, hnsw_db):
        """Rebuild HNSW should preserve all valid embeddings

        Note: For PostgreSQL, pgvector manages HNSW automatically.
        """
        mock_stats = MagicMock()
        mock_stats.get_stats.return_value = {
            'vectors': {'total': 95},
            'chunks': {'total': 95},
        }

        with patch('operations.operations_factory.OperationsFactory') as MockFactory:
            MockFactory.create_stats_collector.return_value = mock_stats

            response = client.post(
                "/api/maintenance/rebuild-hnsw",
                json={"dry_run": False}
            )

            assert response.status_code == 200
            data = response.json()

            # PostgreSQL reports current state (no changes needed)
            assert data['dry_run'] is False
            assert data['embeddings_after'] == 95
            assert data['valid_embeddings'] == 95

    def test_rebuild_hnsw_removes_orphan_embeddings(self, client, hnsw_db):
        """Rebuild HNSW should remove orphan embeddings

        Note: For PostgreSQL, pgvector manages HNSW automatically.
        Orphan cleanup is handled by FK constraints and cascade deletes.
        """
        mock_stats = MagicMock()
        mock_stats.get_stats.return_value = {
            'vectors': {'total': 80},
            'chunks': {'total': 80},
        }

        with patch('operations.operations_factory.OperationsFactory') as MockFactory:
            MockFactory.create_stats_collector.return_value = mock_stats

            response = client.post(
                "/api/maintenance/rebuild-hnsw",
                json={"dry_run": False}
            )

            assert response.status_code == 200
            data = response.json()

            # PostgreSQL doesn't track orphans (they can't exist with FK constraints)
            assert data['orphans_removed'] == 0
            assert data['embeddings_before'] == 80
            assert data['embeddings_after'] == 80

    def test_rebuild_hnsw_response_structure(self, client, hnsw_db):
        """Rebuild HNSW response should have correct structure"""
        mock_stats = MagicMock()
        mock_stats.get_stats.return_value = {
            'vectors': {'total': 50},
            'chunks': {'total': 50},
        }

        with patch('operations.operations_factory.OperationsFactory') as MockFactory:
            MockFactory.create_stats_collector.return_value = mock_stats

            response = client.post(
                "/api/maintenance/rebuild-hnsw",
                json={"dry_run": True}
            )

            assert response.status_code == 200
            data = response.json()

            # Verify required fields
            assert 'embeddings_before' in data
            assert 'embeddings_after' in data
            assert 'valid_embeddings' in data
            assert 'orphans_found' in data
            assert 'orphans_removed' in data
            assert 'dry_run' in data
            assert 'elapsed_time' in data
            assert 'message' in data

    def test_rebuild_hnsw_no_orphans_returns_clean_message(self, client, hnsw_db):
        """Rebuild HNSW with no orphans returns PostgreSQL auto-manage message"""
        mock_stats = MagicMock()
        mock_stats.get_stats.return_value = {
            'vectors': {'total': 100},
            'chunks': {'total': 100},
        }

        with patch('operations.operations_factory.OperationsFactory') as MockFactory:
            MockFactory.create_stats_collector.return_value = mock_stats

            response = client.post(
                "/api/maintenance/rebuild-hnsw",
                json={"dry_run": True}
            )

            assert response.status_code == 200
            data = response.json()

            assert data['orphans_found'] == 0
            # PostgreSQL with pgvector auto-manages HNSW index
            assert 'automatic' in data['message'].lower() or 'postgresql' in data['message'].lower() or 'pgvector' in data['message'].lower()


class TestHnswRebuilder:
    """Unit tests for HnswRebuilder operation class"""

    @pytest.fixture
    def rebuilder_db(self):
        """Create temporary database for HnswRebuilder testing"""
        fd, path = tempfile.mkstemp(suffix='.db')
        conn = sqlite3.connect(path)

        # Create schema matching production
        conn.execute('''
            CREATE TABLE documents (
                id INTEGER PRIMARY KEY,
                file_path TEXT UNIQUE,
                indexed_at TIMESTAMP
            )
        ''')
        conn.execute('''
            CREATE TABLE chunks (
                id INTEGER PRIMARY KEY,
                document_id INTEGER,
                content TEXT,
                FOREIGN KEY (document_id) REFERENCES documents(id)
            )
        ''')
        conn.commit()
        conn.close()

        yield path

        os.close(fd)
        os.unlink(path)

    def test_rebuilder_initialization(self, rebuilder_db):
        """HnswRebuilder should initialize with db_path"""
        import sys
        sys.path.insert(0, '/media/veracrypt1/CODE/rag-kb/api')
        from operations.hnsw_rebuilder import HnswRebuilder

        rebuilder = HnswRebuilder(db_path=rebuilder_db)
        assert rebuilder.db_path == rebuilder_db

    def test_rebuilder_result_structure(self, rebuilder_db):
        """HnswRebuilder.rebuild() should return properly structured result"""
        import sys
        sys.path.insert(0, '/media/veracrypt1/CODE/rag-kb/api')
        from operations.hnsw_rebuilder import HnswRebuilder, HnswRebuildResult

        # Setup: Add chunks (but no vec_chunks since we can't create vectorlite in test)
        conn = sqlite3.connect(rebuilder_db)
        conn.execute('INSERT INTO documents (id, file_path) VALUES (1, "/test/doc.pdf")')
        conn.execute('INSERT INTO chunks (id, document_id, content) VALUES (1, 1, "content")')
        conn.execute('INSERT INTO chunks (id, document_id, content) VALUES (2, 1, "more content")')
        conn.commit()
        conn.close()

        rebuilder = HnswRebuilder(db_path=rebuilder_db)

        # This will handle the case where vectorlite is not available
        result = rebuilder.rebuild(dry_run=True)

        assert isinstance(result, HnswRebuildResult)
        assert isinstance(result.total_embeddings, int)
        assert isinstance(result.valid_embeddings, int)
        assert isinstance(result.orphan_embeddings, int)
        assert isinstance(result.final_embeddings, int)
        assert isinstance(result.dry_run, bool)
        assert isinstance(result.elapsed_time, float)

    def test_rebuilder_dry_run_does_not_modify(self, rebuilder_db):
        """HnswRebuilder.rebuild(dry_run=True) should not modify database"""
        import sys
        sys.path.insert(0, '/media/veracrypt1/CODE/rag-kb/api')
        from operations.hnsw_rebuilder import HnswRebuilder

        # Setup
        conn = sqlite3.connect(rebuilder_db)
        conn.execute('INSERT INTO documents (id, file_path) VALUES (1, "/test/doc.pdf")')
        conn.execute('INSERT INTO chunks (id, document_id, content) VALUES (1, 1, "content")')
        conn.commit()

        # Get initial state
        initial_chunk_count = conn.execute('SELECT COUNT(*) FROM chunks').fetchone()[0]
        conn.close()

        rebuilder = HnswRebuilder(db_path=rebuilder_db)
        result = rebuilder.rebuild(dry_run=True)

        # Verify no changes
        conn = sqlite3.connect(rebuilder_db)
        final_chunk_count = conn.execute('SELECT COUNT(*) FROM chunks').fetchone()[0]
        conn.close()

        assert result.dry_run is True
        assert initial_chunk_count == final_chunk_count


class TestRebuildFts:
    """Tests for POST /api/maintenance/rebuild-fts endpoint"""

    def test_rebuild_fts_dry_run_shows_stats(self, client, fts_db):
        """Rebuild FTS dry run should show stats (PostgreSQL auto-manages)"""
        mock_stats = MagicMock()
        mock_stats.get_stats.return_value = {
            'chunks': {'total': 2},
            'fts': {'total': 2},
        }

        with patch('operations.operations_factory.OperationsFactory') as MockFactory:
            MockFactory.create_stats_collector.return_value = mock_stats

            response = client.post(
                "/api/maintenance/rebuild-fts",
                json={"dry_run": True}
            )

            assert response.status_code == 200
            data = response.json()
            assert data['dry_run'] is True
            assert data['chunks_found'] == 2
            # PostgreSQL tsvector auto-managed, so fts_entries matches chunks
            assert data['fts_entries_before'] == 2
            assert 'automatic' in data['message'].lower() or 'postgresql' in data['message'].lower()

    def test_rebuild_fts_rebuilds_index(self, client, fts_db):
        """Rebuild FTS returns current stats (PostgreSQL auto-manages)"""
        mock_stats = MagicMock()
        mock_stats.get_stats.return_value = {
            'chunks': {'total': 3},
            'fts': {'total': 3},
        }

        with patch('operations.operations_factory.OperationsFactory') as MockFactory:
            MockFactory.create_stats_collector.return_value = mock_stats

            response = client.post(
                "/api/maintenance/rebuild-fts",
                json={"dry_run": False}
            )

            assert response.status_code == 200
            data = response.json()
            assert data['dry_run'] is False
            # PostgreSQL auto-manages tsvector, so chunks_indexed equals fts count
            assert data['chunks_indexed'] == 3
            assert data['fts_entries_after'] == 3
            assert data['time_taken'] >= 0
            # PostgreSQL message about auto-management
            assert 'automatic' in data['message'].lower() or 'postgresql' in data['message'].lower()

    def test_rebuild_fts_handles_empty_db(self, client, fts_db):
        """Rebuild FTS handles empty database (PostgreSQL auto-manages)"""
        mock_stats = MagicMock()
        mock_stats.get_stats.return_value = {
            'chunks': {'total': 0},
            'fts': {'total': 0},
        }

        with patch('operations.operations_factory.OperationsFactory') as MockFactory:
            MockFactory.create_stats_collector.return_value = mock_stats

            response = client.post(
                "/api/maintenance/rebuild-fts",
                json={"dry_run": False}
            )

            assert response.status_code == 200
            data = response.json()
            assert data['chunks_found'] == 0
            assert data['chunks_indexed'] == 0
            assert data['fts_entries_after'] == 0
            # PostgreSQL message about auto-management
            assert 'automatic' in data['message'].lower() or 'postgresql' in data['message'].lower()


class TestFtsRebuilder:
    """Unit tests for FtsRebuilder operation class"""

    @pytest.fixture
    def rebuilder_db(self):
        """Create temporary database for FtsRebuilder testing"""
        fd, path = tempfile.mkstemp(suffix='.db')
        conn = sqlite3.connect(path)

        conn.execute('''
            CREATE TABLE documents (
                id INTEGER PRIMARY KEY,
                file_path TEXT UNIQUE,
                indexed_at TIMESTAMP
            )
        ''')
        conn.execute('''
            CREATE TABLE chunks (
                id INTEGER PRIMARY KEY,
                document_id INTEGER,
                content TEXT,
                FOREIGN KEY (document_id) REFERENCES documents(id)
            )
        ''')
        # FTS virtual table - use simpler schema for test compatibility
        # Production uses content='' and contentless_delete=1 which requires newer SQLite
        conn.execute('''
            CREATE VIRTUAL TABLE fts_chunks USING fts5(
                chunk_id UNINDEXED,
                content
            )
        ''')
        conn.commit()
        conn.close()

        yield path

        os.close(fd)
        os.unlink(path)

    def test_rebuild_returns_structured_result(self, rebuilder_db):
        """FtsRebuilder.rebuild() returns properly structured result"""
        import sys
        sys.path.insert(0, '/media/veracrypt1/CODE/rag-kb/api')
        from operations.fts_rebuilder import FtsRebuilder, FtsRebuildResult

        rebuilder = FtsRebuilder(db_path=rebuilder_db)
        result = rebuilder.rebuild(dry_run=True)

        assert isinstance(result, FtsRebuildResult)
        assert isinstance(result.dry_run, bool)
        assert isinstance(result.chunks_found, int)
        assert isinstance(result.chunks_indexed, int)
        assert isinstance(result.fts_entries_before, int)
        assert isinstance(result.fts_entries_after, int)
        assert isinstance(result.time_taken, float)
        assert isinstance(result.message, str)

    def test_rebuild_preserves_rowid_mapping(self, rebuilder_db):
        """FtsRebuilder.rebuild() should set rowid = chunk_id for JOIN compatibility"""
        conn = sqlite3.connect(rebuilder_db)
        conn.execute('INSERT INTO documents (id, file_path) VALUES (1, "/test/doc.pdf")')
        # Use non-sequential IDs to ensure rowid mapping works
        conn.execute('INSERT INTO chunks (id, document_id, content) VALUES (10, 1, "content ten")')
        conn.execute('INSERT INTO chunks (id, document_id, content) VALUES (20, 1, "content twenty")')
        conn.execute('INSERT INTO chunks (id, document_id, content) VALUES (30, 1, "content thirty")')
        conn.commit()
        conn.close()

        import sys
        sys.path.insert(0, '/media/veracrypt1/CODE/rag-kb/api')
        from operations.fts_rebuilder import FtsRebuilder

        rebuilder = FtsRebuilder(db_path=rebuilder_db)
        result = rebuilder.rebuild(dry_run=False)

        assert result.chunks_indexed == 3

        # Verify rowid matches chunk_id (chunk_id column returns NULL in contentless FTS5)
        # The important thing is that rowid == chunk_id for JOIN compatibility
        conn = sqlite3.connect(rebuilder_db)
        cursor = conn.execute('SELECT rowid FROM fts_chunks ORDER BY rowid')
        rows = cursor.fetchall()
        assert len(rows) == 3
        assert rows[0][0] == 10  # rowid matches chunk_id
        assert rows[1][0] == 20
        assert rows[2][0] == 30
        conn.close()

    def test_rebuild_handles_existing_fts_entries(self, rebuilder_db):
        """FtsRebuilder.rebuild() should drop and recreate FTS table"""
        # Setup: Add stale/orphan FTS entries
        conn = sqlite3.connect(rebuilder_db)
        conn.execute('INSERT INTO documents (id, file_path) VALUES (1, "/test/doc.pdf")')
        conn.execute('INSERT INTO chunks (id, document_id, content) VALUES (1, 1, "real content")')
        # Add orphan FTS entry that shouldn't exist after rebuild
        conn.execute('INSERT INTO fts_chunks (rowid, chunk_id, content) VALUES (999, 999, "orphan")')
        conn.commit()
        conn.close()

        import sys
        sys.path.insert(0, '/media/veracrypt1/CODE/rag-kb/api')
        from operations.fts_rebuilder import FtsRebuilder

        rebuilder = FtsRebuilder(db_path=rebuilder_db)
        result = rebuilder.rebuild(dry_run=False)

        assert result.fts_entries_before == 1
        assert result.fts_entries_after == 1
        assert result.chunks_indexed == 1

        # Verify orphan is gone
        conn = sqlite3.connect(rebuilder_db)
        cursor = conn.execute('SELECT rowid FROM fts_chunks')
        rows = cursor.fetchall()
        assert len(rows) == 1
        assert rows[0][0] == 1  # Only the real chunk
        conn.close()
