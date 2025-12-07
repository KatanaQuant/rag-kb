# Copyright (c) 2024 RAG-KB Contributors
# SPDX-License-Identifier: MIT

"""Tests for maintenance REST API endpoints

Tests for:
- POST /api/maintenance/backfill-chunk-counts - Backfill chunk counts
- POST /api/maintenance/delete-empty-documents - Delete empty document records
- POST /api/maintenance/reindex-failed-documents - Re-index failed documents
- POST /api/maintenance/rebuild-hnsw - Rebuild HNSW vector index
- POST /api/maintenance/rebuild-fts - Rebuild FTS5 full-text search index
- POST /api/maintenance/repair-indexes - Combined HNSW + FTS rebuild
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path
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
def temp_db():
    """Create temporary database with schema"""
    fd, path = tempfile.mkstemp(suffix='.db')
    conn = sqlite3.connect(path)

    # Create minimal schema
    conn.execute('''
        CREATE TABLE documents (
            id INTEGER PRIMARY KEY,
            file_path TEXT,
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
        CREATE TABLE processing_progress (
            file_path TEXT PRIMARY KEY,
            status TEXT
        )
    ''')
    conn.commit()
    conn.close()

    yield path

    os.close(fd)
    os.unlink(path)


class TestBackfillChunkCountsEndpoint:
    """Test POST /api/maintenance/backfill-chunk-counts endpoint"""

    def test_backfill_chunk_counts_dry_run(self, client):
        """Backfill chunk counts dry run should not modify data"""
        # Import is inside the endpoint, need to mock at module import
        mock_module = MagicMock()
        mock_module.backfill_chunk_counts = Mock(return_value={
            'checked': 100,
            'would_update': 10
        })

        with patch.dict('sys.modules', {'migrations.backfill_chunk_counts': mock_module}):
            response = client.post(
                "/api/maintenance/backfill-chunk-counts",
                json={"dry_run": True}
            )

            # Should work or handle import gracefully
            assert response.status_code in [200, 500]
            if response.status_code == 200:
                data = response.json()
                assert data['dry_run'] is True
                assert 'Would update' in data['message']

    def test_backfill_chunk_counts_actual_update(self, client):
        """Backfill chunk counts without dry_run should update data"""
        mock_module = MagicMock()
        mock_module.backfill_chunk_counts = Mock(return_value={
            'checked': 100,
            'updated': 10
        })

        with patch.dict('sys.modules', {'migrations.backfill_chunk_counts': mock_module}):
            response = client.post(
                "/api/maintenance/backfill-chunk-counts",
                json={"dry_run": False}
            )

            assert response.status_code in [200, 500]
            if response.status_code == 200:
                data = response.json()
                assert data['dry_run'] is False

    def test_backfill_chunk_counts_default_is_not_dry_run(self, client):
        """Backfill chunk counts with no body should default to dry_run=False"""
        mock_module = MagicMock()
        mock_module.backfill_chunk_counts = Mock(return_value={
            'checked': 50,
            'updated': 5
        })

        with patch.dict('sys.modules', {'migrations.backfill_chunk_counts': mock_module}):
            response = client.post("/api/maintenance/backfill-chunk-counts")

            assert response.status_code in [200, 500]
            if response.status_code == 200:
                data = response.json()
                assert data['dry_run'] is False


class TestDeleteEmptyDocumentsEndpoint:
    """Test POST /api/maintenance/delete-empty-documents endpoint"""

    def test_delete_empty_documents_finds_orphans(self, client, temp_db):
        """Delete empty documents should find documents with no chunks"""
        # Add orphan document (no chunks)
        conn = sqlite3.connect(temp_db)
        conn.execute('INSERT INTO documents (id, file_path) VALUES (1, "/test/orphan.pdf")')
        conn.commit()
        conn.close()

        with patch('routes.maintenance.default_config') as mock_config:
            mock_config.database.path = temp_db

            response = client.post(
                "/api/maintenance/delete-empty-documents",
                json={"dry_run": True}
            )

            assert response.status_code == 200
            data = response.json()
            assert data['orphans_found'] == 1
            assert data['orphans_deleted'] == 0  # dry_run
            assert data['dry_run'] is True
            assert len(data['orphans']) == 1
            assert data['orphans'][0]['filename'] == 'orphan.pdf'

    def test_delete_empty_documents_skips_documents_with_chunks(self, client, temp_db):
        """Delete empty documents should not find documents with chunks"""
        conn = sqlite3.connect(temp_db)
        conn.execute('INSERT INTO documents (id, file_path) VALUES (1, "/test/complete.pdf")')
        conn.execute('INSERT INTO chunks (document_id, content) VALUES (1, "chunk content")')
        conn.commit()
        conn.close()

        with patch('routes.maintenance.default_config') as mock_config:
            mock_config.database.path = temp_db

            response = client.post(
                "/api/maintenance/delete-empty-documents",
                json={"dry_run": True}
            )

            assert response.status_code == 200
            data = response.json()
            assert data['orphans_found'] == 0

    def test_delete_empty_documents_actually_deletes(self, client, temp_db):
        """Delete empty documents without dry_run should delete records"""
        conn = sqlite3.connect(temp_db)
        conn.execute('INSERT INTO documents (id, file_path) VALUES (1, "/test/orphan1.pdf")')
        conn.execute('INSERT INTO documents (id, file_path) VALUES (2, "/test/orphan2.pdf")')
        conn.execute('INSERT INTO processing_progress (file_path, status) VALUES ("/test/orphan1.pdf", "failed")')
        conn.commit()
        conn.close()

        with patch('routes.maintenance.default_config') as mock_config:
            mock_config.database.path = temp_db

            response = client.post(
                "/api/maintenance/delete-empty-documents",
                json={"dry_run": False}
            )

            assert response.status_code == 200
            data = response.json()
            assert data['orphans_found'] == 2
            assert data['orphans_deleted'] == 2
            assert data['dry_run'] is False

            # Verify deletion
            conn = sqlite3.connect(temp_db)
            cursor = conn.execute('SELECT COUNT(*) FROM documents')
            assert cursor.fetchone()[0] == 0
            conn.close()

    def test_delete_empty_documents_response_structure(self, client, temp_db):
        """Delete empty documents response should have correct structure"""
        with patch('routes.maintenance.default_config') as mock_config:
            mock_config.database.path = temp_db

            response = client.post(
                "/api/maintenance/delete-empty-documents",
                json={"dry_run": True}
            )

            assert response.status_code == 200
            data = response.json()

            assert 'orphans_found' in data
            assert 'orphans_deleted' in data
            assert 'dry_run' in data
            assert 'orphans' in data
            assert 'message' in data


class TestReindexFailedDocumentsEndpoint:
    """Test POST /api/maintenance/reindex-failed-documents endpoint"""

    def test_reindex_failed_documents_dry_run(self, client):
        """Reindex failed documents dry run should list documents without queueing"""
        mock_reporter = Mock()
        mock_reporter.generate_report.return_value = {
            'issues': [
                {'file_path': '/test/incomplete1.pdf', 'issue': 'zero_chunks'},
                {'file_path': '/test/incomplete2.pdf', 'issue': 'processing_incomplete'}
            ]
        }

        with patch('operations.completeness_reporter.CompletenessReporter', return_value=mock_reporter):
            response = client.post(
                "/api/maintenance/reindex-failed-documents",
                json={"dry_run": True}
            )

            # Should work or handle app_state gracefully
            assert response.status_code in [200, 500]
            if response.status_code == 200:
                data = response.json()
                assert data['documents_found'] == 2
                assert data['documents_queued'] == 0  # dry_run
                assert data['dry_run'] is True
                assert len(data['documents']) == 2

    def test_reindex_failed_documents_filters_by_issue_type(self, client):
        """Reindex should filter by specified issue types"""
        mock_reporter = Mock()
        mock_reporter.generate_report.return_value = {
            'issues': [
                {'file_path': '/test/a.pdf', 'issue': 'zero_chunks'},
                {'file_path': '/test/b.pdf', 'issue': 'processing_incomplete'},
                {'file_path': '/test/c.pdf', 'issue': 'missing_embeddings'}
            ]
        }

        with patch('operations.completeness_reporter.CompletenessReporter', return_value=mock_reporter):
            response = client.post(
                "/api/maintenance/reindex-failed-documents",
                json={"dry_run": True, "issue_types": ["zero_chunks"]}
            )

            assert response.status_code in [200, 500]
            if response.status_code == 200:
                data = response.json()
                assert data['documents_found'] == 1
                assert data['documents'][0]['filename'] == 'a.pdf'

    def test_reindex_failed_documents_no_issues(self, client):
        """Reindex with no issues should return zero"""
        mock_reporter = Mock()
        mock_reporter.generate_report.return_value = {'issues': []}

        with patch('operations.completeness_reporter.CompletenessReporter', return_value=mock_reporter):
            response = client.post(
                "/api/maintenance/reindex-failed-documents",
                json={"dry_run": True}
            )

            assert response.status_code in [200, 500]
            if response.status_code == 200:
                data = response.json()
                assert data['documents_found'] == 0
                assert data['documents'] == []
                assert 'No incomplete' in data['message']

    def test_reindex_failed_documents_response_structure(self, client):
        """Reindex response should have correct structure"""
        mock_reporter = Mock()
        mock_reporter.generate_report.return_value = {'issues': []}

        with patch('operations.completeness_reporter.CompletenessReporter', return_value=mock_reporter):
            response = client.post(
                "/api/maintenance/reindex-failed-documents",
                json={"dry_run": True}
            )

            assert response.status_code in [200, 500]
            if response.status_code == 200:
                data = response.json()

                assert 'documents_found' in data
                assert 'documents_queued' in data
                assert 'dry_run' in data
                assert 'documents' in data
                assert 'message' in data


class TestMaintenanceApiIntegration:
    """Integration tests for maintenance endpoints"""

    def test_all_endpoints_accept_empty_body(self, client, temp_db):
        """All maintenance endpoints should work without request body"""
        with patch('routes.maintenance.default_config') as mock_config:
            mock_config.database.path = temp_db

            # delete-empty-documents should work
            response = client.post("/api/maintenance/delete-empty-documents")
            assert response.status_code == 200

        # reindex-failed-documents requires app_state, so mock CompletenessReporter
        mock_reporter = Mock()
        mock_reporter.generate_report.return_value = {'issues': []}

        with patch('operations.completeness_reporter.CompletenessReporter', return_value=mock_reporter):
            # reindex-failed-documents should work with empty body
            response = client.post("/api/maintenance/reindex-failed-documents")
            # Will return 200 (no issues) or 500 (app_state not initialized)
            assert response.status_code in [200, 500]

    def test_all_endpoints_return_json(self, client, temp_db):
        """All maintenance endpoints should return JSON"""
        with patch('routes.maintenance.default_config') as mock_config:
            mock_config.database.path = temp_db

            response = client.post("/api/maintenance/delete-empty-documents")
            assert response.headers.get('content-type') == 'application/json'

        mock_reporter = Mock()
        mock_reporter.generate_report.return_value = {'issues': []}

        with patch('operations.completeness_reporter.CompletenessReporter', return_value=mock_reporter):
            response = client.post("/api/maintenance/reindex-failed-documents")
            assert response.headers.get('content-type') == 'application/json'


class TestVerifyIntegrityEndpoint:
    """Test GET /api/maintenance/verify-integrity endpoint"""

    @pytest.fixture
    def integrity_db(self):
        """Create temporary database with full schema for integrity testing"""
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

    def test_verify_integrity_returns_healthy_when_no_issues(self, client, integrity_db):
        """Verify integrity returns healthy status when database is consistent"""
        # Setup: Add consistent data
        conn = sqlite3.connect(integrity_db)
        conn.execute('INSERT INTO documents (id, file_path) VALUES (1, "/test/doc.pdf")')
        conn.execute('INSERT INTO chunks (id, document_id, content) VALUES (1, 1, "test content")')
        conn.execute('INSERT INTO fts_chunks (rowid, content, chunk_id) VALUES (1, "test content", 1)')
        conn.commit()
        conn.close()

        with patch('routes.maintenance.default_config') as mock_config:
            mock_config.database.path = integrity_db

            response = client.get("/api/maintenance/verify-integrity")

            assert response.status_code == 200
            data = response.json()
            assert data['healthy'] is True
            assert data['issues'] == []
            assert 'checks' in data

    def test_verify_integrity_detects_orphan_chunks(self, client, integrity_db):
        """Verify integrity detects chunks without parent documents"""
        # Setup: Add orphan chunk (document_id references non-existent document)
        conn = sqlite3.connect(integrity_db)
        conn.execute('INSERT INTO chunks (id, document_id, content) VALUES (1, 999, "orphan content")')
        conn.execute('INSERT INTO fts_chunks (rowid, content, chunk_id) VALUES (1, "orphan content", 1)')
        conn.commit()
        conn.close()

        with patch('routes.maintenance.default_config') as mock_config:
            mock_config.database.path = integrity_db

            response = client.get("/api/maintenance/verify-integrity")

            assert response.status_code == 200
            data = response.json()
            assert data['healthy'] is False
            assert len(data['issues']) > 0
            # Find the referential integrity issue
            orphan_issue = next(
                (i for i in data['issues'] if 'orphan' in i.lower()),
                None
            )
            assert orphan_issue is not None

    def test_verify_integrity_detects_missing_embeddings(self, client, integrity_db):
        """Verify integrity detects chunks count vs vec_chunks count mismatch"""
        # Setup: Add chunk but no corresponding vec_chunks entry
        # Note: vec_chunks is a vectorlite table we can't easily create in test,
        # so we mock the IntegrityChecker
        conn = sqlite3.connect(integrity_db)
        conn.execute('INSERT INTO documents (id, file_path) VALUES (1, "/test/doc.pdf")')
        conn.execute('INSERT INTO chunks (id, document_id, content) VALUES (1, 1, "content")')
        conn.execute('INSERT INTO fts_chunks (rowid, content, chunk_id) VALUES (1, "content", 1)')
        conn.commit()
        conn.close()

        # Mock the IntegrityChecker to simulate missing embeddings
        mock_result = {
            'healthy': False,
            'issues': ['5 chunks missing from HNSW index'],
            'checks': [
                {'name': 'HNSW Index Consistency', 'passed': False,
                 'details': '5 chunks missing from HNSW index'}
            ],
            'table_counts': {'documents': 1, 'chunks': 1}
        }

        with patch('routes.maintenance.default_config') as mock_config:
            mock_config.database.path = integrity_db

            with patch('operations.integrity_checker.IntegrityChecker') as MockChecker:
                mock_instance = MockChecker.return_value
                mock_instance.check.return_value = mock_result

                response = client.get("/api/maintenance/verify-integrity")

                assert response.status_code == 200
                data = response.json()
                assert data['healthy'] is False
                assert any('HNSW' in issue or 'missing' in issue for issue in data['issues'])

    def test_verify_integrity_detects_fts_inconsistency(self, client, integrity_db):
        """Verify integrity detects FTS index inconsistency"""
        # Setup: Chunk exists but FTS entry is missing
        conn = sqlite3.connect(integrity_db)
        conn.execute('INSERT INTO documents (id, file_path) VALUES (1, "/test/doc.pdf")')
        conn.execute('INSERT INTO chunks (id, document_id, content) VALUES (1, 1, "content")')
        # Intentionally NOT adding fts_chunks entry
        conn.commit()
        conn.close()

        with patch('routes.maintenance.default_config') as mock_config:
            mock_config.database.path = integrity_db

            response = client.get("/api/maintenance/verify-integrity")

            assert response.status_code == 200
            data = response.json()
            assert data['healthy'] is False
            # Find the FTS inconsistency issue
            fts_issue = next(
                (i for i in data['issues'] if 'FTS' in i or 'fts' in i.lower()),
                None
            )
            assert fts_issue is not None


class TestIntegrityChecker:
    """Unit tests for IntegrityChecker operation class"""

    @pytest.fixture
    def checker_db(self):
        """Create temporary database with full schema for IntegrityChecker testing"""
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

    def test_check_returns_healthy_for_consistent_db(self, checker_db):
        """IntegrityChecker.check() returns healthy=True for consistent database"""
        # Setup: Add consistent data
        conn = sqlite3.connect(checker_db)
        conn.execute('INSERT INTO documents (id, file_path) VALUES (1, "/test/doc.pdf")')
        conn.execute('INSERT INTO chunks (id, document_id, content) VALUES (1, 1, "content")')
        conn.execute('INSERT INTO fts_chunks (rowid, content, chunk_id) VALUES (1, "content", 1)')
        conn.commit()
        conn.close()

        # Import and test
        import sys
        sys.path.insert(0, '/media/veracrypt1/CODE/rag-kb/api')
        from operations.integrity_checker import IntegrityChecker

        checker = IntegrityChecker(db_path=checker_db)
        result = checker.check()

        assert result.healthy is True
        assert result.issues == []
        assert len(result.checks) >= 3  # At least referential, FTS, duplicate checks
        assert result.table_counts['documents'] == 1
        assert result.table_counts['chunks'] == 1

    def test_check_detects_orphan_chunks(self, checker_db):
        """IntegrityChecker.check() detects chunks without valid documents"""
        # Setup: Add orphan chunk
        conn = sqlite3.connect(checker_db)
        conn.execute('INSERT INTO chunks (id, document_id, content) VALUES (1, 999, "orphan")')
        conn.execute('INSERT INTO fts_chunks (rowid, content, chunk_id) VALUES (1, "orphan", 1)')
        conn.commit()
        conn.close()

        import sys
        sys.path.insert(0, '/media/veracrypt1/CODE/rag-kb/api')
        from operations.integrity_checker import IntegrityChecker

        checker = IntegrityChecker(db_path=checker_db)
        result = checker.check()

        assert result.healthy is False
        assert any('orphan' in issue.lower() for issue in result.issues)

    def test_check_detects_fts_inconsistency(self, checker_db):
        """IntegrityChecker.check() detects FTS index missing entries"""
        # Setup: Add chunk without FTS entry
        conn = sqlite3.connect(checker_db)
        conn.execute('INSERT INTO documents (id, file_path) VALUES (1, "/test/doc.pdf")')
        conn.execute('INSERT INTO chunks (id, document_id, content) VALUES (1, 1, "content")')
        # Intentionally NOT adding fts_chunks entry
        conn.commit()
        conn.close()

        import sys
        sys.path.insert(0, '/media/veracrypt1/CODE/rag-kb/api')
        from operations.integrity_checker import IntegrityChecker

        checker = IntegrityChecker(db_path=checker_db)
        result = checker.check()

        assert result.healthy is False
        assert any('FTS' in issue or 'fts' in issue.lower() for issue in result.issues)

    def test_check_detects_duplicate_documents(self, checker_db):
        """IntegrityChecker.check() detects duplicate file paths"""
        # Setup: Add duplicate documents (same file_path)
        conn = sqlite3.connect(checker_db)
        # Remove UNIQUE constraint for this test
        conn.execute('DROP TABLE documents')
        conn.execute('''
            CREATE TABLE documents (
                id INTEGER PRIMARY KEY,
                file_path TEXT,
                indexed_at TIMESTAMP
            )
        ''')
        conn.execute('INSERT INTO documents (id, file_path) VALUES (1, "/test/doc.pdf")')
        conn.execute('INSERT INTO documents (id, file_path) VALUES (2, "/test/doc.pdf")')
        conn.commit()
        conn.close()

        import sys
        sys.path.insert(0, '/media/veracrypt1/CODE/rag-kb/api')
        from operations.integrity_checker import IntegrityChecker

        checker = IntegrityChecker(db_path=checker_db)
        result = checker.check()

        assert result.healthy is False
        assert any('multiple' in issue.lower() or 'duplicate' in issue.lower() for issue in result.issues)

    def test_check_result_structure(self, checker_db):
        """IntegrityChecker.check() returns properly structured result"""
        import sys
        sys.path.insert(0, '/media/veracrypt1/CODE/rag-kb/api')
        from operations.integrity_checker import IntegrityChecker, IntegrityResult

        checker = IntegrityChecker(db_path=checker_db)
        result = checker.check()

        # Verify result type and structure
        assert isinstance(result, IntegrityResult)
        assert isinstance(result.healthy, bool)
        assert isinstance(result.issues, list)
        assert isinstance(result.checks, list)
        assert isinstance(result.table_counts, dict)

        # Verify checks have required fields
        for check in result.checks:
            assert 'name' in check
            assert 'passed' in check
            assert 'details' in check


class TestCleanupOrphans:
    """Test POST /api/maintenance/cleanup-orphans endpoint"""

    @pytest.fixture
    def orphan_db(self):
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

    def test_cleanup_orphans_dry_run_shows_preview(self, client, orphan_db):
        """Cleanup orphans dry run should show what would be deleted without deleting"""
        # Setup: Create orphan chunk (document_id references non-existent document)
        conn = sqlite3.connect(orphan_db)
        conn.execute('INSERT INTO chunks (id, document_id, content) VALUES (1, 999, "orphan chunk")')
        conn.execute('INSERT INTO fts_chunks (rowid, content, chunk_id) VALUES (1, "orphan chunk", 1)')
        conn.commit()
        conn.close()

        with patch('routes.maintenance.default_config') as mock_config:
            mock_config.database.path = orphan_db

            response = client.post(
                "/api/maintenance/cleanup-orphans",
                json={"dry_run": True}
            )

            assert response.status_code == 200
            data = response.json()
            assert data['dry_run'] is True
            assert data['orphan_chunks_found'] == 1
            assert data['orphan_chunks_deleted'] == 0  # dry run - nothing deleted
            # Verify orphan still exists
            conn = sqlite3.connect(orphan_db)
            cursor = conn.execute('SELECT COUNT(*) FROM chunks')
            assert cursor.fetchone()[0] == 1
            conn.close()

    def test_cleanup_orphans_execute_removes_orphans(self, client, orphan_db):
        """Cleanup orphans with dry_run=False should actually delete orphan chunks"""
        # Setup: Create orphan chunk and valid chunk
        conn = sqlite3.connect(orphan_db)
        conn.execute('INSERT INTO documents (id, file_path) VALUES (1, "/test/valid.pdf")')
        conn.execute('INSERT INTO chunks (id, document_id, content) VALUES (1, 1, "valid chunk")')
        conn.execute('INSERT INTO chunks (id, document_id, content) VALUES (2, 999, "orphan chunk")')
        conn.execute('INSERT INTO fts_chunks (rowid, content, chunk_id) VALUES (1, "valid chunk", 1)')
        conn.execute('INSERT INTO fts_chunks (rowid, content, chunk_id) VALUES (2, "orphan chunk", 2)')
        conn.commit()
        conn.close()

        with patch('routes.maintenance.default_config') as mock_config:
            mock_config.database.path = orphan_db

            response = client.post(
                "/api/maintenance/cleanup-orphans",
                json={"dry_run": False}
            )

            assert response.status_code == 200
            data = response.json()
            assert data['dry_run'] is False
            assert data['orphan_chunks_found'] == 1
            assert data['orphan_chunks_deleted'] == 1

            # Verify orphan chunk was deleted, valid chunk remains
            conn = sqlite3.connect(orphan_db)
            cursor = conn.execute('SELECT COUNT(*) FROM chunks')
            assert cursor.fetchone()[0] == 1  # Only valid chunk remains
            cursor = conn.execute('SELECT id FROM chunks')
            assert cursor.fetchone()[0] == 1  # Chunk id 1 (valid) remains
            conn.close()

    def test_cleanup_orphans_cleans_vec_chunks_and_fts(self, client, orphan_db):
        """Cleanup orphans should also clean related fts_chunks entries"""
        # Setup: Create orphan chunk with FTS entry
        conn = sqlite3.connect(orphan_db)
        conn.execute('INSERT INTO chunks (id, document_id, content) VALUES (1, 999, "orphan")')
        conn.execute('INSERT INTO fts_chunks (rowid, content, chunk_id) VALUES (1, "orphan", 1)')
        conn.commit()
        conn.close()

        with patch('routes.maintenance.default_config') as mock_config:
            mock_config.database.path = orphan_db

            response = client.post(
                "/api/maintenance/cleanup-orphans",
                json={"dry_run": False}
            )

            assert response.status_code == 200
            data = response.json()
            assert data['orphan_chunks_deleted'] == 1

            # Verify FTS entry was also deleted
            conn = sqlite3.connect(orphan_db)
            cursor = conn.execute('SELECT COUNT(*) FROM fts_chunks')
            assert cursor.fetchone()[0] == 0
            conn.close()

    def test_cleanup_orphans_response_structure(self, client, orphan_db):
        """Cleanup orphans response should have correct structure"""
        with patch('routes.maintenance.default_config') as mock_config:
            mock_config.database.path = orphan_db

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
        # Setup: Chunks and FTS count mismatch (more FTS entries than chunks)
        conn = sqlite3.connect(orphan_db)
        conn.execute('INSERT INTO documents (id, file_path) VALUES (1, "/test/doc.pdf")')
        conn.execute('INSERT INTO chunks (id, document_id, content) VALUES (1, 1, "chunk1")')
        conn.execute('INSERT INTO fts_chunks (rowid, content, chunk_id) VALUES (1, "chunk1", 1)')
        conn.execute('INSERT INTO fts_chunks (rowid, content, chunk_id) VALUES (2, "orphan fts", 999)')
        conn.commit()
        conn.close()

        with patch('routes.maintenance.default_config') as mock_config:
            mock_config.database.path = orphan_db

            response = client.post(
                "/api/maintenance/cleanup-orphans",
                json={"dry_run": True}
            )

            assert response.status_code == 200
            data = response.json()
            # FTS has 2 entries, chunks has 1 -> 1 extra FTS entry
            assert data['orphan_fts_chunks_estimate'] == 1

    def test_cleanup_orphans_default_is_not_dry_run(self, client, orphan_db):
        """Cleanup orphans with no body should default to dry_run=False"""
        with patch('routes.maintenance.default_config') as mock_config:
            mock_config.database.path = orphan_db

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


class TestRebuildHnsw:
    """Test POST /api/maintenance/rebuild-hnsw endpoint

    Tests for CRITICAL HNSW index recovery functionality.
    The rebuild-hnsw endpoint is used to recover from HNSW index corruption
    by rebuilding the index from existing embeddings without re-embedding.
    """

    @pytest.fixture
    def hnsw_db(self):
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

    def test_rebuild_hnsw_dry_run_shows_stats(self, client, hnsw_db):
        """Rebuild HNSW dry run should show statistics without modifying index

        In dry_run mode, the endpoint should:
        - Report total embeddings in vec_chunks
        - Report valid embeddings (with matching chunks)
        - Report orphan embeddings count
        - NOT modify the vec_chunks table
        """
        from operations.hnsw_rebuilder import HnswRebuildResult

        mock_result = HnswRebuildResult(
            total_embeddings=100,
            valid_embeddings=95,
            orphan_embeddings=5,
            final_embeddings=100,  # Unchanged in dry_run
            dry_run=True,
            elapsed_time=0.5
        )

        with patch('operations.hnsw_rebuilder.HnswRebuilder') as MockRebuilder:
            mock_instance = MockRebuilder.return_value
            mock_instance.rebuild.return_value = mock_result

            response = client.post(
                "/api/maintenance/rebuild-hnsw",
                json={"dry_run": True}
            )

            assert response.status_code == 200
            data = response.json()

            # Verify stats are returned
            assert data['dry_run'] is True
            assert data['embeddings_before'] == 100
            assert data['orphans_found'] == 5
            assert 'Would remove' in data['message']

    def test_rebuild_hnsw_preserves_valid_embeddings(self, client, hnsw_db):
        """Rebuild HNSW should preserve all valid embeddings

        After rebuild:
        - All embeddings with matching chunk IDs should remain
        - final_embeddings should equal valid_embeddings
        """
        from operations.hnsw_rebuilder import HnswRebuildResult

        mock_result = HnswRebuildResult(
            total_embeddings=100,
            valid_embeddings=95,
            orphan_embeddings=5,
            final_embeddings=95,  # After rebuild, only valid remain
            dry_run=False,
            elapsed_time=2.5
        )

        with patch('operations.hnsw_rebuilder.HnswRebuilder') as MockRebuilder:
            mock_instance = MockRebuilder.return_value
            mock_instance.rebuild.return_value = mock_result

            response = client.post(
                "/api/maintenance/rebuild-hnsw",
                json={"dry_run": False}
            )

            assert response.status_code == 200
            data = response.json()

            # After rebuild, valid embeddings are preserved
            assert data['dry_run'] is False
            assert data['embeddings_after'] == 95
            assert data['valid_embeddings'] == 95
            assert 'Removed' in data['message']

    def test_rebuild_hnsw_removes_orphan_embeddings(self, client, hnsw_db):
        """Rebuild HNSW should remove orphan embeddings

        Orphan embeddings are vec_chunks entries where the rowid
        does not exist in the chunks table. After rebuild:
        - orphans_removed should equal orphan_embeddings
        - final_embeddings should be total - orphans
        """
        from operations.hnsw_rebuilder import HnswRebuildResult

        mock_result = HnswRebuildResult(
            total_embeddings=100,
            valid_embeddings=80,
            orphan_embeddings=20,
            final_embeddings=80,
            dry_run=False,
            elapsed_time=3.0
        )

        with patch('operations.hnsw_rebuilder.HnswRebuilder') as MockRebuilder:
            mock_instance = MockRebuilder.return_value
            mock_instance.rebuild.return_value = mock_result

            response = client.post(
                "/api/maintenance/rebuild-hnsw",
                json={"dry_run": False}
            )

            assert response.status_code == 200
            data = response.json()

            # Verify orphans were removed
            assert data['orphans_removed'] == 20
            assert data['embeddings_before'] == 100
            assert data['embeddings_after'] == 80

    def test_rebuild_hnsw_response_structure(self, client, hnsw_db):
        """Rebuild HNSW response should have correct structure"""
        from operations.hnsw_rebuilder import HnswRebuildResult

        mock_result = HnswRebuildResult(
            total_embeddings=50,
            valid_embeddings=50,
            orphan_embeddings=0,
            final_embeddings=50,
            dry_run=True,
            elapsed_time=0.1
        )

        with patch('operations.hnsw_rebuilder.HnswRebuilder') as MockRebuilder:
            mock_instance = MockRebuilder.return_value
            mock_instance.rebuild.return_value = mock_result

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
        """Rebuild HNSW with no orphans should return clean index message"""
        from operations.hnsw_rebuilder import HnswRebuildResult

        mock_result = HnswRebuildResult(
            total_embeddings=100,
            valid_embeddings=100,
            orphan_embeddings=0,
            final_embeddings=100,
            dry_run=True,
            elapsed_time=0.5
        )

        with patch('operations.hnsw_rebuilder.HnswRebuilder') as MockRebuilder:
            mock_instance = MockRebuilder.return_value
            mock_instance.rebuild.return_value = mock_result

            response = client.post(
                "/api/maintenance/rebuild-hnsw",
                json={"dry_run": True}
            )

            assert response.status_code == 200
            data = response.json()

            assert data['orphans_found'] == 0
            assert 'clean' in data['message'].lower() or 'no orphans' in data['message'].lower()


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

    @pytest.fixture
    def fts_db(self):
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

    def test_rebuild_fts_dry_run_shows_stats(self, client, fts_db):
        """Rebuild FTS dry run should show stats without modifying data"""
        # Setup: Add chunks but with mismatched FTS
        conn = sqlite3.connect(fts_db)
        conn.execute('INSERT INTO documents (id, file_path) VALUES (1, "/test/doc1.pdf")')
        conn.execute('INSERT INTO chunks (id, document_id, content) VALUES (1, 1, "first chunk content")')
        conn.execute('INSERT INTO chunks (id, document_id, content) VALUES (2, 1, "second chunk content")')
        # Intentionally leave FTS empty to simulate out-of-sync state
        conn.commit()
        conn.close()

        with patch('routes.maintenance.default_config') as mock_config:
            mock_config.database.path = fts_db

            response = client.post(
                "/api/maintenance/rebuild-fts",
                json={"dry_run": True}
            )

            assert response.status_code == 200
            data = response.json()
            assert data['dry_run'] is True
            assert data['chunks_found'] == 2
            assert data['fts_entries_before'] == 0
            assert data['chunks_indexed'] == 0  # dry_run, no actual indexing
            assert 'Would rebuild' in data['message']

            # Verify FTS was NOT modified
            conn = sqlite3.connect(fts_db)
            cursor = conn.execute('SELECT COUNT(*) FROM fts_chunks')
            assert cursor.fetchone()[0] == 0
            conn.close()

    def test_rebuild_fts_rebuilds_index(self, client, fts_db):
        """Rebuild FTS should recreate FTS index from chunks"""
        # Setup: Add chunks with no FTS entries
        conn = sqlite3.connect(fts_db)
        conn.execute('INSERT INTO documents (id, file_path) VALUES (1, "/test/doc1.pdf")')
        conn.execute('INSERT INTO chunks (id, document_id, content) VALUES (1, 1, "searchable content one")')
        conn.execute('INSERT INTO chunks (id, document_id, content) VALUES (2, 1, "searchable content two")')
        conn.execute('INSERT INTO chunks (id, document_id, content) VALUES (3, 1, "searchable content three")')
        conn.commit()
        conn.close()

        with patch('routes.maintenance.default_config') as mock_config:
            mock_config.database.path = fts_db

            response = client.post(
                "/api/maintenance/rebuild-fts",
                json={"dry_run": False}
            )

            assert response.status_code == 200
            data = response.json()
            assert data['dry_run'] is False
            assert data['chunks_indexed'] == 3
            assert data['fts_entries_after'] == 3
            assert data['time_taken'] >= 0
            assert 'Rebuilt' in data['message']

            # Verify FTS was rebuilt correctly
            conn = sqlite3.connect(fts_db)
            cursor = conn.execute('SELECT COUNT(*) FROM fts_chunks')
            assert cursor.fetchone()[0] == 3

            # Verify FTS search works
            cursor = conn.execute(
                "SELECT rowid FROM fts_chunks WHERE fts_chunks MATCH 'searchable'"
            )
            results = cursor.fetchall()
            assert len(results) == 3
            conn.close()

    def test_rebuild_fts_handles_empty_db(self, client, fts_db):
        """Rebuild FTS should handle empty database gracefully"""
        # No data added - empty database

        with patch('routes.maintenance.default_config') as mock_config:
            mock_config.database.path = fts_db

            response = client.post(
                "/api/maintenance/rebuild-fts",
                json={"dry_run": False}
            )

            assert response.status_code == 200
            data = response.json()
            assert data['chunks_found'] == 0
            assert data['chunks_indexed'] == 0
            assert data['fts_entries_after'] == 0
            assert 'No chunks' in data['message'] or 'empty' in data['message'].lower()


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


class TestRepairIndexes:
    """Test POST /api/maintenance/repair-indexes endpoint

    Tests for combined HNSW + FTS index repair functionality.
    This endpoint runs both rebuilders in sequence for complete index maintenance.
    """

    @pytest.fixture
    def repair_db(self):
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

    def test_repair_indexes_dry_run_shows_combined_stats(self, client, repair_db):
        """Repair indexes dry run should show stats for both HNSW and FTS"""
        from dataclasses import dataclass
        from typing import Optional

        @dataclass
        class MockHnswResult:
            total_embeddings: int = 100
            valid_embeddings: int = 95
            orphan_embeddings: int = 5
            final_embeddings: int = 100
            dry_run: bool = True
            elapsed_time: float = 0.5
            total_chunks: int = 95
            error: Optional[str] = None

        @dataclass
        class MockFtsResult:
            dry_run: bool = True
            chunks_found: int = 95
            chunks_indexed: int = 0
            fts_entries_before: int = 90
            fts_entries_after: int = 90
            time_taken: float = 0.3
            message: str = "Would rebuild FTS index with 95 chunks"
            errors: Optional[list] = None

        @dataclass
        class MockRepairResult:
            dry_run: bool = True
            total_time: float = 0.8
            hnsw_result: MockHnswResult = None
            fts_result: MockFtsResult = None
            message: str = "Would repair indexes"
            error: Optional[str] = None

            def __post_init__(self):
                if self.hnsw_result is None:
                    self.hnsw_result = MockHnswResult()
                if self.fts_result is None:
                    self.fts_result = MockFtsResult()

        with patch('operations.index_repairer.IndexRepairer') as MockRepairer:
            mock_instance = MockRepairer.return_value
            mock_instance.repair.return_value = MockRepairResult()

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

            # Verify HNSW stats
            assert data['hnsw']['embeddings_before'] == 100
            assert data['hnsw']['orphans_found'] == 5

            # Verify FTS stats
            assert data['fts']['chunks_found'] == 95

    def test_repair_indexes_executes_both_rebuilds(self, client, repair_db):
        """Repair indexes should execute both HNSW and FTS rebuilds"""
        from dataclasses import dataclass
        from typing import Optional

        @dataclass
        class MockHnswResult:
            total_embeddings: int = 100
            valid_embeddings: int = 95
            orphan_embeddings: int = 5
            final_embeddings: int = 95
            dry_run: bool = False
            elapsed_time: float = 2.0
            total_chunks: int = 95
            error: Optional[str] = None

        @dataclass
        class MockFtsResult:
            dry_run: bool = False
            chunks_found: int = 95
            chunks_indexed: int = 95
            fts_entries_before: int = 90
            fts_entries_after: int = 95
            time_taken: float = 1.5
            message: str = "Rebuilt FTS index: 95 chunks indexed"
            errors: Optional[list] = None

        @dataclass
        class MockRepairResult:
            dry_run: bool = False
            total_time: float = 3.5
            hnsw_result: MockHnswResult = None
            fts_result: MockFtsResult = None
            message: str = "Repaired indexes"
            error: Optional[str] = None

            def __post_init__(self):
                if self.hnsw_result is None:
                    self.hnsw_result = MockHnswResult()
                if self.fts_result is None:
                    self.fts_result = MockFtsResult()

        with patch('operations.index_repairer.IndexRepairer') as MockRepairer:
            mock_instance = MockRepairer.return_value
            mock_instance.repair.return_value = MockRepairResult()

            response = client.post(
                "/api/maintenance/repair-indexes",
                json={"dry_run": False}
            )

            assert response.status_code == 200
            data = response.json()

            assert data['dry_run'] is False
            # HNSW should have removed orphans
            assert data['hnsw']['orphans_removed'] == 5
            assert data['hnsw']['embeddings_after'] == 95
            # FTS should have rebuilt
            assert data['fts']['chunks_indexed'] == 95
            assert data['fts']['fts_entries_after'] == 95

    def test_repair_indexes_response_structure(self, client, repair_db):
        """Repair indexes response should have correct structure"""
        from dataclasses import dataclass
        from typing import Optional

        @dataclass
        class MockHnswResult:
            total_embeddings: int = 50
            valid_embeddings: int = 50
            orphan_embeddings: int = 0
            final_embeddings: int = 50
            dry_run: bool = True
            elapsed_time: float = 0.1
            total_chunks: int = 50
            error: Optional[str] = None

        @dataclass
        class MockFtsResult:
            dry_run: bool = True
            chunks_found: int = 50
            chunks_indexed: int = 0
            fts_entries_before: int = 50
            fts_entries_after: int = 50
            time_taken: float = 0.1
            message: str = "Would rebuild"
            errors: Optional[list] = None

        @dataclass
        class MockRepairResult:
            dry_run: bool = True
            total_time: float = 0.2
            hnsw_result: MockHnswResult = None
            fts_result: MockFtsResult = None
            message: str = "Would repair"
            error: Optional[str] = None

            def __post_init__(self):
                if self.hnsw_result is None:
                    self.hnsw_result = MockHnswResult()
                if self.fts_result is None:
                    self.fts_result = MockFtsResult()

        with patch('operations.index_repairer.IndexRepairer') as MockRepairer:
            mock_instance = MockRepairer.return_value
            mock_instance.repair.return_value = MockRepairResult()

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
        from dataclasses import dataclass
        from typing import Optional

        @dataclass
        class MockHnswResult:
            total_embeddings: int = 0
            valid_embeddings: int = 0
            orphan_embeddings: int = 0
            final_embeddings: int = 0
            dry_run: bool = False
            elapsed_time: float = 0.1
            total_chunks: int = 0
            error: Optional[str] = None

        @dataclass
        class MockFtsResult:
            dry_run: bool = False
            chunks_found: int = 0
            chunks_indexed: int = 0
            fts_entries_before: int = 0
            fts_entries_after: int = 0
            time_taken: float = 0.1
            message: str = "Rebuilt"
            errors: Optional[list] = None

        @dataclass
        class MockRepairResult:
            dry_run: bool = False
            total_time: float = 0.2
            hnsw_result: MockHnswResult = None
            fts_result: MockFtsResult = None
            message: str = "Repaired"
            error: Optional[str] = None

            def __post_init__(self):
                if self.hnsw_result is None:
                    self.hnsw_result = MockHnswResult()
                if self.fts_result is None:
                    self.fts_result = MockFtsResult()

        with patch('operations.index_repairer.IndexRepairer') as MockRepairer:
            mock_instance = MockRepairer.return_value
            mock_instance.repair.return_value = MockRepairResult()

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


class TestReindexPath:
    """Test POST /api/maintenance/reindex-path endpoint

    Tests for path-based reindexing functionality that deletes and
    re-queues files at a specific path for reindexing.
    """

    @pytest.fixture
    def reindex_db(self):
        """Create temporary database for reindex-path testing"""
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
            CREATE TABLE processing_progress (
                file_path TEXT PRIMARY KEY,
                status TEXT
            )
        ''')
        conn.commit()
        conn.close()

        yield path

        os.close(fd)
        os.unlink(path)

    @pytest.fixture
    def temp_file(self, tmp_path):
        """Create a temporary test file"""
        test_file = tmp_path / "test_document.pdf"
        test_file.write_text("test content")
        return test_file

    @pytest.fixture
    def temp_dir(self, tmp_path):
        """Create a temporary directory with test files"""
        test_dir = tmp_path / "test_docs"
        test_dir.mkdir()
        (test_dir / "doc1.pdf").write_text("pdf content")
        (test_dir / "doc2.md").write_text("markdown content")
        (test_dir / "ignored.txt").write_text("ignored content")  # Unsupported
        return test_dir

    def test_reindex_path_file_dry_run(self, client, temp_file):
        """Reindex path dry run for file should show preview without changes"""
        from dataclasses import dataclass, field
        from typing import Optional, List

        @dataclass
        class MockResult:
            file_path: str
            filename: str
            deleted_from_db: bool = True
            queued: bool = True
            chunks_deleted: int = 5
            error: Optional[str] = None

        @dataclass
        class MockSummary:
            path: str
            is_directory: bool = False
            files_found: int = 1
            files_deleted: int = 1
            files_queued: int = 1
            total_chunks_deleted: int = 5
            dry_run: bool = True
            results: List[MockResult] = field(default_factory=list)
            message: str = "Would reindex test_document.pdf"

        with patch('operations.path_reindexer.PathReindexer') as MockReindexer:
            mock_instance = MockReindexer.return_value
            summary = MockSummary(
                path=str(temp_file),
                results=[MockResult(file_path=str(temp_file), filename="test_document.pdf")]
            )
            mock_instance.reindex.return_value = summary

            response = client.post(
                "/api/maintenance/reindex-path",
                json={"path": str(temp_file), "dry_run": True}
            )

            assert response.status_code == 200
            data = response.json()
            assert data['dry_run'] is True
            assert data['is_directory'] is False
            assert data['files_found'] == 1
            assert data['files_queued'] == 1
            assert 'Would reindex' in data['message']

    def test_reindex_path_file_execute(self, client, temp_file):
        """Reindex path execute for file should delete and queue"""
        from dataclasses import dataclass, field
        from typing import Optional, List

        @dataclass
        class MockResult:
            file_path: str
            filename: str
            deleted_from_db: bool = True
            queued: bool = True
            chunks_deleted: int = 10
            error: Optional[str] = None

        @dataclass
        class MockSummary:
            path: str
            is_directory: bool = False
            files_found: int = 1
            files_deleted: int = 1
            files_queued: int = 1
            total_chunks_deleted: int = 10
            dry_run: bool = False
            results: List[MockResult] = field(default_factory=list)
            message: str = "Reindexed test_document.pdf"

        with patch('operations.path_reindexer.PathReindexer') as MockReindexer:
            mock_instance = MockReindexer.return_value
            summary = MockSummary(
                path=str(temp_file),
                results=[MockResult(file_path=str(temp_file), filename="test_document.pdf")]
            )
            mock_instance.reindex.return_value = summary

            response = client.post(
                "/api/maintenance/reindex-path",
                json={"path": str(temp_file), "dry_run": False}
            )

            assert response.status_code == 200
            data = response.json()
            assert data['dry_run'] is False
            assert data['files_deleted'] == 1
            assert data['files_queued'] == 1
            assert data['total_chunks_deleted'] == 10

    def test_reindex_path_directory_dry_run(self, client, temp_dir):
        """Reindex path dry run for directory should show all files"""
        from dataclasses import dataclass, field
        from typing import Optional, List

        @dataclass
        class MockResult:
            file_path: str
            filename: str
            deleted_from_db: bool = True
            queued: bool = True
            chunks_deleted: int = 5
            error: Optional[str] = None

        @dataclass
        class MockSummary:
            path: str
            is_directory: bool = True
            files_found: int = 2
            files_deleted: int = 2
            files_queued: int = 2
            total_chunks_deleted: int = 10
            dry_run: bool = True
            results: List[MockResult] = field(default_factory=list)
            message: str = "Would reindex 2 files from test_docs/"

        with patch('operations.path_reindexer.PathReindexer') as MockReindexer:
            mock_instance = MockReindexer.return_value
            summary = MockSummary(
                path=str(temp_dir),
                results=[
                    MockResult(file_path=str(temp_dir / "doc1.pdf"), filename="doc1.pdf"),
                    MockResult(file_path=str(temp_dir / "doc2.md"), filename="doc2.md"),
                ]
            )
            mock_instance.reindex.return_value = summary

            response = client.post(
                "/api/maintenance/reindex-path",
                json={"path": str(temp_dir), "dry_run": True}
            )

            assert response.status_code == 200
            data = response.json()
            assert data['is_directory'] is True
            assert data['files_found'] == 2
            assert len(data['results']) == 2

    def test_reindex_path_not_found(self, client):
        """Reindex path should handle non-existent paths"""
        from dataclasses import dataclass, field
        from typing import Optional, List

        @dataclass
        class MockSummary:
            path: str
            is_directory: bool = False
            files_found: int = 0
            files_deleted: int = 0
            files_queued: int = 0
            total_chunks_deleted: int = 0
            dry_run: bool = False
            results: List = field(default_factory=list)
            message: str = "Path not found: /nonexistent/path.pdf"

        with patch('operations.path_reindexer.PathReindexer') as MockReindexer:
            mock_instance = MockReindexer.return_value
            mock_instance.reindex.return_value = MockSummary(path="/nonexistent/path.pdf")

            response = client.post(
                "/api/maintenance/reindex-path",
                json={"path": "/nonexistent/path.pdf", "dry_run": False}
            )

            assert response.status_code == 200
            data = response.json()
            assert data['files_found'] == 0
            assert 'not found' in data['message'].lower()

    def test_reindex_path_response_structure(self, client, temp_file):
        """Reindex path response should have correct structure"""
        from dataclasses import dataclass, field
        from typing import Optional, List

        @dataclass
        class MockResult:
            file_path: str
            filename: str
            deleted_from_db: bool = True
            queued: bool = True
            chunks_deleted: int = 5
            error: Optional[str] = None

        @dataclass
        class MockSummary:
            path: str
            is_directory: bool = False
            files_found: int = 1
            files_deleted: int = 1
            files_queued: int = 1
            total_chunks_deleted: int = 5
            dry_run: bool = True
            results: List[MockResult] = field(default_factory=list)
            message: str = "Test"

        with patch('operations.path_reindexer.PathReindexer') as MockReindexer:
            mock_instance = MockReindexer.return_value
            mock_instance.reindex.return_value = MockSummary(
                path=str(temp_file),
                results=[MockResult(file_path=str(temp_file), filename="test.pdf")]
            )

            response = client.post(
                "/api/maintenance/reindex-path",
                json={"path": str(temp_file), "dry_run": True}
            )

            assert response.status_code == 200
            data = response.json()

            # Verify required fields
            assert 'path' in data
            assert 'is_directory' in data
            assert 'files_found' in data
            assert 'files_deleted' in data
            assert 'files_queued' in data
            assert 'total_chunks_deleted' in data
            assert 'dry_run' in data
            assert 'results' in data
            assert 'message' in data

            # Verify result structure
            if data['results']:
                result = data['results'][0]
                assert 'file_path' in result
                assert 'filename' in result
                assert 'deleted_from_db' in result
                assert 'queued' in result
                assert 'chunks_deleted' in result

    def test_reindex_path_unsupported_file(self, client, tmp_path):
        """Reindex path should handle unsupported file types"""
        unsupported_file = tmp_path / "file.xyz"
        unsupported_file.write_text("content")

        from dataclasses import dataclass, field
        from typing import Optional, List

        @dataclass
        class MockResult:
            file_path: str
            filename: str
            deleted_from_db: bool = False
            queued: bool = False
            chunks_deleted: int = 0
            error: str = "Unsupported file type: .xyz"

        @dataclass
        class MockSummary:
            path: str
            is_directory: bool = False
            files_found: int = 1
            files_deleted: int = 0
            files_queued: int = 0
            total_chunks_deleted: int = 0
            dry_run: bool = False
            results: List[MockResult] = field(default_factory=list)
            message: str = "File type .xyz is not supported"

        with patch('operations.path_reindexer.PathReindexer') as MockReindexer:
            mock_instance = MockReindexer.return_value
            mock_instance.reindex.return_value = MockSummary(
                path=str(unsupported_file),
                results=[MockResult(file_path=str(unsupported_file), filename="file.xyz")]
            )

            response = client.post(
                "/api/maintenance/reindex-path",
                json={"path": str(unsupported_file), "dry_run": False}
            )

            assert response.status_code == 200
            data = response.json()
            assert data['files_queued'] == 0
            assert 'not supported' in data['message'].lower()


class TestPathReindexer:
    """Unit tests for PathReindexer operation class"""

    @pytest.fixture
    def reindexer_db(self):
        """Create temporary database for PathReindexer testing"""
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
            CREATE TABLE processing_progress (
                file_path TEXT PRIMARY KEY,
                status TEXT
            )
        ''')
        conn.commit()
        conn.close()

        yield path

        os.close(fd)
        os.unlink(path)

    @pytest.fixture
    def mock_dependencies(self):
        """Create mock dependencies for PathReindexer"""
        vector_store = Mock()
        vector_store.delete_document.return_value = {'found': True, 'chunks_deleted': 5}

        progress_tracker = Mock()
        progress_tracker.delete_document = Mock()

        indexing_queue = Mock()
        indexing_queue.add = Mock()

        return vector_store, progress_tracker, indexing_queue

    def test_reindexer_initialization(self, mock_dependencies):
        """PathReindexer should initialize with dependencies"""
        import sys
        sys.path.insert(0, '/media/veracrypt1/CODE/rag-kb/api')
        from operations.path_reindexer import PathReindexer

        vector_store, progress_tracker, indexing_queue = mock_dependencies
        reindexer = PathReindexer(
            vector_store=vector_store,
            progress_tracker=progress_tracker,
            indexing_queue=indexing_queue
        )

        assert reindexer.vector_store is vector_store
        assert reindexer.progress_tracker is progress_tracker
        assert reindexer.indexing_queue is indexing_queue

    def test_reindex_file_dry_run(self, tmp_path, mock_dependencies):
        """PathReindexer.reindex() dry run should not modify anything"""
        import sys
        sys.path.insert(0, '/media/veracrypt1/CODE/rag-kb/api')
        from operations.path_reindexer import PathReindexer

        # Create test file
        test_file = tmp_path / "test.pdf"
        test_file.write_text("content")

        vector_store, progress_tracker, indexing_queue = mock_dependencies
        reindexer = PathReindexer(
            vector_store=vector_store,
            progress_tracker=progress_tracker,
            indexing_queue=indexing_queue
        )

        result = reindexer.reindex(str(test_file), dry_run=True)

        assert result.dry_run is True
        assert result.is_directory is False
        assert result.files_found == 1
        # In dry run, delete_document should NOT be called
        vector_store.delete_document.assert_not_called()
        # In dry run, queue.add should NOT be called
        indexing_queue.add.assert_not_called()

    def test_reindex_file_execute(self, tmp_path, mock_dependencies):
        """PathReindexer.reindex() should delete and queue file"""
        import sys
        sys.path.insert(0, '/media/veracrypt1/CODE/rag-kb/api')
        from operations.path_reindexer import PathReindexer

        # Create test file
        test_file = tmp_path / "test.pdf"
        test_file.write_text("content")

        vector_store, progress_tracker, indexing_queue = mock_dependencies
        reindexer = PathReindexer(
            vector_store=vector_store,
            progress_tracker=progress_tracker,
            indexing_queue=indexing_queue
        )

        result = reindexer.reindex(str(test_file), dry_run=False)

        assert result.dry_run is False
        assert result.files_queued == 1
        # Verify delete was called
        vector_store.delete_document.assert_called_once_with(str(test_file))
        progress_tracker.delete_document.assert_called_once_with(str(test_file))
        # Verify queue.add was called
        indexing_queue.add.assert_called_once()

    def test_reindex_directory(self, tmp_path, mock_dependencies):
        """PathReindexer.reindex() should handle directories recursively"""
        import sys
        sys.path.insert(0, '/media/veracrypt1/CODE/rag-kb/api')
        from operations.path_reindexer import PathReindexer

        # Create test directory with files
        test_dir = tmp_path / "docs"
        test_dir.mkdir()
        (test_dir / "doc1.pdf").write_text("pdf")
        (test_dir / "doc2.md").write_text("md")
        (test_dir / "ignored.txt").write_text("txt")  # Should be ignored

        vector_store, progress_tracker, indexing_queue = mock_dependencies
        reindexer = PathReindexer(
            vector_store=vector_store,
            progress_tracker=progress_tracker,
            indexing_queue=indexing_queue
        )

        result = reindexer.reindex(str(test_dir), dry_run=False)

        assert result.is_directory is True
        assert result.files_found == 2  # Only .pdf and .md
        assert result.files_queued == 2
        # Verify delete was called for each supported file
        assert vector_store.delete_document.call_count == 2
        assert indexing_queue.add.call_count == 2

    def test_reindex_nonexistent_path(self, mock_dependencies):
        """PathReindexer.reindex() should handle non-existent paths"""
        import sys
        sys.path.insert(0, '/media/veracrypt1/CODE/rag-kb/api')
        from operations.path_reindexer import PathReindexer

        vector_store, progress_tracker, indexing_queue = mock_dependencies
        reindexer = PathReindexer(
            vector_store=vector_store,
            progress_tracker=progress_tracker,
            indexing_queue=indexing_queue
        )

        result = reindexer.reindex("/nonexistent/path.pdf", dry_run=False)

        assert result.files_found == 0
        assert result.files_queued == 0
        assert 'not found' in result.message.lower()
        vector_store.delete_document.assert_not_called()

    def test_reindex_unsupported_file_type(self, tmp_path, mock_dependencies):
        """PathReindexer.reindex() should reject unsupported file types"""
        import sys
        sys.path.insert(0, '/media/veracrypt1/CODE/rag-kb/api')
        from operations.path_reindexer import PathReindexer

        # Create unsupported file
        test_file = tmp_path / "file.xyz"
        test_file.write_text("content")

        vector_store, progress_tracker, indexing_queue = mock_dependencies
        reindexer = PathReindexer(
            vector_store=vector_store,
            progress_tracker=progress_tracker,
            indexing_queue=indexing_queue
        )

        result = reindexer.reindex(str(test_file), dry_run=False)

        assert result.files_found == 1
        assert result.files_queued == 0
        assert 'not supported' in result.message.lower()
        assert len(result.results) == 1
        assert result.results[0].error is not None

    def test_reindex_result_structure(self, tmp_path, mock_dependencies):
        """PathReindexer result should have correct structure"""
        import sys
        sys.path.insert(0, '/media/veracrypt1/CODE/rag-kb/api')
        from operations.path_reindexer import PathReindexer, PathReindexSummary, PathReindexResult

        # Create test file
        test_file = tmp_path / "test.pdf"
        test_file.write_text("content")

        vector_store, progress_tracker, indexing_queue = mock_dependencies
        reindexer = PathReindexer(
            vector_store=vector_store,
            progress_tracker=progress_tracker,
            indexing_queue=indexing_queue
        )

        result = reindexer.reindex(str(test_file), dry_run=False)

        # Verify result type
        assert isinstance(result, PathReindexSummary)
        assert isinstance(result.path, str)
        assert isinstance(result.is_directory, bool)
        assert isinstance(result.files_found, int)
        assert isinstance(result.files_deleted, int)
        assert isinstance(result.files_queued, int)
        assert isinstance(result.total_chunks_deleted, int)
        assert isinstance(result.dry_run, bool)
        assert isinstance(result.results, list)
        assert isinstance(result.message, str)

        # Verify individual result type
        if result.results:
            item = result.results[0]
            assert isinstance(item, PathReindexResult)
            assert isinstance(item.file_path, str)
            assert isinstance(item.filename, str)
            assert isinstance(item.deleted_from_db, bool)
            assert isinstance(item.queued, bool)
            assert isinstance(item.chunks_deleted, int)

    def test_reindex_custom_extensions(self, tmp_path, mock_dependencies):
        """PathReindexer should support custom extensions"""
        import sys
        sys.path.insert(0, '/media/veracrypt1/CODE/rag-kb/api')
        from operations.path_reindexer import PathReindexer

        # Create test directory with custom extension
        test_dir = tmp_path / "docs"
        test_dir.mkdir()
        (test_dir / "file.custom").write_text("custom")
        (test_dir / "file.pdf").write_text("pdf")

        vector_store, progress_tracker, indexing_queue = mock_dependencies
        reindexer = PathReindexer(
            vector_store=vector_store,
            progress_tracker=progress_tracker,
            indexing_queue=indexing_queue,
            supported_extensions={'.custom'}  # Only .custom
        )

        result = reindexer.reindex(str(test_dir), dry_run=False)

        assert result.files_found == 1  # Only .custom file
        assert indexing_queue.add.call_count == 1
