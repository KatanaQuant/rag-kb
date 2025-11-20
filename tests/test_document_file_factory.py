"""Tests for DocumentFile factory method - Sandi Metz refactoring

Following 'Tell, Don't Ask' principle: DocumentFile should know how to create itself
from a path, rather than having clients construct it manually.
"""
import pytest
from pathlib import Path
import tempfile
from domain_models import DocumentFile


class TestDocumentFileFactory:
    """Test factory method for DocumentFile creation"""

    def test_from_path_creates_document_file(self, tmp_path):
        """Should create DocumentFile from path"""
        # Create a temporary file
        test_file = tmp_path / "test.pdf"
        test_file.write_text("test content")

        # Create via factory
        doc_file = DocumentFile.from_path(test_file)

        assert doc_file.path == test_file
        assert doc_file.hash is not None
        assert len(doc_file.hash) > 0

    def test_from_path_hash_is_consistent(self, tmp_path):
        """Should return same hash for same file"""
        test_file = tmp_path / "test.pdf"
        test_file.write_text("test content")

        doc1 = DocumentFile.from_path(test_file)
        doc2 = DocumentFile.from_path(test_file)

        assert doc1.hash == doc2.hash

    def test_from_path_hash_changes_when_content_changes(self, tmp_path):
        """Should return different hash when file changes"""
        test_file = tmp_path / "test.pdf"
        test_file.write_text("original content")
        doc1 = DocumentFile.from_path(test_file)

        # Modify file
        test_file.write_text("modified content")
        doc2 = DocumentFile.from_path(test_file)

        assert doc1.hash != doc2.hash

    def test_from_path_preserves_existing_properties(self, tmp_path):
        """Factory-created DocumentFile should have all expected properties"""
        test_file = tmp_path / "document.md"
        test_file.write_text("# Markdown")

        doc_file = DocumentFile.from_path(test_file)

        assert doc_file.name == "document.md"
        assert doc_file.extension == ".md"
        assert doc_file.exists() is True

    def test_from_path_with_nonexistent_file_raises_error(self, tmp_path):
        """Should raise error for nonexistent file

        Following fail-fast principle: Better to catch missing files early
        rather than silently creating invalid DocumentFile objects.
        """
        nonexistent = tmp_path / "missing.pdf"

        with pytest.raises(FileNotFoundError):
            DocumentFile.from_path(nonexistent)
