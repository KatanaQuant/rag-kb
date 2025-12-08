"""
Comprehensive tests for resumable processing
"""
import pytest
import sqlite3
from pathlib import Path
from unittest.mock import Mock, patch
import tempfile
import shutil

from tests import requires_huggingface

# Import SQLite progress tracker explicitly (not the PostgreSQL alias)
from ingestion.progress import ProcessingProgressTracker, ProcessingProgress
from ingestion import DocumentProcessor, FileHasher
from domain_models import DocumentFile


# temp_db_progress fixture is provided by conftest.py


@pytest.fixture
def tracker(temp_db_progress):
    """Create progress tracker"""
    return ProcessingProgressTracker(temp_db_progress)


class TestProcessingProgressTracker:
    """Test progress tracking functionality"""

    def test_start_new_processing(self, tracker):
        """Test starting fresh processing"""
        progress = tracker.start_processing("/test/file.pdf", "hash123")

        assert progress.file_path == "/test/file.pdf"
        assert progress.file_hash == "hash123"
        assert progress.status == "in_progress"
        assert progress.chunks_processed == 0
        assert progress.last_chunk_end == 0
        assert progress.started_at is not None

    def test_resume_existing_processing(self, tracker):
        """Test resuming from existing progress"""
        # Start processing
        tracker.start_processing("/test/file.pdf", "hash123")
        tracker.update_progress("/test/file.pdf", 10, 500)

        # Resume
        progress = tracker.start_processing("/test/file.pdf", "hash123")

        assert progress.chunks_processed == 10
        assert progress.last_chunk_end == 500
        assert progress.status == "in_progress"

    def test_hash_mismatch_restarts(self, tracker):
        """Test that hash mismatch triggers restart"""
        # Start processing
        tracker.start_processing("/test/file.pdf", "hash123")
        tracker.update_progress("/test/file.pdf", 10, 500)

        # Resume with different hash
        progress = tracker.start_processing("/test/file.pdf", "hash456")

        assert progress.chunks_processed == 0
        assert progress.last_chunk_end == 0
        assert progress.file_hash == "hash456"

    def test_update_progress(self, tracker):
        """Test updating progress"""
        tracker.start_processing("/test/file.pdf", "hash123")
        tracker.update_progress("/test/file.pdf", 5, 250)

        progress = tracker.get_progress("/test/file.pdf")

        assert progress.chunks_processed == 5
        assert progress.last_chunk_end == 250
        assert progress.last_updated is not None

    def test_mark_completed(self, tracker):
        """Test marking file as completed"""
        tracker.start_processing("/test/file.pdf", "hash123")
        tracker.mark_completed("/test/file.pdf")

        progress = tracker.get_progress("/test/file.pdf")

        assert progress.status == "completed"
        assert progress.completed_at is not None

    def test_mark_failed(self, tracker):
        """Test marking file as failed"""
        tracker.start_processing("/test/file.pdf", "hash123")
        tracker.mark_failed("/test/file.pdf", "Test error")

        progress = tracker.get_progress("/test/file.pdf")

        assert progress.status == "failed"
        assert progress.error_message == "Test error"

    def test_get_incomplete_files(self, tracker):
        """Test retrieving incomplete files"""
        tracker.start_processing("/test/file1.pdf", "hash1")
        tracker.start_processing("/test/file2.pdf", "hash2")
        tracker.mark_completed("/test/file2.pdf")
        tracker.start_processing("/test/file3.pdf", "hash3")

        incomplete = tracker.get_incomplete_files()

        assert len(incomplete) == 2
        paths = [p.file_path for p in incomplete]
        assert "/test/file1.pdf" in paths
        assert "/test/file3.pdf" in paths

    def test_get_progress_nonexistent(self, tracker):
        """Test getting progress for non-existent file"""
        progress = tracker.get_progress("/nonexistent.pdf")

        assert progress is None


class TestDocumentProcessor:
    """Test end-to-end document processing"""

    @pytest.fixture
    def temp_file(self):
        """Create temporary markdown file"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write("# Test Document\n\n")
            f.write("Test content for processing\n\n" * 100)
            temp_path = Path(f.name)

        yield temp_path

        temp_path.unlink(missing_ok=True)

    @requires_huggingface
    def test_skip_completed_unchanged(self, tracker, temp_file):
        """Test skipping completed files with matching hash"""
        processor = DocumentProcessor(tracker)

        file_hash = FileHasher.hash_file(temp_file)
        doc_file = DocumentFile(path=temp_file, hash=file_hash)

        # First processing
        chunks1 = processor.process_file(doc_file)

        # Second processing (should skip)
        chunks2 = processor.process_file(doc_file)

        assert len(chunks1) > 0
        assert len(chunks2) == 0  # Skipped

    @requires_huggingface
    def test_reprocess_on_hash_change(self, tracker, temp_file):
        """Test reprocessing when file hash changes"""
        processor = DocumentProcessor(tracker)

        # First processing
        file_hash1 = FileHasher.hash_file(temp_file)
        doc_file1 = DocumentFile(path=temp_file, hash=file_hash1)
        chunks1 = processor.process_file(doc_file1)

        # Modify file
        with open(temp_file, 'a') as f:
            f.write("\nNew content added")

        # Should reprocess
        file_hash2 = FileHasher.hash_file(temp_file)
        doc_file2 = DocumentFile(path=temp_file, hash=file_hash2)
        chunks2 = processor.process_file(doc_file2)

        assert len(chunks1) > 0
        assert len(chunks2) > 0

    @requires_huggingface
    def test_process_without_tracker(self, temp_file):
        """Test legacy processing without tracker"""
        processor = DocumentProcessor(progress_tracker=None)

        file_hash = FileHasher.hash_file(temp_file)
        doc_file = DocumentFile(path=temp_file, hash=file_hash)
        chunks = processor.process_file(doc_file)

        assert len(chunks) > 0

    def test_error_handling(self, tracker):
        """Test error handling marks failure"""
        processor = DocumentProcessor(tracker)

        # Process non-existent file
        doc_file = DocumentFile(path=Path("/nonexistent/file.txt"), hash="fake_hash")
        chunks = processor.process_file(doc_file)

        assert len(chunks) == 0

    @requires_huggingface
    def test_resume_interrupted_processing(self, tracker, temp_file):
        """Test resuming interrupted processing"""
        processor = DocumentProcessor(tracker)

        # Simulate interrupted processing
        file_hash = FileHasher.hash_file(temp_file)
        tracker.start_processing(str(temp_file), file_hash)
        tracker.update_progress(str(temp_file), 5, 250)

        # Resume
        doc_file = DocumentFile(path=temp_file, hash=file_hash)
        chunks = processor.process_file(doc_file)

        progress = tracker.get_progress(str(temp_file))
        assert progress.status == "completed"
