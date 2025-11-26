# Copyright (c) 2024 RAG-KB Contributors
# SPDX-License-Identifier: MIT

"""Tests for self-healing startup service

Tests for automatic database repair at startup:
- Delete empty documents (records with no chunks)
- Backfill missing chunk counts
- Environment variable control (AUTO_SELF_HEAL)
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
import tempfile
import sqlite3
import os


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


class TestSelfHealingService:
    """Test SelfHealingService class"""

    def test_is_enabled_default_true(self):
        """Self-healing should be enabled by default"""
        from startup.self_healing import SelfHealingService

        with patch.dict(os.environ, {}, clear=True):
            # Remove AUTO_SELF_HEAL if set
            os.environ.pop('AUTO_SELF_HEAL', None)
            healer = SelfHealingService()
            assert healer.is_enabled() is True

    def test_is_enabled_can_be_disabled(self):
        """Self-healing can be disabled via environment variable"""
        from startup.self_healing import SelfHealingService

        with patch.dict(os.environ, {'AUTO_SELF_HEAL': 'false'}):
            healer = SelfHealingService()
            assert healer.is_enabled() is False

    def test_run_when_disabled_returns_early(self):
        """Run should return early when disabled"""
        from startup.self_healing import SelfHealingService

        with patch.dict(os.environ, {'AUTO_SELF_HEAL': 'false'}):
            healer = SelfHealingService()
            result = healer.run()
            assert result == {'enabled': False}


class TestDeleteEmptyDocuments:
    """Test empty document deletion"""

    def test_deletes_documents_with_no_chunks(self, temp_db):
        """Should delete document records that have no chunks"""
        from startup.self_healing import SelfHealingService

        # Add orphan document (no chunks)
        conn = sqlite3.connect(temp_db)
        conn.execute('INSERT INTO documents (id, file_path) VALUES (1, "/test/orphan.pdf")')
        conn.execute('INSERT INTO processing_progress (file_path, status) VALUES ("/test/orphan.pdf", "completed")')
        conn.commit()
        conn.close()

        healer = SelfHealingService(db_path=temp_db)
        result = healer.run()

        assert result['empty_documents']['found'] == 1
        assert result['empty_documents']['deleted'] == 1

        # Verify deletion
        conn = sqlite3.connect(temp_db)
        cursor = conn.execute('SELECT COUNT(*) FROM documents')
        assert cursor.fetchone()[0] == 0
        cursor = conn.execute('SELECT COUNT(*) FROM processing_progress')
        assert cursor.fetchone()[0] == 0
        conn.close()

    def test_keeps_documents_with_chunks(self, temp_db):
        """Should not delete documents that have chunks"""
        from startup.self_healing import SelfHealingService

        # Add document WITH chunks
        conn = sqlite3.connect(temp_db)
        conn.execute('INSERT INTO documents (id, file_path) VALUES (1, "/test/complete.pdf")')
        conn.execute('INSERT INTO chunks (document_id, content) VALUES (1, "chunk content")')
        conn.commit()
        conn.close()

        healer = SelfHealingService(db_path=temp_db)
        result = healer.run()

        assert result['empty_documents']['found'] == 0
        assert result['empty_documents']['deleted'] == 0

        # Verify NOT deleted
        conn = sqlite3.connect(temp_db)
        cursor = conn.execute('SELECT COUNT(*) FROM documents')
        assert cursor.fetchone()[0] == 1
        conn.close()

    def test_handles_multiple_empty_documents(self, temp_db):
        """Should delete multiple empty documents"""
        from startup.self_healing import SelfHealingService

        conn = sqlite3.connect(temp_db)
        conn.execute('INSERT INTO documents (id, file_path) VALUES (1, "/test/empty1.pdf")')
        conn.execute('INSERT INTO documents (id, file_path) VALUES (2, "/test/empty2.pdf")')
        conn.execute('INSERT INTO documents (id, file_path) VALUES (3, "/test/empty3.pdf")')
        conn.commit()
        conn.close()

        healer = SelfHealingService(db_path=temp_db)
        result = healer.run()

        assert result['empty_documents']['found'] == 3
        assert result['empty_documents']['deleted'] == 3

    def test_handles_mix_of_empty_and_complete(self, temp_db):
        """Should only delete empty documents, keep complete ones"""
        from startup.self_healing import SelfHealingService

        conn = sqlite3.connect(temp_db)
        # Empty document
        conn.execute('INSERT INTO documents (id, file_path) VALUES (1, "/test/empty.pdf")')
        # Complete document
        conn.execute('INSERT INTO documents (id, file_path) VALUES (2, "/test/complete.pdf")')
        conn.execute('INSERT INTO chunks (document_id, content) VALUES (2, "chunk")')
        conn.commit()
        conn.close()

        healer = SelfHealingService(db_path=temp_db)
        result = healer.run()

        assert result['empty_documents']['found'] == 1
        assert result['empty_documents']['deleted'] == 1

        # Verify correct document remains
        conn = sqlite3.connect(temp_db)
        cursor = conn.execute('SELECT file_path FROM documents')
        remaining = cursor.fetchone()
        assert remaining[0] == '/test/complete.pdf'
        conn.close()


class TestBackfillChunkCounts:
    """Test chunk count backfilling"""

    def test_backfill_when_migration_available(self, temp_db):
        """Should call backfill migration when available"""
        from startup.self_healing import SelfHealingService

        mock_module = MagicMock()
        mock_module.backfill_chunk_counts = Mock(return_value={
            'checked': 100,
            'updated': 5
        })

        with patch.dict('sys.modules', {'migrations.backfill_chunk_counts': mock_module}):
            healer = SelfHealingService(db_path=temp_db)
            result = healer.run()

            assert result['chunk_counts']['checked'] == 100
            assert result['chunk_counts']['updated'] == 5

    def test_backfill_skipped_when_migration_not_available(self, temp_db):
        """Should skip gracefully when migration module not available"""
        from startup.self_healing import SelfHealingService

        # Ensure migration module is not available
        with patch.dict('sys.modules', {'migrations.backfill_chunk_counts': None}):
            healer = SelfHealingService(db_path=temp_db)
            # This should not raise
            result = healer.run()

            # Should have chunk_counts key (may be skipped or error)
            assert 'chunk_counts' in result


class TestSelfHealingIntegration:
    """Integration tests for self-healing"""

    def test_full_run_returns_results(self, temp_db):
        """Full run should return comprehensive results"""
        from startup.self_healing import SelfHealingService

        healer = SelfHealingService(db_path=temp_db)
        result = healer.run()

        assert 'empty_documents' in result
        assert 'chunk_counts' in result

    def test_healthy_database_needs_no_repairs(self, temp_db):
        """Healthy database should need no repairs"""
        from startup.self_healing import SelfHealingService

        # Add healthy document
        conn = sqlite3.connect(temp_db)
        conn.execute('INSERT INTO documents (id, file_path) VALUES (1, "/test/healthy.pdf")')
        conn.execute('INSERT INTO chunks (document_id, content) VALUES (1, "chunk")')
        conn.commit()
        conn.close()

        healer = SelfHealingService(db_path=temp_db)
        result = healer.run()

        assert result['empty_documents']['deleted'] == 0

    def test_handles_database_errors_gracefully(self):
        """Should handle database errors without crashing"""
        from startup.self_healing import SelfHealingService

        healer = SelfHealingService(db_path='/nonexistent/path/db.sqlite')
        # Should not raise, but should record error
        result = healer.run()

        assert 'error' in result['empty_documents']
