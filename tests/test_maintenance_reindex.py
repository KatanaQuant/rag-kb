# Copyright (c) 2024 RAG-KB Contributors
# SPDX-License-Identifier: MIT

"""Tests for maintenance path-based reindexing endpoints

Tests for:
- POST /api/maintenance/reindex-path - Path-based reindexing
- PathReindexer operation class unit tests
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, MagicMock, patch
from dataclasses import dataclass, field
from typing import Optional, List
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
def reindex_db():
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
def temp_file(tmp_path):
    """Create a temporary test file"""
    test_file = tmp_path / "test_document.pdf"
    test_file.write_text("test content")
    return test_file


@pytest.fixture
def temp_dir(tmp_path):
    """Create a temporary directory with test files"""
    test_dir = tmp_path / "test_docs"
    test_dir.mkdir()
    (test_dir / "doc1.pdf").write_text("pdf content")
    (test_dir / "doc2.md").write_text("markdown content")
    (test_dir / "ignored.txt").write_text("ignored content")  # Unsupported
    return test_dir


# Mock dataclasses for PathReindexer results
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
    message: str = "Test message"


class TestReindexPath:
    """Test POST /api/maintenance/reindex-path endpoint

    Tests for path-based reindexing functionality that deletes and
    re-queues files at a specific path for reindexing.
    """

    def test_reindex_path_file_dry_run(self, client, temp_file):
        """Reindex path dry run for file should show preview without changes"""
        with patch('operations.path_reindexer.PathReindexer') as MockReindexer:
            mock_instance = MockReindexer.return_value
            summary = MockSummary(
                path=str(temp_file),
                message="Would reindex test_document.pdf",
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
        with patch('operations.path_reindexer.PathReindexer') as MockReindexer:
            mock_instance = MockReindexer.return_value
            summary = MockSummary(
                path=str(temp_file),
                dry_run=False,
                total_chunks_deleted=10,
                message="Reindexed test_document.pdf",
                results=[MockResult(file_path=str(temp_file), filename="test_document.pdf", chunks_deleted=10)]
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
        with patch('operations.path_reindexer.PathReindexer') as MockReindexer:
            mock_instance = MockReindexer.return_value
            summary = MockSummary(
                path=str(temp_dir),
                is_directory=True,
                files_found=2,
                files_deleted=2,
                files_queued=2,
                total_chunks_deleted=10,
                message="Would reindex 2 files from test_docs/",
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
        with patch('operations.path_reindexer.PathReindexer') as MockReindexer:
            mock_instance = MockReindexer.return_value
            mock_instance.reindex.return_value = MockSummary(
                path="/nonexistent/path.pdf",
                files_found=0,
                files_deleted=0,
                files_queued=0,
                total_chunks_deleted=0,
                dry_run=False,
                results=[],
                message="Path not found: /nonexistent/path.pdf"
            )

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

        with patch('operations.path_reindexer.PathReindexer') as MockReindexer:
            mock_instance = MockReindexer.return_value
            mock_instance.reindex.return_value = MockSummary(
                path=str(unsupported_file),
                files_found=1,
                files_deleted=0,
                files_queued=0,
                total_chunks_deleted=0,
                dry_run=False,
                message="File type .xyz is not supported",
                results=[MockResult(
                    file_path=str(unsupported_file),
                    filename="file.xyz",
                    deleted_from_db=False,
                    queued=False,
                    chunks_deleted=0,
                    error="Unsupported file type: .xyz"
                )]
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
