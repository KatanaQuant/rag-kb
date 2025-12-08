"""Tests for rejection tracking system"""
import pytest
from pathlib import Path
import tempfile
import shutil
import sqlite3

from ingestion.progress import ProcessingProgressTracker, ProcessingProgress


# temp_db_progress fixture is provided by conftest.py


class TestRejectionTracking:
    """Test rejection tracking in ProcessingProgressTracker"""

    def test_mark_rejected_creates_new_record(self, temp_db_progress):
        """Test marking a file as rejected creates new record"""
        tracker = ProcessingProgressTracker(temp_db_progress)

        tracker.mark_rejected(
            "/app/knowledge_base/malware.pdf",
            "File too large: 600 MB",
            "FileSizeStrategy"
        )

        rejected = tracker.get_rejected_files()
        assert len(rejected) == 1
        assert rejected[0].file_path == "/app/knowledge_base/malware.pdf"
        assert rejected[0].status == "rejected"
        assert "FileSizeStrategy" in rejected[0].error_message
        assert "File too large" in rejected[0].error_message

    def test_mark_rejected_updates_existing_record(self, temp_db_progress):
        """Test marking existing file as rejected updates record"""
        tracker = ProcessingProgressTracker(temp_db_progress)

        # Create in_progress record
        tracker.start_processing("/app/knowledge_base/test.pdf", "abc123")

        # Mark as rejected
        tracker.mark_rejected(
            "/app/knowledge_base/test.pdf",
            "Archive bomb detected",
            "ArchiveBombStrategy"
        )

        # Check updated
        progress = tracker.get_progress("/app/knowledge_base/test.pdf")
        assert progress.status == "rejected"
        assert "ArchiveBombStrategy" in progress.error_message

    def test_get_rejected_files_returns_only_rejected(self, temp_db_progress):
        """Test get_rejected_files returns only rejected status"""
        tracker = ProcessingProgressTracker(temp_db_progress)

        # Create various states
        tracker.start_processing("/app/kb/in_progress.pdf", "hash1")
        tracker.mark_rejected("/app/kb/rejected1.pdf", "Too large", "FileSizeStrategy")
        tracker.mark_rejected("/app/kb/rejected2.pdf", "Zip bomb", "ArchiveBombStrategy")
        tracker.mark_completed("/app/kb/in_progress.pdf")

        rejected = tracker.get_rejected_files()
        assert len(rejected) == 2
        assert all(r.status == "rejected" for r in rejected)

    def test_rejected_files_ordered_by_timestamp(self, temp_db_progress):
        """Test rejected files are ordered by most recent first"""
        tracker = ProcessingProgressTracker(temp_db_progress)

        tracker.mark_rejected("/app/kb/old.pdf", "Reason 1", "Strategy1")
        import time
        time.sleep(0.1)
        tracker.mark_rejected("/app/kb/new.pdf", "Reason 2", "Strategy2")

        rejected = tracker.get_rejected_files()
        # Most recent first
        assert rejected[0].file_path == "/app/kb/new.pdf"
        assert rejected[1].file_path == "/app/kb/old.pdf"

    def test_mark_rejected_includes_validation_check(self, temp_db_progress):
        """Test mark_rejected properly formats error message with check name"""
        tracker = ProcessingProgressTracker(temp_db_progress)

        tracker.mark_rejected(
            "/app/kb/exec.pdf",
            "Executable masquerading as pdf",
            "ExtensionMismatchStrategy"
        )

        rejected = tracker.get_rejected_files()
        error_msg = rejected[0].error_message

        assert "Validation failed" in error_msg
        assert "ExtensionMismatchStrategy" in error_msg
        assert "Executable masquerading as pdf" in error_msg

    def test_mark_rejected_without_check_name(self, temp_db_progress):
        """Test mark_rejected works without validation_check parameter"""
        tracker = ProcessingProgressTracker(temp_db_progress)

        tracker.mark_rejected(
            "/app/kb/file.pdf",
            "Some generic reason",
            None
        )

        rejected = tracker.get_rejected_files()
        assert "Validation failed: Some generic reason" in rejected[0].error_message
        # Should not have empty parentheses
        assert "()" not in rejected[0].error_message


class TestEmptyFileWhitelist:
    """Test empty file whitelist functionality"""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory"""
        temp = tempfile.mkdtemp()
        yield Path(temp)
        shutil.rmtree(temp)

    def test_init_py_allowed_when_empty(self, temp_dir):
        """Test __init__.py is allowed to be empty"""
        from ingestion.file_type_validator import FileTypeValidator

        init_file = temp_dir / "__init__.py"
        init_file.touch()  # Create empty file

        validator = FileTypeValidator()
        result = validator.validate(init_file)

        # Should pass validation even though empty
        assert result.is_valid is True

    def test_gitkeep_allowed_when_empty(self, temp_dir):
        """Test .gitkeep is allowed to be empty (at existence check level)"""
        from ingestion.validation_strategies import FileExistenceStrategy

        gitkeep = temp_dir / ".gitkeep"
        gitkeep.touch()  # Create empty file

        # Test at the FileExistenceStrategy level (before extension check)
        strategy = FileExistenceStrategy()
        result = strategy.validate(gitkeep)

        # Should pass existence check even though empty
        assert result.is_valid is True

    def test_regular_empty_file_rejected(self, temp_dir):
        """Test regular empty files are still rejected"""
        from ingestion.file_type_validator import FileTypeValidator

        empty_pdf = temp_dir / "document.pdf"
        empty_pdf.touch()  # Create empty file

        validator = FileTypeValidator()
        result = validator.validate(empty_pdf)

        # Should fail validation
        assert result.is_valid is False
        assert "empty" in result.reason.lower()
        assert result.validation_check == "FileExistenceStrategy"
