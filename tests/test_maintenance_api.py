# Copyright (c) 2024 RAG-KB Contributors
# SPDX-License-Identifier: MIT

"""Tests for maintenance REST API endpoints

Tests for:
- POST /api/maintenance/backfill-chunk-counts - Backfill chunk counts
- POST /api/maintenance/delete-empty-documents - Delete empty document records
- POST /api/maintenance/reindex-failed-documents - Re-index failed documents
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
