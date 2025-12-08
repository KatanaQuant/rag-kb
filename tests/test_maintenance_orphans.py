# Copyright (c) 2024 RAG-KB Contributors
# SPDX-License-Identifier: MIT

"""Tests for maintenance orphan cleanup endpoints

Tests for:
- POST /api/maintenance/cleanup-orphans - Clean up orphaned chunks
- OrphanCleaner operation class unit tests
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
def orphan_db():
    """Create temporary database with full schema for orphan testing"""
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
    # FTS virtual table
    conn.execute('''
        CREATE VIRTUAL TABLE fts_chunks USING fts5(content, chunk_id UNINDEXED)
    ''')
    conn.commit()
    conn.close()

    yield path

    os.close(fd)
    os.unlink(path)


class TestCleanupOrphans:
    """Test POST /api/maintenance/cleanup-orphans endpoint"""

    def test_cleanup_orphans_dry_run_shows_preview(self, client, orphan_db):
        """Cleanup orphans dry run should show what would be deleted without deleting"""
        # Create mock cleaner that returns orphan counts
        mock_cleaner = MagicMock()
        mock_cleaner.clean_all.return_value = {
            'dry_run': True,
            'orphan_chunks': {'deleted': 1},
            'orphan_vectors': {'deleted': 0},
            'orphan_fts': {'deleted': 1},
        }

        with patch('operations.operations_factory.OperationsFactory') as MockFactory:
            MockFactory.create_orphan_cleaner.return_value = mock_cleaner

            response = client.post(
                "/api/maintenance/cleanup-orphans",
                json={"dry_run": True}
            )

            assert response.status_code == 200
            data = response.json()
            assert data['dry_run'] is True
            assert data['orphan_chunks_found'] >= 1
            assert data['orphan_chunks_deleted'] == 0  # dry run - nothing deleted

    def test_cleanup_orphans_execute_removes_orphans(self, client, orphan_db):
        """Cleanup orphans with dry_run=False should actually delete orphan chunks"""
        # Create mock cleaner that returns deletion results
        mock_cleaner = MagicMock()
        mock_cleaner.clean_all.return_value = {
            'dry_run': False,
            'orphan_chunks': {'deleted': 1},
            'orphan_vectors': {'deleted': 0},
            'orphan_fts': {'deleted': 1},
        }

        with patch('operations.operations_factory.OperationsFactory') as MockFactory:
            MockFactory.create_orphan_cleaner.return_value = mock_cleaner

            response = client.post(
                "/api/maintenance/cleanup-orphans",
                json={"dry_run": False}
            )

            assert response.status_code == 200
            data = response.json()
            assert data['dry_run'] is False
            assert data['orphan_chunks_found'] >= 1
            assert data['orphan_chunks_deleted'] >= 1

    def test_cleanup_orphans_cleans_vec_chunks_and_fts(self, client, orphan_db):
        """Cleanup orphans should also clean related fts_chunks entries"""
        # Create mock cleaner that returns FTS cleanup results
        mock_cleaner = MagicMock()
        mock_cleaner.clean_all.return_value = {
            'dry_run': False,
            'orphan_chunks': {'deleted': 1},
            'orphan_vectors': {'deleted': 0},
            'orphan_fts': {'deleted': 1},
        }

        with patch('operations.operations_factory.OperationsFactory') as MockFactory:
            MockFactory.create_orphan_cleaner.return_value = mock_cleaner

            response = client.post(
                "/api/maintenance/cleanup-orphans",
                json={"dry_run": False}
            )

            assert response.status_code == 200
            data = response.json()
            assert data['orphan_chunks_deleted'] >= 1

    def test_cleanup_orphans_response_structure(self, client, orphan_db):
        """Cleanup orphans response should have correct structure"""
        mock_cleaner = MagicMock()
        mock_cleaner.clean_all.return_value = {
            'dry_run': True,
            'orphan_chunks': {'deleted': 0},
            'orphan_vectors': {'deleted': 0},
            'orphan_fts': {'deleted': 0},
        }

        with patch('operations.operations_factory.OperationsFactory') as MockFactory:
            MockFactory.create_orphan_cleaner.return_value = mock_cleaner

            response = client.post(
                "/api/maintenance/cleanup-orphans",
                json={"dry_run": True}
            )

            assert response.status_code == 200
            data = response.json()

            # Verify response structure
            assert 'dry_run' in data
            assert 'orphan_chunks_found' in data
            assert 'orphan_chunks_deleted' in data
            assert 'orphan_vec_chunks_estimate' in data
            assert 'orphan_fts_chunks_estimate' in data
            assert 'message' in data

    def test_cleanup_orphans_returns_estimates(self, client, orphan_db):
        """Cleanup orphans should return vec_chunks and fts_chunks estimates"""
        mock_cleaner = MagicMock()
        mock_cleaner.clean_all.return_value = {
            'dry_run': True,
            'orphan_chunks': {'deleted': 0},
            'orphan_vectors': {'deleted': 0},
            'orphan_fts': {'deleted': 1},
        }

        with patch('operations.operations_factory.OperationsFactory') as MockFactory:
            MockFactory.create_orphan_cleaner.return_value = mock_cleaner

            response = client.post(
                "/api/maintenance/cleanup-orphans",
                json={"dry_run": True}
            )

            assert response.status_code == 200
            data = response.json()
            assert data['orphan_fts_chunks_estimate'] == 1

    def test_cleanup_orphans_default_is_not_dry_run(self, client, orphan_db):
        """Cleanup orphans with no body should default to dry_run=False"""
        mock_cleaner = MagicMock()
        mock_cleaner.clean_all.return_value = {
            'dry_run': False,
            'orphan_chunks': {'deleted': 0},
            'orphan_vectors': {'deleted': 0},
            'orphan_fts': {'deleted': 0},
        }

        with patch('operations.operations_factory.OperationsFactory') as MockFactory:
            MockFactory.create_orphan_cleaner.return_value = mock_cleaner

            response = client.post("/api/maintenance/cleanup-orphans")

            assert response.status_code == 200
            data = response.json()
            assert data['dry_run'] is False


class TestOrphanCleaner:
    """Unit tests for OrphanCleaner operation class"""

    @pytest.fixture
    def cleaner_db(self):
        """Create temporary database for OrphanCleaner testing"""
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
        conn.execute('''
            CREATE VIRTUAL TABLE fts_chunks USING fts5(content, chunk_id UNINDEXED)
        ''')
        conn.commit()
        conn.close()

        yield path

        os.close(fd)
        os.unlink(path)

    def test_clean_dry_run_returns_counts_without_deleting(self, cleaner_db):
        """OrphanCleaner.clean(dry_run=True) returns counts without deleting"""
        # Setup orphan data
        conn = sqlite3.connect(cleaner_db)
        conn.execute('INSERT INTO chunks (id, document_id, content) VALUES (1, 999, "orphan")')
        conn.execute('INSERT INTO fts_chunks (rowid, content, chunk_id) VALUES (1, "orphan", 1)')
        conn.commit()
        conn.close()

        import sys
        sys.path.insert(0, '/media/veracrypt1/CODE/rag-kb/api')
        from operations.orphan_cleaner import OrphanCleaner

        cleaner = OrphanCleaner(db_path=cleaner_db)
        result = cleaner.clean(dry_run=True)

        assert result.dry_run is True
        assert result.orphan_chunks_found == 1
        assert result.orphan_chunks_deleted == 0

        # Verify data still exists
        conn = sqlite3.connect(cleaner_db)
        cursor = conn.execute('SELECT COUNT(*) FROM chunks')
        assert cursor.fetchone()[0] == 1
        conn.close()

    def test_clean_execute_deletes_orphan_chunks(self, cleaner_db):
        """OrphanCleaner.clean(dry_run=False) deletes orphan chunks"""
        # Setup: one valid chunk, one orphan chunk
        conn = sqlite3.connect(cleaner_db)
        conn.execute('INSERT INTO documents (id, file_path) VALUES (1, "/test/doc.pdf")')
        conn.execute('INSERT INTO chunks (id, document_id, content) VALUES (1, 1, "valid")')
        conn.execute('INSERT INTO chunks (id, document_id, content) VALUES (2, 999, "orphan")')
        conn.execute('INSERT INTO fts_chunks (rowid, content, chunk_id) VALUES (1, "valid", 1)')
        conn.execute('INSERT INTO fts_chunks (rowid, content, chunk_id) VALUES (2, "orphan", 2)')
        conn.commit()
        conn.close()

        import sys
        sys.path.insert(0, '/media/veracrypt1/CODE/rag-kb/api')
        from operations.orphan_cleaner import OrphanCleaner

        cleaner = OrphanCleaner(db_path=cleaner_db)
        result = cleaner.clean(dry_run=False)

        assert result.dry_run is False
        assert result.orphan_chunks_found == 1
        assert result.orphan_chunks_deleted == 1

        # Verify only valid chunk remains
        conn = sqlite3.connect(cleaner_db)
        cursor = conn.execute('SELECT COUNT(*) FROM chunks')
        assert cursor.fetchone()[0] == 1
        cursor = conn.execute('SELECT id FROM chunks')
        assert cursor.fetchone()[0] == 1
        conn.close()

    def test_clean_deletes_related_fts_entries(self, cleaner_db):
        """OrphanCleaner.clean() also deletes FTS entries for orphan chunks"""
        conn = sqlite3.connect(cleaner_db)
        conn.execute('INSERT INTO chunks (id, document_id, content) VALUES (1, 999, "orphan")')
        conn.execute('INSERT INTO fts_chunks (rowid, content, chunk_id) VALUES (1, "orphan", 1)')
        conn.commit()
        conn.close()

        import sys
        sys.path.insert(0, '/media/veracrypt1/CODE/rag-kb/api')
        from operations.orphan_cleaner import OrphanCleaner

        cleaner = OrphanCleaner(db_path=cleaner_db)
        result = cleaner.clean(dry_run=False)

        assert result.orphan_chunks_deleted == 1

        conn = sqlite3.connect(cleaner_db)
        cursor = conn.execute('SELECT COUNT(*) FROM fts_chunks')
        assert cursor.fetchone()[0] == 0
        conn.close()

    def test_clean_estimates_orphan_fts_chunks(self, cleaner_db):
        """OrphanCleaner.clean() estimates orphan fts_chunks from count mismatch"""
        # Setup: more FTS entries than chunks
        conn = sqlite3.connect(cleaner_db)
        conn.execute('INSERT INTO documents (id, file_path) VALUES (1, "/test/doc.pdf")')
        conn.execute('INSERT INTO chunks (id, document_id, content) VALUES (1, 1, "chunk")')
        conn.execute('INSERT INTO fts_chunks (rowid, content, chunk_id) VALUES (1, "chunk", 1)')
        conn.execute('INSERT INTO fts_chunks (rowid, content, chunk_id) VALUES (2, "extra", 999)')
        conn.execute('INSERT INTO fts_chunks (rowid, content, chunk_id) VALUES (3, "extra2", 998)')
        conn.commit()
        conn.close()

        import sys
        sys.path.insert(0, '/media/veracrypt1/CODE/rag-kb/api')
        from operations.orphan_cleaner import OrphanCleaner

        cleaner = OrphanCleaner(db_path=cleaner_db)
        result = cleaner.clean(dry_run=True)

        # 3 FTS entries - 1 chunk = 2 estimated orphans
        assert result.orphan_fts_chunks_estimate == 2

    def test_clean_result_structure(self, cleaner_db):
        """OrphanCleaner.clean() returns properly structured result"""
        import sys
        sys.path.insert(0, '/media/veracrypt1/CODE/rag-kb/api')
        from operations.orphan_cleaner import OrphanCleaner, OrphanCleanupResult

        cleaner = OrphanCleaner(db_path=cleaner_db)
        result = cleaner.clean(dry_run=True)

        assert isinstance(result, OrphanCleanupResult)
        assert isinstance(result.dry_run, bool)
        assert isinstance(result.orphan_chunks_found, int)
        assert isinstance(result.orphan_chunks_deleted, int)
        assert isinstance(result.orphan_vec_chunks_estimate, int)
        assert isinstance(result.orphan_fts_chunks_estimate, int)
        assert isinstance(result.message, str)
