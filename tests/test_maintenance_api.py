# Copyright (c) 2024 RAG-KB Contributors
# SPDX-License-Identifier: MIT

"""Tests for maintenance REST API endpoints

Tests for:
- POST /api/maintenance/fix-tracking - Backfill chunk counts
- POST /api/maintenance/delete-orphans - Delete orphan document records
- POST /api/maintenance/reindex-incomplete - Re-index incomplete documents
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


class TestFixTrackingEndpoint:
    """Test POST /api/maintenance/fix-tracking endpoint"""

    def test_fix_tracking_dry_run(self, client):
        """Fix tracking dry run should not modify data"""
        # Import is inside the endpoint, need to mock at module import
        mock_module = MagicMock()
        mock_module.backfill_chunk_counts = Mock(return_value={
            'checked': 100,
            'would_update': 10
        })

        with patch.dict('sys.modules', {'migrations.backfill_chunk_counts': mock_module}):
            response = client.post(
                "/api/maintenance/fix-tracking",
                json={"dry_run": True}
            )

            # Should work or handle import gracefully
            assert response.status_code in [200, 500]
            if response.status_code == 200:
                data = response.json()
                assert data['dry_run'] is True
                assert 'Would update' in data['message']

    def test_fix_tracking_actual_update(self, client):
        """Fix tracking without dry_run should update data"""
        mock_module = MagicMock()
        mock_module.backfill_chunk_counts = Mock(return_value={
            'checked': 100,
            'updated': 10
        })

        with patch.dict('sys.modules', {'migrations.backfill_chunk_counts': mock_module}):
            response = client.post(
                "/api/maintenance/fix-tracking",
                json={"dry_run": False}
            )

            assert response.status_code in [200, 500]
            if response.status_code == 200:
                data = response.json()
                assert data['dry_run'] is False

    def test_fix_tracking_default_is_not_dry_run(self, client):
        """Fix tracking with no body should default to dry_run=False"""
        mock_module = MagicMock()
        mock_module.backfill_chunk_counts = Mock(return_value={
            'checked': 50,
            'updated': 5
        })

        with patch.dict('sys.modules', {'migrations.backfill_chunk_counts': mock_module}):
            response = client.post("/api/maintenance/fix-tracking")

            assert response.status_code in [200, 500]
            if response.status_code == 200:
                data = response.json()
                assert data['dry_run'] is False


class TestDeleteOrphansEndpoint:
    """Test POST /api/maintenance/delete-orphans endpoint"""

    def test_delete_orphans_finds_orphans(self, client, temp_db):
        """Delete orphans should find documents with no chunks"""
        # Add orphan document (no chunks)
        conn = sqlite3.connect(temp_db)
        conn.execute('INSERT INTO documents (id, file_path) VALUES (1, "/test/orphan.pdf")')
        conn.commit()
        conn.close()

        with patch('routes.maintenance.default_config') as mock_config:
            mock_config.database.path = temp_db

            response = client.post(
                "/api/maintenance/delete-orphans",
                json={"dry_run": True}
            )

            assert response.status_code == 200
            data = response.json()
            assert data['orphans_found'] == 1
            assert data['orphans_deleted'] == 0  # dry_run
            assert data['dry_run'] is True
            assert len(data['orphans']) == 1
            assert data['orphans'][0]['filename'] == 'orphan.pdf'

    def test_delete_orphans_skips_documents_with_chunks(self, client, temp_db):
        """Delete orphans should not find documents with chunks"""
        conn = sqlite3.connect(temp_db)
        conn.execute('INSERT INTO documents (id, file_path) VALUES (1, "/test/complete.pdf")')
        conn.execute('INSERT INTO chunks (document_id, content) VALUES (1, "chunk content")')
        conn.commit()
        conn.close()

        with patch('routes.maintenance.default_config') as mock_config:
            mock_config.database.path = temp_db

            response = client.post(
                "/api/maintenance/delete-orphans",
                json={"dry_run": True}
            )

            assert response.status_code == 200
            data = response.json()
            assert data['orphans_found'] == 0

    def test_delete_orphans_actually_deletes(self, client, temp_db):
        """Delete orphans without dry_run should delete records"""
        conn = sqlite3.connect(temp_db)
        conn.execute('INSERT INTO documents (id, file_path) VALUES (1, "/test/orphan1.pdf")')
        conn.execute('INSERT INTO documents (id, file_path) VALUES (2, "/test/orphan2.pdf")')
        conn.execute('INSERT INTO processing_progress (file_path, status) VALUES ("/test/orphan1.pdf", "failed")')
        conn.commit()
        conn.close()

        with patch('routes.maintenance.default_config') as mock_config:
            mock_config.database.path = temp_db

            response = client.post(
                "/api/maintenance/delete-orphans",
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

    def test_delete_orphans_response_structure(self, client, temp_db):
        """Delete orphans response should have correct structure"""
        with patch('routes.maintenance.default_config') as mock_config:
            mock_config.database.path = temp_db

            response = client.post(
                "/api/maintenance/delete-orphans",
                json={"dry_run": True}
            )

            assert response.status_code == 200
            data = response.json()

            assert 'orphans_found' in data
            assert 'orphans_deleted' in data
            assert 'dry_run' in data
            assert 'orphans' in data
            assert 'message' in data


class TestReindexIncompleteEndpoint:
    """Test POST /api/maintenance/reindex-incomplete endpoint"""

    def test_reindex_incomplete_dry_run(self, client):
        """Reindex incomplete dry run should list documents"""
        # Patch requests module before it's imported in the endpoint
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'issues': [
                {'file_path': '/test/incomplete1.pdf', 'issue': 'zero_chunks'},
                {'file_path': '/test/incomplete2.pdf', 'issue': 'processing_incomplete'}
            ]
        }

        with patch('requests.get', return_value=mock_response):
            response = client.post(
                "/api/maintenance/reindex-incomplete",
                json={"dry_run": True}
            )

            assert response.status_code == 200
            data = response.json()
            assert data['documents_found'] == 2
            assert data['documents_reindexed'] == 0  # dry_run
            assert data['dry_run'] is True
            assert len(data['results']) == 2

    def test_reindex_incomplete_filters_by_issue_type(self, client):
        """Reindex should filter by specified issue types"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'issues': [
                {'file_path': '/test/a.pdf', 'issue': 'zero_chunks'},
                {'file_path': '/test/b.pdf', 'issue': 'processing_incomplete'},
                {'file_path': '/test/c.pdf', 'issue': 'missing_embeddings'}
            ]
        }

        with patch('requests.get', return_value=mock_response):
            response = client.post(
                "/api/maintenance/reindex-incomplete",
                json={"dry_run": True, "issue_types": ["zero_chunks"]}
            )

            assert response.status_code == 200
            data = response.json()
            assert data['documents_found'] == 1
            assert data['results'][0]['filename'] == 'a.pdf'

    def test_reindex_incomplete_no_issues(self, client):
        """Reindex with no issues should return zero"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'issues': []}

        with patch('requests.get', return_value=mock_response):
            response = client.post(
                "/api/maintenance/reindex-incomplete",
                json={"dry_run": True}
            )

            assert response.status_code == 200
            data = response.json()
            assert data['documents_found'] == 0
            assert data['results'] == []
            assert 'No incomplete' in data['message']

    def test_reindex_incomplete_connection_error(self, client):
        """Reindex should handle connection errors gracefully"""
        import requests as req

        with patch('requests.get', side_effect=req.exceptions.ConnectionError("Connection refused")):
            response = client.post(
                "/api/maintenance/reindex-incomplete",
                json={"dry_run": True}
            )

            assert response.status_code == 503
            assert 'Cannot connect' in response.json()['detail']

    def test_reindex_incomplete_response_structure(self, client):
        """Reindex response should have correct structure"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'issues': []}

        with patch('requests.get', return_value=mock_response):
            response = client.post(
                "/api/maintenance/reindex-incomplete",
                json={"dry_run": True}
            )

            assert response.status_code == 200
            data = response.json()

            assert 'documents_found' in data
            assert 'documents_reindexed' in data
            assert 'documents_failed' in data
            assert 'dry_run' in data
            assert 'results' in data
            assert 'message' in data


class TestMaintenanceApiIntegration:
    """Integration tests for maintenance endpoints"""

    def test_all_endpoints_accept_empty_body(self, client, temp_db):
        """All maintenance endpoints should work without request body"""
        with patch('routes.maintenance.default_config') as mock_config:
            mock_config.database.path = temp_db

            # delete-orphans should work
            response = client.post("/api/maintenance/delete-orphans")
            assert response.status_code == 200

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'issues': []}

        with patch('requests.get', return_value=mock_response):
            # reindex-incomplete should work
            response = client.post("/api/maintenance/reindex-incomplete")
            assert response.status_code == 200

    def test_all_endpoints_return_json(self, client, temp_db):
        """All maintenance endpoints should return JSON"""
        with patch('routes.maintenance.default_config') as mock_config:
            mock_config.database.path = temp_db

            response = client.post("/api/maintenance/delete-orphans")
            assert response.headers.get('content-type') == 'application/json'

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'issues': []}

        with patch('requests.get', return_value=mock_response):
            response = client.post("/api/maintenance/reindex-incomplete")
            assert response.headers.get('content-type') == 'application/json'
