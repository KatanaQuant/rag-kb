# Copyright (c) 2024 RAG-KB Contributors
# SPDX-License-Identifier: MIT

"""Tests for OrphanDetector - TDD for EPUB conversion handling

Bug: EPUBs in original/ directory are being flagged as orphans, but they
shouldn't be - they're converted to PDF and the PDFs are what gets processed.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock
import tempfile
import sqlite3

from tests import requires_huggingface


class TestOrphanDetector:
    """Test suite for OrphanDetector EPUB handling"""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test files"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def mock_tracker(self, temp_dir):
        """Create a mock progress tracker with real SQLite database"""
        # Create a real SQLite database in temp directory
        db_path = temp_dir / "test_progress.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute('''
            CREATE TABLE processing_progress (
                file_path TEXT PRIMARY KEY,
                file_hash TEXT,
                status TEXT,
                chunks_processed INTEGER DEFAULT 0,
                last_updated TEXT
            )
        ''')
        conn.execute('''
            CREATE TABLE documents (
                id INTEGER PRIMARY KEY,
                file_path TEXT,
                file_hash TEXT
            )
        ''')
        conn.commit()
        conn.close()

        # Create mock tracker that returns the db path
        tracker = Mock()
        tracker.get_db_path.return_value = str(db_path)
        tracker.delete_document = Mock()
        tracker._db_path = str(db_path)
        return tracker

    @pytest.fixture
    def mock_store(self):
        """Create a mock vector store"""
        return Mock()

    @pytest.fixture
    def orphan_detector(self, mock_tracker, mock_store):
        """Create OrphanDetector with mocked dependencies"""
        from operations.orphan_detector import OrphanDetector
        return OrphanDetector(mock_tracker, mock_store)

    def _add_progress_entry(self, tracker, file_path: str, status: str = 'completed'):
        """Helper to add a progress entry to the test database"""
        conn = sqlite3.connect(tracker._db_path)
        conn.execute('''
            INSERT INTO processing_progress (file_path, file_hash, status, last_updated)
            VALUES (?, ?, ?, datetime('now'))
        ''', (file_path, 'test_hash', status))
        conn.commit()
        conn.close()

    def test_epub_in_original_directory_is_converted_epub(self, temp_dir, orphan_detector):
        """EPUB in original/ with sibling PDF should be detected as converted EPUB

        When an EPUB is converted to PDF:
        1. EPUB is moved to original/ subdirectory
        2. PDF is created at the original EPUB location
        3. The EPUB in original/ should NOT be flagged as orphan
        """
        # Setup: create original/ subdir with EPUB and parent PDF
        original_dir = temp_dir / "original"
        original_dir.mkdir()
        epub = original_dir / "book.epub"
        epub.write_text("fake epub content")
        pdf = temp_dir / "book.pdf"
        pdf.write_text("fake pdf content")

        # EPUB in original/ with PDF in parent should be detected as converted
        assert orphan_detector._is_converted_epub(epub) is True

    def test_epub_not_in_original_with_pdf_not_converted(self, temp_dir, orphan_detector):
        """EPUB not in original/ that has been moved should be detected

        Original case: EPUB at /kb/book.epub is converted:
        1. PDF created at /kb/book.pdf
        2. EPUB moved to /kb/original/book.epub
        3. Database still has entry for /kb/book.epub (old path)
        """
        # Setup: EPUB was at root, now has original/ copy and PDF
        original_dir = temp_dir / "original"
        original_dir.mkdir()
        original_epub = original_dir / "book.epub"
        original_epub.write_text("fake epub")
        pdf = temp_dir / "book.pdf"
        pdf.write_text("fake pdf")

        # The old path (without original/) should also be detected as converted
        # because original/book.epub exists AND book.pdf exists
        old_epub_path = temp_dir / "book.epub"
        assert orphan_detector._is_converted_epub(old_epub_path) is True

    def test_epub_without_pdf_not_converted(self, temp_dir, orphan_detector):
        """EPUB in original/ WITHOUT sibling PDF is NOT a converted EPUB"""
        # Setup: create original/ subdir with EPUB but NO PDF
        original_dir = temp_dir / "original"
        original_dir.mkdir()
        epub = original_dir / "book.epub"
        epub.write_text("fake epub content")
        # NO PDF exists

        # Should NOT be detected as converted (PDF doesn't exist)
        assert orphan_detector._is_converted_epub(epub) is False

    def test_epub_outside_original_without_conversion_not_converted(self, temp_dir, orphan_detector):
        """EPUB outside original/ without original/ copy is NOT converted"""
        # Setup: EPUB at root with no original/ subdirectory
        epub = temp_dir / "book.epub"
        epub.write_text("fake epub content")
        # No original/ directory, no PDF

        # Should NOT be detected as converted
        assert orphan_detector._is_converted_epub(epub) is False

    def test_non_epub_file_not_converted(self, temp_dir, orphan_detector):
        """Non-EPUB files are never considered converted EPUBs"""
        # Setup: PDF file
        pdf = temp_dir / "book.pdf"
        pdf.write_text("fake pdf content")

        # Should NOT be detected as converted (not an EPUB)
        assert orphan_detector._is_converted_epub(pdf) is False

    @requires_huggingface
    def test_repair_orphans_cleans_converted_epub(self, temp_dir, mock_tracker, orphan_detector):
        """Converted EPUBs should be cleaned from progress tracker, not queued"""
        # Setup: EPUB in original/ with sibling PDF
        original_dir = temp_dir / "original"
        original_dir.mkdir()
        epub = original_dir / "book.epub"
        epub.write_text("fake epub")
        pdf = temp_dir / "book.pdf"
        pdf.write_text("fake pdf")

        # Add progress entry for the EPUB path (as it appears in DB)
        self._add_progress_entry(mock_tracker, str(epub))

        # Create mock queue
        mock_queue = Mock()

        # Patch detect_orphans to return test data (avoid hitting production DB)
        # Note: detect_orphans() creates its own DB connection, bypassing mock_tracker
        orphan_detector.detect_orphans = Mock(return_value=[
            {'path': str(epub), 'chunks': 10, 'updated': '2024-01-01'}
        ])

        # Run repair
        orphan_detector.repair_orphans(mock_queue)

        # Verify: delete_document was called to clean up the EPUB entry
        mock_tracker.delete_document.assert_called_with(str(epub))

        # Verify: queue.add was NOT called (EPUB should not be reprocessed)
        mock_queue.add.assert_not_called()
