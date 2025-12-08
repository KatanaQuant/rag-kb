# Copyright (c) 2024 RAG-KB Contributors
# SPDX-License-Identifier: MIT

"""Tests for maintenance integrity verification endpoints

Tests for:
- GET /api/maintenance/verify-integrity - Verify database integrity
- IntegrityChecker operation class unit tests
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
def integrity_db():
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


class TestVerifyIntegrityEndpoint:
    """Test GET /api/maintenance/verify-integrity endpoint"""

    def test_verify_integrity_returns_healthy_when_no_issues(self, client, integrity_db):
        """Verify integrity returns healthy status when database is consistent"""
        # Setup: Add consistent data
        conn = sqlite3.connect(integrity_db)
        conn.execute('INSERT INTO documents (id, file_path) VALUES (1, "/test/doc.pdf")')
        conn.execute('INSERT INTO chunks (id, document_id, content) VALUES (1, 1, "test content")')
        conn.execute('INSERT INTO fts_chunks (rowid, content, chunk_id) VALUES (1, "test content", 1)')
        conn.commit()
        conn.close()

        # Create mock checker that returns healthy result
        mock_checker = MagicMock()
        mock_checker.check_all.return_value = {
            'all_passed': True,
            'orphan_chunks': {'ok': True, 'count': 0},
        }

        with patch('operations.operations_factory.OperationsFactory') as MockFactory:
            MockFactory.create_integrity_checker.return_value = mock_checker

            response = client.get("/api/maintenance/verify-integrity")

            assert response.status_code == 200
            data = response.json()
            assert data['healthy'] is True
            assert data['issues'] == []
            assert 'checks' in data

    def test_verify_integrity_detects_orphan_chunks(self, client, integrity_db):
        """Verify integrity detects chunks without parent documents"""
        # Create mock checker that returns orphan chunks
        mock_checker = MagicMock()
        mock_checker.check_all.return_value = {
            'all_passed': False,
            'orphan_chunks': {'ok': False, 'count': 5},
        }

        with patch('operations.operations_factory.OperationsFactory') as MockFactory:
            MockFactory.create_integrity_checker.return_value = mock_checker

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
        # Create mock checker that simulates missing embeddings
        mock_checker = MagicMock()
        mock_checker.check_all.return_value = {
            'all_passed': False,
            'vector_count_mismatch': {'ok': False, 'chunks': 100, 'vectors': 95, 'missing': 5},
        }

        with patch('operations.operations_factory.OperationsFactory') as MockFactory:
            MockFactory.create_integrity_checker.return_value = mock_checker

            response = client.get("/api/maintenance/verify-integrity")

            assert response.status_code == 200
            data = response.json()
            assert data['healthy'] is False
            assert any('vector' in issue.lower() or 'missing' in issue.lower() for issue in data['issues'])

    def test_verify_integrity_detects_fts_inconsistency(self, client, integrity_db):
        """Verify integrity detects FTS index inconsistency"""
        # Create mock checker that simulates FTS inconsistency
        mock_checker = MagicMock()
        mock_checker.check_all.return_value = {
            'all_passed': False,
            'orphan_fts': {'ok': False, 'count': 3},
        }

        with patch('operations.operations_factory.OperationsFactory') as MockFactory:
            MockFactory.create_integrity_checker.return_value = mock_checker

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
