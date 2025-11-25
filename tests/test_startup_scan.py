"""
TDD Tests for Startup File Scanning

Ensures that all existing files in knowledge_base/ are discovered and queued
during startup, not just files that are created/modified after startup.

Note: Test classes for IndexOrchestrator have been removed as that class was
refactored out to pipeline architecture in v0.11+. The functionality is now
tested through integration tests of the pipeline components.
"""
import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
from api_services.file_walker import FileWalker
from ingestion.file_filter import FileFilterPolicy


class TestStartupFileScan:
    """Test that startup scan finds all existing files"""

    def test_walker_finds_existing_files(self, tmp_path):
        """Test FileWalker discovers all existing files on startup"""
        # Setup: Create files BEFORE walker is initialized (simulates startup)
        (tmp_path / "file1.pdf").touch()
        (tmp_path / "file2.md").touch()
        (tmp_path / "file3.epub").touch()

        # Create walker AFTER files exist (startup scenario)
        walker = FileWalker(tmp_path, {'.pdf', '.md', '.epub'})

        # Should find all 3 files
        found_files = list(walker.walk())
        assert len(found_files) == 3
        assert any(f.name == "file1.pdf" for f in found_files)
        assert any(f.name == "file2.md" for f in found_files)
        assert any(f.name == "file3.epub" for f in found_files)

    def test_walker_finds_files_in_subdirectories(self, tmp_path):
        """Test walker recursively finds files in subdirectories"""
        # Create nested directory structure
        (tmp_path / "subdir1").mkdir()
        (tmp_path / "subdir2").mkdir()
        (tmp_path / "subdir1" / "nested").mkdir()

        (tmp_path / "root.pdf").touch()
        (tmp_path / "subdir1" / "doc1.md").touch()
        (tmp_path / "subdir2" / "doc2.epub").touch()
        (tmp_path / "subdir1" / "nested" / "deep.pdf").touch()

        walker = FileWalker(tmp_path, {'.pdf', '.md', '.epub'})
        found_files = list(walker.walk())

        # Should find all 4 files recursively
        assert len(found_files) == 4

    def test_walker_respects_file_filter_policy(self, tmp_path):
        """Test walker excludes files based on filter policy"""
        # Create files including some that should be excluded
        (tmp_path / "good.pdf").touch()
        (tmp_path / ".hidden.md").touch()
        (tmp_path / "__pycache__").mkdir()
        (tmp_path / "__pycache__" / "cache.py").touch()

        filter_policy = FileFilterPolicy()
        walker = FileWalker(tmp_path, {'.pdf', '.md', '.py'}, filter_policy)
        found_files = list(walker.walk())

        # Should only find good.pdf (hidden and __pycache__ excluded)
        assert len(found_files) == 1
        assert found_files[0].name == "good.pdf"

    def test_walker_excludes_problematic_directory(self, tmp_path):
        """Test walker excludes 'problematic' directory"""
        (tmp_path / "good.pdf").touch()
        (tmp_path / "problematic").mkdir()
        (tmp_path / "problematic" / "bad.pdf").touch()

        filter_policy = FileFilterPolicy()
        walker = FileWalker(tmp_path, {'.pdf'}, filter_policy)
        found_files = list(walker.walk())

        # Should only find good.pdf (problematic/ excluded)
        assert len(found_files) == 1
        assert found_files[0].name == "good.pdf"

    def test_walker_excludes_original_directory(self, tmp_path):
        """Test walker excludes 'original' directory (where EPUBs are moved)"""
        (tmp_path / "active.pdf").touch()
        (tmp_path / "original").mkdir()
        (tmp_path / "original" / "old.epub").touch()

        filter_policy = FileFilterPolicy()
        walker = FileWalker(tmp_path, {'.pdf', '.epub'}, filter_policy)
        found_files = list(walker.walk())

        # Should only find active.pdf (original/ excluded)
        assert len(found_files) == 1
        assert found_files[0].name == "active.pdf"


class TestStartupScanIntegration:
    """Integration tests for complete startup scan flow"""

    def test_large_directory_scan_performance(self, tmp_path):
        """Test walker handles large directories efficiently"""
        # Create 100 files
        for i in range(100):
            (tmp_path / f"doc{i}.pdf").touch()

        walker = FileWalker(tmp_path, {'.pdf'})
        found_files = list(walker.walk())

        # Should find all 100 files
        assert len(found_files) == 100

    def test_mixed_content_realistic_scenario(self, tmp_path):
        """Test realistic knowledge base with mixed content"""
        # Simulate realistic directory structure
        (tmp_path / "books").mkdir()
        (tmp_path / "papers").mkdir()
        (tmp_path / "notes").mkdir()
        (tmp_path / "original").mkdir()
        (tmp_path / ".git").mkdir()

        # Valid files
        (tmp_path / "README.md").touch()
        (tmp_path / "books" / "book1.pdf").touch()
        (tmp_path / "books" / "book2.epub").touch()
        (tmp_path / "papers" / "paper1.pdf").touch()
        (tmp_path / "notes" / "note1.md").touch()

        # Files that should be excluded
        (tmp_path / "original" / "old.epub").touch()
        (tmp_path / ".git" / "config").touch()
        (tmp_path / ".DS_Store").touch()

        filter_policy = FileFilterPolicy()
        walker = FileWalker(tmp_path, {'.pdf', '.md', '.epub'}, filter_policy)
        found_files = list(walker.walk())

        # Should find 5 valid files (README, book1, book2, paper1, note1)
        # Should exclude original/, .git/, .DS_Store
        assert len(found_files) == 5
        file_names = {f.name for f in found_files}
        assert "README.md" in file_names
        assert "book1.pdf" in file_names
        assert "book2.epub" in file_names
        assert "paper1.pdf" in file_names
        assert "note1.md" in file_names
