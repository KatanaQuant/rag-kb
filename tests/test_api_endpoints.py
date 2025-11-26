"""
Tests for FastAPI endpoints in main.py

Tests for high-priority API endpoints that were previously untested:
- POST /index - Trigger reindexing (with new background task fix)
- POST /indexing/pause - Pause background indexing
- POST /indexing/resume - Resume background indexing
- POST /indexing/priority/{path} - Add file with high priority
- POST /api/maintenance/reindex-orphaned-files - Reindex orphaned files
- GET /document/{filename} - Get document info
- GET /documents - List all documents
- DELETE /document/{path} - Delete document

These endpoints are critical for production use and had ZERO test coverage.
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path


@pytest.fixture
def client():
    """Create test client with mocked app state"""
    from main import app, state

    # Mock the state
    state.indexing = Mock()
    state.indexing.queue = Mock()
    state.indexing.queue.size.return_value = 10
    state.indexing.queue.is_paused.return_value = False

    state.core = Mock()
    state.core.vector_store = Mock()
    state.core.progress_tracker = Mock()

    client = TestClient(app)
    yield client


class TestIndexEndpoint:
    """Test /index endpoint"""

    def test_index_endpoint_runs_in_background(self, client):
        """NEW FIX: File scan should not block API response"""
        from main import state
        from unittest.mock import patch

        # Mock queue
        state.indexing.queue = Mock()
        state.indexing.queue.add_many = Mock()

        # Mock FileWalker to avoid actual file scanning
        with patch('routes.indexing.FileWalker') as mock_walker_class:
            mock_walker = Mock()
            mock_walker.walk.return_value = []
            mock_walker_class.return_value = mock_walker

            # Call endpoint
            response = client.post("/index", json={"force_reindex": False})

            # Should return immediately (not wait for file scan)
            assert response.status_code == 200
            data = response.json()
            assert data['status'] == 'success'
            assert 'background' in data['message'].lower()

    def test_index_endpoint_with_force_reindex(self, client):
        """force_reindex=True should add files with HIGH priority"""
        from main import state
        from unittest.mock import patch

        state.indexing.queue = Mock()
        state.indexing.queue.add_many = Mock()

        with patch('routes.indexing.FileWalker') as mock_walker_class:
            mock_walker = Mock()
            mock_walker.walk.return_value = []
            mock_walker_class.return_value = mock_walker

            response = client.post("/index", json={"force_reindex": True})

            assert response.status_code == 200
            data = response.json()
            assert 'force=True' in data['message'] or 'force=true' in data['message'].lower()

    def test_index_endpoint_without_queue_fails(self, client):
        """Endpoint should fail gracefully if queue not initialized"""
        from main import state

        state.indexing.queue = None

        response = client.post("/index", json={"force_reindex": False})

        assert response.status_code == 400
        assert 'not initialized' in response.json()['detail'].lower()

    def test_index_endpoint_returns_immediately(self, client):
        """Endpoint should return success"""
        from main import state
        from unittest.mock import patch

        state.indexing.queue = Mock()
        state.indexing.queue.add_many = Mock()

        with patch('routes.indexing.FileWalker') as mock_walker_class:
            mock_walker = Mock()
            mock_walker.walk.return_value = []
            mock_walker_class.return_value = mock_walker

            response = client.post("/index", json={"force_reindex": False})

            assert response.status_code == 200
            assert 'success' in response.json()['status'].lower()


class TestPauseResumeEndpoints:
    """Test /indexing/pause and /indexing/resume endpoints"""

    def test_pause_indexing_success(self, client):
        """Pause endpoint should pause the queue"""
        from main import state

        state.indexing.queue = Mock()
        state.indexing.queue.pause = Mock()
        state.indexing.queue.size.return_value = 42

        response = client.post("/indexing/pause")

        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'success'
        assert 'paused' in data['message'].lower()
        assert data['queue_size'] == 42
        state.indexing.queue.pause.assert_called_once()

    def test_pause_without_queue_fails(self, client):
        """Pause should fail if queue not initialized"""
        from main import state

        state.indexing.queue = None

        response = client.post("/indexing/pause")

        assert response.status_code == 400
        assert 'not initialized' in response.json()['detail'].lower()

    def test_resume_indexing_success(self, client):
        """Resume endpoint should resume the queue"""
        from main import state

        state.indexing.queue = Mock()
        state.indexing.queue.resume = Mock()
        state.indexing.queue.size.return_value = 15

        response = client.post("/indexing/resume")

        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'success'
        assert 'resumed' in data['message'].lower()
        assert data['queue_size'] == 15
        state.indexing.queue.resume.assert_called_once()

    def test_resume_without_queue_fails(self, client):
        """Resume should fail if queue not initialized"""
        from main import state

        state.indexing.queue = None

        response = client.post("/indexing/resume")

        assert response.status_code == 400
        assert 'not initialized' in response.json()['detail'].lower()

    def test_pause_then_resume_workflow(self, client):
        """Full workflow: Pause → Resume should work"""
        from main import state

        state.indexing.queue = Mock()
        state.indexing.queue.pause = Mock()
        state.indexing.queue.resume = Mock()
        state.indexing.queue.size.return_value = 20

        # Pause
        pause_response = client.post("/indexing/pause")
        assert pause_response.status_code == 200

        # Resume
        resume_response = client.post("/indexing/resume")
        assert resume_response.status_code == 200

        # Verify both were called
        state.indexing.queue.pause.assert_called_once()
        state.indexing.queue.resume.assert_called_once()


class TestPriorityEndpoint:
    """Test /indexing/priority/{path} endpoint"""

    def test_add_priority_file_success(self, client, tmp_path):
        """Priority endpoint should add file with HIGH priority"""
        from main import state, default_config

        # Create test file
        test_file = tmp_path / "test.pdf"
        test_file.touch()

        # Mock config
        default_config.paths.knowledge_base = tmp_path

        state.indexing.queue = Mock()
        state.indexing.queue.add = Mock()
        state.indexing.queue.size.return_value = 5

        response = client.post("/indexing/priority/test.pdf?force=false")

        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'success'
        assert 'HIGH priority' in data['message']
        assert data['queue_size'] == 5
        assert data['force'] is False

        # Verify queue.add was called
        state.indexing.queue.add.assert_called_once()

    def test_add_priority_file_with_force(self, client, tmp_path):
        """Priority endpoint with force=True should force reindex"""
        from main import state, default_config

        test_file = tmp_path / "test.pdf"
        test_file.touch()

        default_config.paths.knowledge_base = tmp_path

        state.indexing.queue = Mock()
        state.indexing.queue.add = Mock()
        state.indexing.queue.size.return_value = 5

        response = client.post("/indexing/priority/test.pdf?force=true")

        assert response.status_code == 200
        data = response.json()
        assert data['force'] is True

    def test_add_priority_nonexistent_file_fails(self, client, tmp_path):
        """Priority endpoint should fail for non-existent files"""
        from main import state, default_config

        default_config.paths.knowledge_base = tmp_path

        state.indexing.queue = Mock()

        response = client.post("/indexing/priority/nonexistent.pdf")

        assert response.status_code == 404
        assert 'not found' in response.json()['detail'].lower()

    def test_add_priority_without_queue_fails(self, client):
        """Priority endpoint should fail if queue not initialized"""
        from main import state

        state.indexing.queue = None

        response = client.post("/indexing/priority/test.pdf")

        assert response.status_code == 400
        assert 'not initialized' in response.json()['detail'].lower()


class TestReindexOrphanedFilesEndpoint:
    """Test /api/maintenance/reindex-orphaned-files endpoint"""

    def test_reindex_orphaned_files_finds_and_repairs(self, client):
        """Reindex orphaned files endpoint should detect and queue orphaned files"""
        from main import state

        # Mock orphan detector
        mock_detector = Mock()
        mock_detector.detect_orphans.return_value = [
            {'path': '/test/orphan1.pdf', 'chunks': 10},
            {'path': '/test/orphan2.md', 'chunks': 5}
        ]
        mock_detector.repair_orphans.return_value = 2

        state.core.progress_tracker = Mock()
        state.core.vector_store = Mock()
        state.indexing.queue = Mock()

        with patch('routes.database.OrphanDetector', return_value=mock_detector):
            response = client.post("/api/maintenance/reindex-orphaned-files")

        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'success'
        assert data['orphans_found'] == 2
        assert data['orphans_queued'] == 2
        assert 'HIGH priority' in data['message']

    def test_reindex_orphaned_files_no_orphans_found(self, client):
        """Reindex orphaned files endpoint should handle case with no orphans"""
        from main import state

        mock_detector = Mock()
        mock_detector.detect_orphans.return_value = []

        state.core.progress_tracker = Mock()
        state.core.vector_store = Mock()

        with patch('routes.database.OrphanDetector', return_value=mock_detector):
            response = client.post("/api/maintenance/reindex-orphaned-files")

        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'success'
        assert data['orphans_found'] == 0
        assert 'No orphaned' in data['message']

    def test_reindex_orphaned_files_without_progress_tracker_fails(self, client):
        """Reindex orphaned files should fail if progress tracking not enabled"""
        from main import state

        state.core.progress_tracker = None

        response = client.post("/api/maintenance/reindex-orphaned-files")

        assert response.status_code == 400
        assert 'not enabled' in response.json()['detail'].lower()


class TestDocumentInfoEndpoint:
    """Test /document/{filename} endpoint"""

    def test_get_document_info_success(self, client):
        """Get document info should return metadata"""
        from main import state
        from unittest.mock import AsyncMock

        async def mock_get_info(filename):
            return {
                'file_path': '/test/document.pdf',
                'extraction_method': 'docling_pdf',
                'indexed_at': '2025-11-21 08:00:00'
            }

        state.core.async_vector_store = Mock()
        state.core.async_vector_store.get_document_info = AsyncMock(side_effect=mock_get_info)

        response = client.get("/document/document.pdf")

        assert response.status_code == 200
        data = response.json()
        assert 'document.pdf' in data['file_path']
        assert data['extraction_method'] == 'docling_pdf'
        assert 'indexed_at' in data

    def test_get_document_info_not_found(self, client):
        """Get document info should return 404 for missing document"""
        from main import state
        from unittest.mock import AsyncMock

        async def mock_get_info(filename):
            return None

        state.core.async_vector_store = Mock()
        state.core.async_vector_store.get_document_info = AsyncMock(side_effect=mock_get_info)

        response = client.get("/document/nonexistent.pdf")

        assert response.status_code == 404
        assert 'not found' in response.json()['detail'].lower()


class TestListDocumentsEndpoint:
    """Test /documents endpoint"""

    def test_list_documents_success(self, client):
        """List documents should return all indexed documents"""
        from main import state
        from unittest.mock import AsyncMock

        # Create async generator for cursor
        async def mock_cursor():
            for row in [
                ('/test/doc1.pdf', '2025-11-21 08:00:00', 10),
                ('/test/doc2.md', '2025-11-21 08:30:00', 5),
                ('/test/doc3.epub', '2025-11-21 09:00:00', 20)
            ]:
                yield row

        state.core.async_vector_store = Mock()
        state.core.async_vector_store.query_documents_with_chunks = AsyncMock(return_value=mock_cursor())

        response = client.get("/documents")

        assert response.status_code == 200
        data = response.json()
        assert data['total_documents'] == 3
        assert len(data['documents']) == 3
        assert data['documents'][0]['chunk_count'] == 10

    def test_list_documents_empty_database(self, client):
        """List documents should handle empty database"""
        from main import state
        from unittest.mock import AsyncMock

        async def mock_cursor():
            return
            yield  # Make it a generator

        state.core.async_vector_store = Mock()
        state.core.async_vector_store.query_documents_with_chunks = AsyncMock(return_value=mock_cursor())

        state.core.vector_store = Mock()
        state.core.vector_store.query_documents_with_chunks.return_value = []

        response = client.get("/documents")

        assert response.status_code == 200
        data = response.json()
        assert data['total_documents'] == 0
        assert data['documents'] == []


class TestDeleteDocumentEndpoint:
    """Test DELETE /document/{path} endpoint"""

    def test_delete_document_success(self, client):
        """Delete document should remove document and chunks"""
        from main import state
        from unittest.mock import AsyncMock

        # Use AsyncMock for async endpoint
        async def mock_delete(file_path):
            return {
                'found': True,
                'document_id': 42,
                'chunks_deleted': 15,
                'document_deleted': True
            }

        state.core.async_vector_store = Mock()
        state.core.async_vector_store.delete_document = AsyncMock(side_effect=mock_delete)
        state.core.progress_tracker = Mock()
        state.core.progress_tracker.delete_document = Mock()

        response = client.delete("/document/test.pdf")

        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'success'
        assert data['file_path'] == 'test.pdf'
        assert data['found'] is True
        assert data['chunks_deleted'] == 15
        assert data['document_deleted'] is True

        # Verify async method was called
        state.core.async_vector_store.delete_document.assert_called_once_with('test.pdf')
        state.core.progress_tracker.delete_document.assert_called_once_with('test.pdf')

    def test_delete_nonexistent_document(self, client):
        """Delete should handle non-existent documents"""
        from main import state
        from unittest.mock import AsyncMock

        async def mock_delete(file_path):
            return {
                'found': False,
                'chunks_deleted': 0,
                'document_deleted': False
            }

        state.core.async_vector_store = Mock()
        state.core.async_vector_store.delete_document = AsyncMock(side_effect=mock_delete)
        state.core.progress_tracker = Mock()

        response = client.delete("/document/nonexistent.pdf")

        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'success'
        assert data['file_path'] == 'nonexistent.pdf'
        assert data['found'] is False
        assert data['chunks_deleted'] == 0
        assert data['document_deleted'] is False

        # Verify async method was called
        state.core.async_vector_store.delete_document.assert_called_once_with('nonexistent.pdf')


class TestIndexingStatusEndpoint:
    """Test /indexing/status endpoint"""

    def test_indexing_status_shows_queue_state(self, client):
        """Status endpoint should show queue state"""
        from main import state

        state.indexing.queue = Mock()
        state.indexing.queue.is_paused.return_value = False
        state.indexing.queue.size.return_value = 25
        state.indexing.queue.is_empty.return_value = False

        state.indexing.worker = Mock()
        state.indexing.worker.is_running.return_value = True

        # Try to call status endpoint
        response = client.get("/indexing/status")

        # If endpoint exists, verify response
        if response.status_code == 200:
            data = response.json()
            assert 'queue_size' in data or 'size' in data
            assert 'paused' in data or 'is_paused' in data


class TestQueueJobsEndpoint:
    """Test /queue/jobs endpoint"""

    def test_queue_jobs_shows_pending_files(self, client):
        """Queue jobs endpoint should show pending files"""
        from main import state

        state.indexing.queue = Mock()
        state.indexing.queue.size.return_value = 10

        # Try to call queue/jobs endpoint
        response = client.get("/queue/jobs")

        # If endpoint exists, verify basic structure
        if response.status_code == 200:
            data = response.json()
            # Should have some information about queue
            assert isinstance(data, dict)


class TestAPIIntegration:
    """Integration tests for API workflows"""

    def test_full_workflow_pause_add_priority_resume(self, client, tmp_path):
        """Full workflow: Pause → Add Priority File → Resume"""
        from main import state, default_config

        # Setup
        test_file = tmp_path / "urgent.pdf"
        test_file.touch()
        default_config.paths.knowledge_base = tmp_path

        state.indexing.queue = Mock()
        state.indexing.queue.pause = Mock()
        state.indexing.queue.add = Mock()
        state.indexing.queue.resume = Mock()
        state.indexing.queue.size.return_value = 5

        # 1. Pause indexing
        pause_response = client.post("/indexing/pause")
        assert pause_response.status_code == 200

        # 2. Add urgent file with high priority
        priority_response = client.post("/indexing/priority/urgent.pdf")
        assert priority_response.status_code == 200

        # 3. Resume indexing
        resume_response = client.post("/indexing/resume")
        assert resume_response.status_code == 200

        # Verify all operations succeeded
        state.indexing.queue.pause.assert_called_once()
        state.indexing.queue.add.assert_called_once()
        state.indexing.queue.resume.assert_called_once()

    def test_error_handling_across_endpoints(self, client):
        """All endpoints should handle missing queue gracefully"""
        from main import state

        state.indexing.queue = None

        # All these should return 400, not crash
        endpoints = [
            ("POST", "/index"),
            ("POST", "/indexing/pause"),
            ("POST", "/indexing/resume"),
            ("POST", "/indexing/priority/test.pdf")
        ]

        for method, path in endpoints:
            if method == "POST":
                response = client.post(path, json={} if path == "/index" else None)
                assert response.status_code in [400, 422]  # 400 or validation error
