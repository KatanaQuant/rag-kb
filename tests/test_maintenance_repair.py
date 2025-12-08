# Copyright (c) 2024 RAG-KB Contributors
# SPDX-License-Identifier: MIT

"""Tests for maintenance index repair endpoints

Tests for:
- POST /api/maintenance/repair-indexes - Combined HNSW + FTS index repair
- IndexRepairer operation class unit tests
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
def repair_db():
    """Create temporary database for repair-indexes testing"""
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


class TestRepairIndexes:
    """Test POST /api/maintenance/repair-indexes endpoint

    Tests for combined HNSW + FTS index repair functionality.
    This endpoint runs both rebuilders in sequence for complete index maintenance.
    """

    def test_repair_indexes_dry_run_shows_combined_stats(self, client, repair_db):
        """Repair indexes dry run should show stats for both HNSW and FTS"""
        mock_stats = MagicMock()
        mock_stats.get_stats.return_value = {
            'vectors': {'total': 100},
            'chunks': {'total': 95},
            'fts': {'total': 90},
        }

        with patch('operations.operations_factory.OperationsFactory') as MockFactory:
            MockFactory.create_stats_collector.return_value = mock_stats

            response = client.post(
                "/api/maintenance/repair-indexes",
                json={"dry_run": True}
            )

            assert response.status_code == 200
            data = response.json()

            # Verify top-level fields
            assert data['dry_run'] is True
            assert 'total_time' in data
            assert 'hnsw' in data
            assert 'fts' in data
            assert 'message' in data

            # Verify HNSW stats (PostgreSQL auto-manages, so no orphans)
            assert data['hnsw']['embeddings_before'] == 100
            assert data['hnsw']['orphans_found'] == 0

            # Verify FTS stats
            assert data['fts']['chunks_found'] == 95

    def test_repair_indexes_executes_both_rebuilds(self, client, repair_db):
        """Repair indexes should execute both HNSW and FTS rebuilds (PostgreSQL auto-manages)"""
        mock_stats = MagicMock()
        mock_stats.get_stats.return_value = {
            'vectors': {'total': 95},
            'chunks': {'total': 95},
            'fts': {'total': 95},
        }

        with patch('operations.operations_factory.OperationsFactory') as MockFactory:
            MockFactory.create_stats_collector.return_value = mock_stats

            response = client.post(
                "/api/maintenance/repair-indexes",
                json={"dry_run": False}
            )

            assert response.status_code == 200
            data = response.json()

            assert data['dry_run'] is False
            # PostgreSQL auto-manages indexes, no orphans
            assert data['hnsw']['orphans_removed'] == 0
            assert data['hnsw']['embeddings_after'] == 95
            # FTS stats reflect current state
            assert data['fts']['chunks_indexed'] == 95
            assert data['fts']['fts_entries_after'] == 95

    def test_repair_indexes_response_structure(self, client, repair_db):
        """Repair indexes response should have correct structure"""
        mock_stats = MagicMock()
        mock_stats.get_stats.return_value = {
            'vectors': {'total': 50},
            'chunks': {'total': 50},
            'fts': {'total': 50},
        }

        with patch('operations.operations_factory.OperationsFactory') as MockFactory:
            MockFactory.create_stats_collector.return_value = mock_stats

            response = client.post(
                "/api/maintenance/repair-indexes",
                json={"dry_run": True}
            )

            assert response.status_code == 200
            data = response.json()

            # Verify top-level structure
            assert 'dry_run' in data
            assert 'total_time' in data
            assert 'hnsw' in data
            assert 'fts' in data
            assert 'message' in data

            # Verify HNSW structure
            hnsw = data['hnsw']
            assert 'embeddings_before' in hnsw
            assert 'embeddings_after' in hnsw
            assert 'valid_embeddings' in hnsw
            assert 'orphans_found' in hnsw
            assert 'orphans_removed' in hnsw
            assert 'elapsed_time' in hnsw

            # Verify FTS structure
            fts = data['fts']
            assert 'chunks_found' in fts
            assert 'chunks_indexed' in fts
            assert 'fts_entries_before' in fts
            assert 'fts_entries_after' in fts
            assert 'time_taken' in fts

    def test_repair_indexes_default_is_not_dry_run(self, client, repair_db):
        """Repair indexes with no body should default to dry_run=False"""
        mock_stats = MagicMock()
        mock_stats.get_stats.return_value = {
            'vectors': {'total': 0},
            'chunks': {'total': 0},
            'fts': {'total': 0},
        }

        with patch('operations.operations_factory.OperationsFactory') as MockFactory:
            MockFactory.create_stats_collector.return_value = mock_stats

            response = client.post("/api/maintenance/repair-indexes")

            assert response.status_code == 200
            data = response.json()
            assert data['dry_run'] is False


class TestIndexRepairer:
    """Unit tests for IndexRepairer operation class"""

    @pytest.fixture
    def repairer_db(self):
        """Create temporary database for IndexRepairer testing"""
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

    def test_repairer_initialization(self, repairer_db):
        """IndexRepairer should initialize with db_path"""
        import sys
        sys.path.insert(0, '/media/veracrypt1/CODE/rag-kb/api')
        from operations.index_repairer import IndexRepairer

        repairer = IndexRepairer(db_path=repairer_db)
        assert repairer.db_path == repairer_db
        assert repairer.hnsw_rebuilder is not None
        assert repairer.fts_rebuilder is not None

    def test_repairer_result_structure(self, repairer_db):
        """IndexRepairer.repair() should return properly structured result"""
        import sys
        sys.path.insert(0, '/media/veracrypt1/CODE/rag-kb/api')
        from operations.index_repairer import IndexRepairer, IndexRepairResult

        repairer = IndexRepairer(db_path=repairer_db)
        result = repairer.repair(dry_run=True)

        assert isinstance(result, IndexRepairResult)
        assert isinstance(result.dry_run, bool)
        assert isinstance(result.total_time, float)
        assert result.hnsw_result is not None
        assert result.fts_result is not None
        assert isinstance(result.message, str)

    def test_repairer_runs_both_rebuilders(self, repairer_db):
        """IndexRepairer.repair() should run both HNSW and FTS rebuilders"""
        # Setup: Add test data
        conn = sqlite3.connect(repairer_db)
        conn.execute('INSERT INTO documents (id, file_path) VALUES (1, "/test/doc.pdf")')
        conn.execute('INSERT INTO chunks (id, document_id, content) VALUES (1, 1, "content")')
        conn.commit()
        conn.close()

        import sys
        sys.path.insert(0, '/media/veracrypt1/CODE/rag-kb/api')
        from operations.index_repairer import IndexRepairer

        repairer = IndexRepairer(db_path=repairer_db)
        result = repairer.repair(dry_run=False)

        # FTS should have been rebuilt
        assert result.fts_result.chunks_indexed == 1
        assert result.fts_result.fts_entries_after == 1

        # Verify FTS was actually rebuilt
        conn = sqlite3.connect(repairer_db)
        cursor = conn.execute('SELECT COUNT(*) FROM fts_chunks')
        assert cursor.fetchone()[0] == 1
        conn.close()

    def test_repairer_dry_run_does_not_modify(self, repairer_db):
        """IndexRepairer.repair(dry_run=True) should not modify database"""
        # Setup: Empty FTS, should stay empty in dry_run
        conn = sqlite3.connect(repairer_db)
        conn.execute('INSERT INTO documents (id, file_path) VALUES (1, "/test/doc.pdf")')
        conn.execute('INSERT INTO chunks (id, document_id, content) VALUES (1, 1, "content")')
        # FTS is empty
        conn.commit()
        conn.close()

        import sys
        sys.path.insert(0, '/media/veracrypt1/CODE/rag-kb/api')
        from operations.index_repairer import IndexRepairer

        repairer = IndexRepairer(db_path=repairer_db)
        result = repairer.repair(dry_run=True)

        assert result.dry_run is True
        # FTS should not have been rebuilt
        assert result.fts_result.chunks_indexed == 0

        # Verify FTS is still empty
        conn = sqlite3.connect(repairer_db)
        cursor = conn.execute('SELECT COUNT(*) FROM fts_chunks')
        assert cursor.fetchone()[0] == 0
        conn.close()

    def test_repairer_message_includes_both_summaries(self, repairer_db):
        """IndexRepairer.repair() message should summarize both operations"""
        conn = sqlite3.connect(repairer_db)
        conn.execute('INSERT INTO documents (id, file_path) VALUES (1, "/test/doc.pdf")')
        conn.execute('INSERT INTO chunks (id, document_id, content) VALUES (1, 1, "content")')
        conn.commit()
        conn.close()

        import sys
        sys.path.insert(0, '/media/veracrypt1/CODE/rag-kb/api')
        from operations.index_repairer import IndexRepairer

        repairer = IndexRepairer(db_path=repairer_db)
        result = repairer.repair(dry_run=True)

        # Message should mention both HNSW and FTS
        assert 'HNSW' in result.message
        assert 'FTS' in result.message
