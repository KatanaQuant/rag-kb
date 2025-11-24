"""
Comprehensive tests for resumable processing
"""
import pytest
import sqlite3
from pathlib import Path
from unittest.mock import Mock, patch
import tempfile
import shutil

from ingestion import (
    ProcessingProgressTracker,
    ProcessingProgress,
    ChunkedTextProcessor,
    DocumentProcessor,
    TextChunker,
    FileHasher
)
from config import ChunkConfig
from domain_models import DocumentFile


@pytest.fixture
def temp_db():
    """Create temporary database"""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name

    # Initialize schema
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS processing_progress (
            file_path TEXT PRIMARY KEY,
            file_hash TEXT,
            total_chunks INTEGER DEFAULT 0,
            chunks_processed INTEGER DEFAULT 0,
            status TEXT DEFAULT 'in_progress',
            last_chunk_end INTEGER DEFAULT 0,
            error_message TEXT,
            started_at TEXT,
            last_updated TEXT,
            completed_at TEXT
        )
    """)
    conn.commit()
    conn.close()

    yield db_path

    # Cleanup
    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def tracker(temp_db):
    """Create progress tracker"""
    return ProcessingProgressTracker(temp_db)


@pytest.fixture
def chunker():
    """Create text chunker"""
    config = ChunkConfig(size=100, overlap=20, min_size=10, semantic=False)
    return TextChunker(config)


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


class TestChunkedTextProcessor:
    """Test chunk-based text processing"""

    def test_process_new_text(self, tracker, chunker):
        """Test processing text from scratch"""
        processor = ChunkedTextProcessor(chunker, tracker, batch_size=5)

        text = "a" * 1000  # 1000 chars
        chunks = processor.process_text("/test/file.txt", text, "hash123", page_num=1)

        assert len(chunks) > 0
        progress = tracker.get_progress("/test/file.txt")
        assert progress.status == "completed"
        assert progress.chunks_processed == len(chunks)

    def test_resume_from_checkpoint(self, tracker, chunker):
        """Test resuming from saved checkpoint"""
        processor = ChunkedTextProcessor(chunker, tracker, batch_size=5)

        # Simulate partial processing
        tracker.start_processing("/test/file.txt", "hash123")
        tracker.update_progress("/test/file.txt", 5, 400)

        # Resume processing
        full_text = "a" * 1000
        chunks = processor.process_text("/test/file.txt", full_text, "hash123", page_num=1)

        # Should only process remaining text
        assert len(chunks) < len(chunker.chunk(full_text, 1))

    def test_batch_commits(self, tracker, chunker):
        """Test progress updated after each batch"""
        processor = ChunkedTextProcessor(chunker, tracker, batch_size=3)

        text = "a" * 500
        processor.process_text("/test/file.txt", text, "hash123", page_num=1)

        progress = tracker.get_progress("/test/file.txt")
        # Should have multiple updates (batch commits)
        assert progress.chunks_processed > 0
        assert progress.status == "completed"

    def test_empty_text(self, tracker, chunker):
        """Test processing empty text"""
        processor = ChunkedTextProcessor(chunker, tracker, batch_size=5)

        chunks = processor.process_text("/test/file.txt", "", "hash123", page_num=1)

        assert len(chunks) == 0
        progress = tracker.get_progress("/test/file.txt")
        assert progress.status == "completed"


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


class TestIntegration:
    """Integration tests"""

    def test_full_workflow(self, tracker, chunker):
        """Test complete workflow from start to finish"""
        processor = ChunkedTextProcessor(chunker, tracker, batch_size=5)

        # Start processing
        text = "Test content " * 200
        chunks = processor.process_text("/test/doc.pdf", text, "hash_v1", page_num=1)

        # Verify completion
        progress = tracker.get_progress("/test/doc.pdf")
        assert progress.status == "completed"
        assert len(chunks) > 0

        # Should skip on second run
        chunks2 = processor.process_text("/test/doc.pdf", text, "hash_v1", page_num=1)
        assert len(chunks2) == len(chunks)  # Returns same chunks

        # Should restart with new hash
        new_text = text + " additional content " * 100  # Add significant content
        chunks3 = processor.process_text("/test/doc.pdf", new_text, "hash_v2", page_num=1)
        assert len(chunks3) > len(chunks)  # More chunks
