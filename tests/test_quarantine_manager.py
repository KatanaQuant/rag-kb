"""Tests for quarantine manager"""
import pytest
from pathlib import Path
import tempfile
import shutil
import json

from pipeline.quarantine_manager import QuarantineManager, QUARANTINE_CHECKS, TRACK_ONLY_CHECKS


class TestQuarantineManager:
    """Test quarantine manager functionality"""

    @pytest.fixture
    def temp_kb(self):
        """Create temporary knowledge base directory"""
        temp_dir = tempfile.mkdtemp()
        kb_path = Path(temp_dir) / "knowledge_base"
        kb_path.mkdir()
        yield kb_path
        shutil.rmtree(temp_dir)

    def test_should_quarantine_dangerous_files(self, temp_kb):
        """Test that dangerous validation checks trigger quarantine"""
        manager = QuarantineManager(temp_kb)

        assert manager.should_quarantine('ExtensionMismatchStrategy') is True
        assert manager.should_quarantine('ArchiveBombStrategy') is True
        assert manager.should_quarantine('ExecutablePermissionStrategy') is True

    def test_should_not_quarantine_safe_files(self, temp_kb):
        """Test that non-dangerous checks don't trigger quarantine"""
        manager = QuarantineManager(temp_kb)

        assert manager.should_quarantine('FileSizeStrategy') is False
        assert manager.should_quarantine('FileExistenceStrategy') is False
        assert manager.should_quarantine('PDFIntegrityStrategy') is False

    def test_quarantine_file_moves_to_quarantine_dir(self, temp_kb):
        """Test file is moved to .quarantine directory"""
        manager = QuarantineManager(temp_kb)

        # Create test file
        test_file = temp_kb / "malware.pdf"
        test_file.write_text("fake executable content")

        # Quarantine it
        success = manager.quarantine_file(
            test_file,
            "Executable masquerading as pdf",
            "ExtensionMismatchStrategy",
            "abc123"
        )

        assert success is True
        assert not test_file.exists()  # Original removed
        assert (manager.quarantine_dir / "malware.pdf.REJECTED").exists()

    def test_quarantine_creates_metadata(self, temp_kb):
        """Test metadata is created for quarantined file"""
        manager = QuarantineManager(temp_kb)

        test_file = temp_kb / "dangerous.exe"
        test_file.write_text("malicious content")

        manager.quarantine_file(
            test_file,
            "Executable file",
            "ExtensionMismatchStrategy"
        )

        # Check metadata file exists
        metadata_path = manager.quarantine_dir / ".metadata.json"
        assert metadata_path.exists()

        # Check metadata content
        with open(metadata_path, 'r') as f:
            data = json.load(f)

        assert "dangerous.exe.REJECTED" in data
        metadata = data["dangerous.exe.REJECTED"]
        assert metadata["reason"] == "Executable file"
        assert metadata["validation_check"] == "ExtensionMismatchStrategy"
        assert metadata["restored"] is False

    def test_quarantine_handles_name_conflicts(self, temp_kb):
        """Test quarantine handles duplicate filenames"""
        manager = QuarantineManager(temp_kb)

        # Create and quarantine first file
        file1 = temp_kb / "test.pdf"
        file1.write_text("content1")
        manager.quarantine_file(file1, "Reason 1", "ExtensionMismatchStrategy")

        # Create and quarantine second file with same name
        file2 = temp_kb / "test.pdf"
        file2.write_text("content2")
        manager.quarantine_file(file2, "Reason 2", "ExtensionMismatchStrategy")

        # Both should exist with different names
        assert (manager.quarantine_dir / "test.pdf.REJECTED").exists()
        assert (manager.quarantine_dir / "test.pdf.REJECTED.1").exists()

    def test_list_quarantined_returns_active_files(self, temp_kb):
        """Test listing quarantined files"""
        manager = QuarantineManager(temp_kb)

        # Quarantine some files
        file1 = temp_kb / "file1.pdf"
        file1.write_text("content1")
        manager.quarantine_file(file1, "Reason 1", "ExtensionMismatchStrategy")

        file2 = temp_kb / "file2.zip"
        file2.write_text("content2")
        manager.quarantine_file(file2, "Reason 2", "ArchiveBombStrategy")

        quarantined = manager.list_quarantined()

        assert len(quarantined) == 2
        reasons = [q.reason for q in quarantined]
        assert "Reason 1" in reasons
        assert "Reason 2" in reasons

    def test_restore_file_moves_back_to_original_location(self, temp_kb):
        """Test restoring file from quarantine"""
        manager = QuarantineManager(temp_kb)

        original_path = temp_kb / "subdir" / "document.pdf"
        original_path.parent.mkdir(parents=True)
        original_path.write_text("original content")

        # Quarantine it
        manager.quarantine_file(
            original_path,
            "Test quarantine",
            "ExtensionMismatchStrategy"
        )

        # Restore it
        success = manager.restore_file("document.pdf.REJECTED")

        assert success is True
        assert original_path.exists()
        assert original_path.read_text() == "original content"
        assert not (manager.quarantine_dir / "document.pdf.REJECTED").exists()

    def test_restore_updates_metadata(self, temp_kb):
        """Test restore updates metadata to mark as restored"""
        manager = QuarantineManager(temp_kb)

        file_path = temp_kb / "file.pdf"
        file_path.write_text("content")
        manager.quarantine_file(file_path, "Reason", "ExtensionMismatchStrategy")

        manager.restore_file("file.pdf.REJECTED")

        # Check metadata marked as restored
        metadata = manager._read_metadata("file.pdf.REJECTED")
        assert metadata.restored is True
        assert metadata.restored_at is not None

    def test_restore_fails_if_original_exists(self, temp_kb):
        """Test restore fails if original path already exists"""
        manager = QuarantineManager(temp_kb)

        original = temp_kb / "document.pdf"
        original.write_text("original")
        manager.quarantine_file(original, "Test", "ExtensionMismatchStrategy")

        # Create new file at original location
        original.write_text("new file")

        # Try to restore (should fail)
        success = manager.restore_file("document.pdf.REJECTED", force=False)

        assert success is False
        assert (manager.quarantine_dir / "document.pdf.REJECTED").exists()

    def test_restore_with_force_overwrites(self, temp_kb):
        """Test restore with force=True overwrites existing file"""
        manager = QuarantineManager(temp_kb)

        original = temp_kb / "document.pdf"
        original.write_text("quarantined content")
        manager.quarantine_file(original, "Test", "ExtensionMismatchStrategy")

        # Create new file at original location
        original.write_text("different content")

        # Restore with force
        success = manager.restore_file("document.pdf.REJECTED", force=True)

        assert success is True
        assert original.read_text() == "quarantined content"

    def test_purge_removes_old_files(self, temp_kb):
        """Test purging old quarantined files"""
        import time
        from datetime import datetime, timezone, timedelta

        manager = QuarantineManager(temp_kb)

        # Create old file by manually setting quarantined_at
        old_file = temp_kb / "old.pdf"
        old_file.write_text("old")
        manager.quarantine_file(old_file, "Old file", "ExtensionMismatchStrategy")

        # Manually update metadata to make it appear old
        metadata = manager._read_metadata("old.pdf.REJECTED")
        old_date = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
        metadata.quarantined_at = old_date
        manager._write_metadata("old.pdf.REJECTED", metadata)

        # Purge files older than 30 days
        purged = manager.purge_old_files(30, dry_run=False)

        assert purged == 1
        assert not (manager.quarantine_dir / "old.pdf.REJECTED").exists()

    def test_purge_dry_run_does_not_delete(self, temp_kb):
        """Test purge dry run doesn't actually delete files"""
        from datetime import datetime, timezone, timedelta

        manager = QuarantineManager(temp_kb)

        file_path = temp_kb / "test.pdf"
        file_path.write_text("content")
        manager.quarantine_file(file_path, "Test", "ExtensionMismatchStrategy")

        # Make it appear old
        metadata = manager._read_metadata("test.pdf.REJECTED")
        old_date = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
        metadata.quarantined_at = old_date
        manager._write_metadata("test.pdf.REJECTED", metadata)

        # Dry run
        purged = manager.purge_old_files(30, dry_run=True)

        assert purged == 1
        assert (manager.quarantine_dir / "test.pdf.REJECTED").exists()  # Still exists

    def test_non_dangerous_files_not_quarantined(self, temp_kb):
        """Test files from non-dangerous checks are not quarantined"""
        manager = QuarantineManager(temp_kb)

        large_file = temp_kb / "huge.pdf"
        large_file.write_text("x" * 1000)

        # Try to quarantine with non-dangerous check
        success = manager.quarantine_file(
            large_file,
            "File too large",
            "FileSizeStrategy"
        )

        assert success is False  # Should not quarantine
        assert large_file.exists()  # File still in original location
        assert not (manager.quarantine_dir / "huge.pdf.REJECTED").exists()
