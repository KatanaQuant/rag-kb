# Copyright (c) 2024 RAG-KB Contributors
# SPDX-License-Identifier: MIT

"""Tests for rebuild-embeddings and partial-rebuild endpoints

Tests for:
- POST /api/maintenance/rebuild-embeddings - Full re-embed of all documents
- POST /api/maintenance/partial-rebuild - Re-embed chunks by ID range
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch
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


class TestRebuildEmbeddingsEndpoint:
    """Test POST /api/maintenance/rebuild-embeddings endpoint"""

    def test_rebuild_embeddings_dry_run_shows_stats(self, client, temp_db):
        """Rebuild embeddings dry run should show statistics without modifying"""
        from dataclasses import dataclass
        from typing import Optional, List

        @dataclass
        class MockResult:
            dry_run: bool = True
            documents_found: int = 50
            chunks_found: int = 500
            chunks_embedded: int = 0
            embeddings_before: int = 450
            embeddings_after: int = 450
            time_taken: float = 0.5
            message: str = "Would rebuild 500 embeddings from 50 documents"
            errors: List[str] = None
            model_name: str = "Snowflake/snowflake-arctic-embed-l-v2.0"
            embedding_dim: Optional[int] = None

            def __post_init__(self):
                if self.errors is None:
                    self.errors = []

        with patch('operations.embedding_rebuilder.EmbeddingRebuilder') as MockRebuilder:
            mock_instance = MockRebuilder.return_value
            mock_instance.rebuild.return_value = MockResult()

            response = client.post(
                "/api/maintenance/rebuild-embeddings",
                json={"dry_run": True}
            )

            assert response.status_code == 200
            data = response.json()

            assert data['dry_run'] is True
            assert data['documents_found'] == 50
            assert data['chunks_found'] == 500
            assert data['chunks_embedded'] == 0
            assert 'Would rebuild' in data['message']

    def test_rebuild_embeddings_response_structure(self, client, temp_db):
        """Rebuild embeddings response should have correct structure"""
        from dataclasses import dataclass
        from typing import List, Optional

        @dataclass
        class MockResult:
            dry_run: bool = True
            documents_found: int = 10
            chunks_found: int = 100
            chunks_embedded: int = 0
            embeddings_before: int = 100
            embeddings_after: int = 100
            time_taken: float = 0.1
            message: str = "Would rebuild"
            errors: List[str] = None
            model_name: str = "test-model"
            embedding_dim: Optional[int] = None

            def __post_init__(self):
                if self.errors is None:
                    self.errors = []

        with patch('operations.embedding_rebuilder.EmbeddingRebuilder') as MockRebuilder:
            mock_instance = MockRebuilder.return_value
            mock_instance.rebuild.return_value = MockResult()

            response = client.post(
                "/api/maintenance/rebuild-embeddings",
                json={"dry_run": True}
            )

            assert response.status_code == 200
            data = response.json()

            # Verify required fields
            assert 'dry_run' in data
            assert 'documents_found' in data
            assert 'chunks_found' in data
            assert 'chunks_embedded' in data
            assert 'embeddings_before' in data
            assert 'embeddings_after' in data
            assert 'time_taken' in data
            assert 'message' in data
            assert 'model_name' in data


class TestPartialRebuildEndpoint:
    """Test POST /api/maintenance/partial-rebuild endpoint"""

    def test_partial_rebuild_dry_run_shows_range_stats(self, client, temp_db):
        """Partial rebuild dry run should show stats for specified range"""
        from dataclasses import dataclass
        from typing import List, Optional

        @dataclass
        class MockResult:
            dry_run: bool = True
            start_id: int = 70778
            end_id: int = 71727
            chunks_in_range: int = 950
            chunks_embedded: int = 0
            time_taken: float = 0.3
            message: str = "Would embed 950 chunks in range [70778-71727]"
            errors: List[str] = None
            model_name: str = "Snowflake/snowflake-arctic-embed-l-v2.0"

            def __post_init__(self):
                if self.errors is None:
                    self.errors = []

        with patch('operations.partial_rebuilder.PartialRebuilder') as MockRebuilder:
            mock_instance = MockRebuilder.return_value
            mock_instance.rebuild.return_value = MockResult()

            response = client.post(
                "/api/maintenance/partial-rebuild",
                json={"dry_run": True, "start_id": 70778, "end_id": 71727}
            )

            assert response.status_code == 200
            data = response.json()

            assert data['dry_run'] is True
            assert data['start_id'] == 70778
            assert data['end_id'] == 71727
            assert data['chunks_in_range'] == 950
            assert data['chunks_embedded'] == 0
            assert 'Would embed' in data['message']

    def test_partial_rebuild_response_structure(self, client, temp_db):
        """Partial rebuild response should have correct structure"""
        from dataclasses import dataclass
        from typing import List, Optional

        @dataclass
        class MockResult:
            dry_run: bool = True
            start_id: Optional[int] = 100
            end_id: Optional[int] = 200
            chunks_in_range: int = 50
            chunks_embedded: int = 0
            time_taken: float = 0.1
            message: str = "Would embed"
            errors: List[str] = None
            model_name: str = "test-model"

            def __post_init__(self):
                if self.errors is None:
                    self.errors = []

        with patch('operations.partial_rebuilder.PartialRebuilder') as MockRebuilder:
            mock_instance = MockRebuilder.return_value
            mock_instance.rebuild.return_value = MockResult()

            response = client.post(
                "/api/maintenance/partial-rebuild",
                json={"dry_run": True, "start_id": 100, "end_id": 200}
            )

            assert response.status_code == 200
            data = response.json()

            # Verify required fields
            assert 'dry_run' in data
            assert 'start_id' in data
            assert 'end_id' in data
            assert 'chunks_in_range' in data
            assert 'chunks_embedded' in data
            assert 'time_taken' in data
            assert 'message' in data
            assert 'model_name' in data


class TestEmbeddingRebuilder:
    """Unit tests for EmbeddingRebuilder operation class"""

    @pytest.fixture
    def rebuilder_db(self):
        """Create temporary database for EmbeddingRebuilder testing"""
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
        conn.commit()
        conn.close()

        yield path

        os.close(fd)
        os.unlink(path)

    def test_rebuilder_initialization(self, rebuilder_db):
        """EmbeddingRebuilder should initialize with db_path"""
        import sys
        sys.path.insert(0, '/media/veracrypt1/CODE/rag-kb/api')
        from operations.embedding_rebuilder import EmbeddingRebuilder

        rebuilder = EmbeddingRebuilder(db_path=rebuilder_db)
        assert rebuilder.db_path == rebuilder_db
        assert rebuilder.batch_size == 32  # default

    def test_rebuilder_result_structure(self, rebuilder_db):
        """EmbeddingRebuilder.rebuild() should return properly structured result"""
        import sys
        sys.path.insert(0, '/media/veracrypt1/CODE/rag-kb/api')
        from operations.embedding_rebuilder import EmbeddingRebuilder, EmbeddingRebuildResult

        rebuilder = EmbeddingRebuilder(db_path=rebuilder_db)
        result = rebuilder.rebuild(dry_run=True)

        assert isinstance(result, EmbeddingRebuildResult)
        assert isinstance(result.dry_run, bool)
        assert isinstance(result.documents_found, int)
        assert isinstance(result.chunks_found, int)
        assert isinstance(result.chunks_embedded, int)
        assert isinstance(result.time_taken, float)
        assert isinstance(result.message, str)

    def test_rebuilder_empty_db_returns_appropriate_message(self, rebuilder_db):
        """EmbeddingRebuilder should handle empty database gracefully"""
        import sys
        sys.path.insert(0, '/media/veracrypt1/CODE/rag-kb/api')
        from operations.embedding_rebuilder import EmbeddingRebuilder

        rebuilder = EmbeddingRebuilder(db_path=rebuilder_db)
        result = rebuilder.rebuild(dry_run=False)

        assert result.chunks_found == 0
        assert result.chunks_embedded == 0
        assert 'empty' in result.message.lower() or 'No chunks' in result.message


class TestPartialRebuilder:
    """Unit tests for PartialRebuilder operation class"""

    @pytest.fixture
    def rebuilder_db(self):
        """Create temporary database for PartialRebuilder testing"""
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
        conn.commit()
        conn.close()

        yield path

        os.close(fd)
        os.unlink(path)

    def test_rebuilder_initialization(self, rebuilder_db):
        """PartialRebuilder should initialize with db_path"""
        import sys
        sys.path.insert(0, '/media/veracrypt1/CODE/rag-kb/api')
        from operations.partial_rebuilder import PartialRebuilder

        rebuilder = PartialRebuilder(db_path=rebuilder_db)
        assert rebuilder.db_path == rebuilder_db
        assert rebuilder.batch_size == 32  # default

    def test_rebuilder_result_structure(self, rebuilder_db):
        """PartialRebuilder.rebuild() should return properly structured result"""
        import sys
        sys.path.insert(0, '/media/veracrypt1/CODE/rag-kb/api')
        from operations.partial_rebuilder import PartialRebuilder, PartialRebuildResult

        rebuilder = PartialRebuilder(db_path=rebuilder_db)
        result = rebuilder.rebuild(dry_run=True)

        assert isinstance(result, PartialRebuildResult)
        assert isinstance(result.dry_run, bool)
        assert isinstance(result.chunks_in_range, int)
        assert isinstance(result.chunks_embedded, int)
        assert isinstance(result.time_taken, float)
        assert isinstance(result.message, str)

    def test_rebuilder_respects_id_range(self, rebuilder_db):
        """PartialRebuilder should only process chunks in specified range"""
        # Setup: Add chunks with various IDs
        conn = sqlite3.connect(rebuilder_db)
        conn.execute('INSERT INTO documents (id, file_path) VALUES (1, "/test/doc.pdf")')
        conn.execute('INSERT INTO chunks (id, document_id, content) VALUES (10, 1, "chunk 10")')
        conn.execute('INSERT INTO chunks (id, document_id, content) VALUES (20, 1, "chunk 20")')
        conn.execute('INSERT INTO chunks (id, document_id, content) VALUES (30, 1, "chunk 30")')
        conn.execute('INSERT INTO chunks (id, document_id, content) VALUES (40, 1, "chunk 40")')
        conn.commit()
        conn.close()

        import sys
        sys.path.insert(0, '/media/veracrypt1/CODE/rag-kb/api')
        from operations.partial_rebuilder import PartialRebuilder

        rebuilder = PartialRebuilder(db_path=rebuilder_db)
        # Only chunks 20 and 30 should be in range
        result = rebuilder.rebuild(start_id=15, end_id=35, dry_run=True)

        assert result.chunks_in_range == 2
        assert result.start_id == 15
        assert result.end_id == 35

    def test_rebuilder_empty_range_returns_zero(self, rebuilder_db):
        """PartialRebuilder should handle empty range gracefully"""
        # Setup: Add chunks outside the range we'll query
        conn = sqlite3.connect(rebuilder_db)
        conn.execute('INSERT INTO documents (id, file_path) VALUES (1, "/test/doc.pdf")')
        conn.execute('INSERT INTO chunks (id, document_id, content) VALUES (1, 1, "chunk 1")')
        conn.commit()
        conn.close()

        import sys
        sys.path.insert(0, '/media/veracrypt1/CODE/rag-kb/api')
        from operations.partial_rebuilder import PartialRebuilder

        rebuilder = PartialRebuilder(db_path=rebuilder_db)
        # Range with no chunks
        result = rebuilder.rebuild(start_id=100, end_id=200, dry_run=True)

        assert result.chunks_in_range == 0
        assert 'No chunks' in result.message
