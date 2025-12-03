"""Tests for security validation strategies"""
import pytest
from pathlib import Path
import tempfile
import shutil
import zipfile
import os

from ingestion.security_strategies import (
    FileSizeStrategy,
    ArchiveBombStrategy,
    ExtensionMismatchStrategy,
    ExecutablePermissionStrategy
)


class TestFileSizeStrategy:
    """Test file size validation"""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory"""
        temp = tempfile.mkdtemp()
        yield Path(temp)
        shutil.rmtree(temp)

    def test_accepts_small_file(self, temp_dir):
        """Small files should pass validation"""
        file_path = temp_dir / "small.pdf"
        file_path.write_bytes(b"x" * 1024)  # 1 KB

        strategy = FileSizeStrategy(max_size_mb=10)
        result = strategy.validate(file_path, 'pdf')

        assert result.is_valid is True

    def test_rejects_oversized_file(self, temp_dir):
        """Files exceeding max size should be rejected"""
        file_path = temp_dir / "huge.pdf"
        file_path.write_bytes(b"x" * (11 * 1024 * 1024))  # 11 MB

        strategy = FileSizeStrategy(max_size_mb=10)
        result = strategy.validate(file_path, 'pdf')

        assert result.is_valid is False
        assert "too large" in result.reason.lower()
        assert "11" in result.reason  # Shows actual size

    def test_warns_on_large_file(self, temp_dir, capsys):
        """Files above warn threshold should trigger warning"""
        file_path = temp_dir / "large.pdf"
        file_path.write_bytes(b"x" * (150 * 1024 * 1024))  # 150 MB

        strategy = FileSizeStrategy(max_size_mb=500, warn_size_mb=100)
        result = strategy.validate(file_path, 'pdf')

        assert result.is_valid is True  # Still passes
        captured = capsys.readouterr()
        assert "warning" in captured.out.lower()
        assert "150" in captured.out

    def test_custom_size_limits(self, temp_dir):
        """Strategy should respect custom size limits"""
        file_path = temp_dir / "medium.pdf"
        file_path.write_bytes(b"x" * (50 * 1024 * 1024))  # 50 MB

        strategy = FileSizeStrategy(max_size_mb=100, warn_size_mb=25)
        result = strategy.validate(file_path, 'pdf')

        assert result.is_valid is True


class TestArchiveBombStrategy:
    """Test archive bomb detection"""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory"""
        temp = tempfile.mkdtemp()
        yield Path(temp)
        shutil.rmtree(temp)

    def test_accepts_normal_zip(self, temp_dir):
        """Normal ZIP files should pass"""
        zip_path = temp_dir / "normal.zip"

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("file1.txt", "x" * 1000)
            zf.writestr("file2.txt", "y" * 1000)

        strategy = ArchiveBombStrategy()
        result = strategy.validate(zip_path, 'zip')

        assert result.is_valid is True

    def test_rejects_high_compression_ratio(self, temp_dir):
        """ZIP with extreme compression ratio should be rejected"""
        zip_path = temp_dir / "bomb.zip"

        # Create ZIP with very high compression ratio
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            # Highly compressible data (all zeros)
            zf.writestr("zeros.txt", b"\x00" * (50 * 1024 * 1024), compress_type=zipfile.ZIP_DEFLATED)

        strategy = ArchiveBombStrategy()
        result = strategy.validate(zip_path, 'zip')

        # Should be rejected for high compression ratio
        assert result.is_valid is False
        assert "compression ratio" in result.reason.lower() or "uncompressed size" in result.reason.lower()

    def test_rejects_excessive_uncompressed_size(self, temp_dir):
        """ZIP with huge uncompressed size should be rejected"""
        zip_path = temp_dir / "huge.zip"

        # Create ZIP with many large files to exceed uncompressed size limit
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_STORED) as zf:
            # Add multiple 100MB files (totaling > 1GB uncompressed)
            for i in range(12):
                # Use STORED (no compression) with actual data
                zf.writestr(f"file{i}.txt", b"x" * (100 * 1024 * 1024))

        strategy = ArchiveBombStrategy()
        result = strategy.validate(zip_path, 'zip')

        # Should be rejected for excessive uncompressed size
        assert result.is_valid is False
        assert "uncompressed size" in result.reason.lower()

    def test_accepts_epub_files(self, temp_dir):
        """EPUB files (ZIP-based) should be validated"""
        epub_path = temp_dir / "book.epub"

        # Create minimal EPUB structure
        with zipfile.ZipFile(epub_path, 'w') as zf:
            zf.writestr("mimetype", "application/epub+zip")
            zf.writestr("content.opf", "<package></package>")

        strategy = ArchiveBombStrategy()
        result = strategy.validate(epub_path, 'epub')

        assert result.is_valid is True

    def test_ignores_non_archive_files(self, temp_dir):
        """Non-archive files should pass through"""
        text_path = temp_dir / "document.txt"
        text_path.write_text("Normal text file")

        strategy = ArchiveBombStrategy()
        result = strategy.validate(text_path, 'text')

        assert result.is_valid is True


class TestExtensionMismatchStrategy:
    """Test extension mismatch detection"""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory"""
        temp = tempfile.mkdtemp()
        yield Path(temp)
        shutil.rmtree(temp)

    def test_accepts_valid_pdf(self, temp_dir):
        """PDF with correct extension should pass"""
        pdf_path = temp_dir / "document.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\nSome PDF content")

        strategy = ExtensionMismatchStrategy()
        result = strategy.validate(pdf_path, 'pdf')

        assert result.is_valid is True

    def test_rejects_executable_as_pdf(self, temp_dir):
        """Executable renamed to .pdf should be rejected"""
        fake_pdf = temp_dir / "malware.pdf"
        fake_pdf.write_bytes(b"MZ\x90\x00")  # PE executable header

        strategy = ExtensionMismatchStrategy()
        result = strategy.validate(fake_pdf, 'pdf')

        assert result.is_valid is False
        assert "executable" in result.reason.lower()
        assert "masquerading" in result.reason.lower()

    def test_rejects_elf_as_document(self, temp_dir):
        """ELF binary renamed to document should be rejected"""
        fake_doc = temp_dir / "file.docx"
        fake_doc.write_bytes(b"\x7fELF")  # ELF header

        strategy = ExtensionMismatchStrategy()
        result = strategy.validate(fake_doc, 'docx')

        assert result.is_valid is False
        assert "executable" in result.reason.lower()

    def test_accepts_zip_based_formats(self, temp_dir):
        """ZIP-based formats (DOCX, EPUB) should be compatible"""
        docx_path = temp_dir / "document.docx"

        # Create valid ZIP structure
        with zipfile.ZipFile(docx_path, 'w') as zf:
            zf.writestr("word/document.xml", "<document/>")

        strategy = ExtensionMismatchStrategy()
        result = strategy.validate(docx_path, 'docx')

        assert result.is_valid is True

    def test_rejects_pdf_as_txt(self, temp_dir):
        """PDF renamed to .txt should be rejected"""
        fake_txt = temp_dir / "file.txt"
        fake_txt.write_bytes(b"%PDF-1.4\nContent")

        strategy = ExtensionMismatchStrategy()
        result = strategy.validate(fake_txt, 'text')

        assert result.is_valid is False
        assert "pdf" in result.reason.lower()


class TestExecutablePermissionStrategy:
    """Test executable permission detection"""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory"""
        temp = tempfile.mkdtemp()
        yield Path(temp)
        shutil.rmtree(temp)

    def test_accepts_normal_file(self, temp_dir):
        """File without execute permissions should pass"""
        file_path = temp_dir / "document.pdf"
        file_path.write_bytes(b"%PDF-1.4\nContent")
        os.chmod(file_path, 0o644)  # rw-r--r--

        strategy = ExecutablePermissionStrategy()
        result = strategy.validate(file_path, 'pdf')

        assert result.is_valid is True

    def test_rejects_script_with_shebang(self, temp_dir):
        """File with execute bit and shebang should be rejected"""
        script_path = temp_dir / "malware.pdf"
        script_path.write_bytes(b"#!/bin/bash\nrm -rf /")
        os.chmod(script_path, 0o755)  # rwxr-xr-x

        strategy = ExecutablePermissionStrategy()
        result = strategy.validate(script_path, 'pdf')

        assert result.is_valid is False
        assert "executable" in result.reason.lower()
        assert "shebang" in result.reason.lower()

    def test_rejects_executable_without_shebang(self, temp_dir):
        """File with execute bit but no shebang should fail validation

        This allows PipelineCoordinator to attempt remediation (chmod -x)
        before final rejection decision.
        """
        file_path = temp_dir / "document.pdf"
        file_path.write_bytes(b"%PDF-1.4\nContent")
        os.chmod(file_path, 0o755)  # rwxr-xr-x (accidental chmod)

        strategy = ExecutablePermissionStrategy()
        result = strategy.validate(file_path, 'pdf')

        # Now fails validation (coordinator will remediate)
        assert result.is_valid is False
        assert result.file_type == 'pdf'  # Preserves expected type (not 'script')
        assert result.validation_check == 'ExecutablePermissionStrategy'
        assert "executable" in result.reason.lower()

    def test_detects_any_execute_bit(self, temp_dir):
        """Should detect execute bit for owner, group, or others"""
        file_path = temp_dir / "script.py"
        file_path.write_bytes(b"#!/usr/bin/env python3\nprint('hi')")

        # Test owner execute
        os.chmod(file_path, 0o744)
        strategy = ExecutablePermissionStrategy()
        result = strategy.validate(file_path, 'python')
        assert result.is_valid is False

        # Test group execute
        os.chmod(file_path, 0o654)
        result = strategy.validate(file_path, 'python')
        assert result.is_valid is False

        # Test others execute
        os.chmod(file_path, 0o645)
        result = strategy.validate(file_path, 'python')
        assert result.is_valid is False


class TestSecurityStrategyComposition:
    """Test that security strategies compose correctly"""

    def test_all_strategies_have_validate_method(self):
        """All security strategies should implement validate()"""
        strategies = [
            FileSizeStrategy(),
            ArchiveBombStrategy(),
            ExtensionMismatchStrategy(),
            ExecutablePermissionStrategy()
        ]

        for strategy in strategies:
            assert hasattr(strategy, 'validate')
            assert callable(strategy.validate)

    def test_strategies_return_validation_result(self, tmp_path):
        """All strategies should return ValidationResult"""
        from ingestion.validation_result import ValidationResult

        file_path = tmp_path / "test.txt"
        file_path.write_text("test")

        strategies = [
            FileSizeStrategy(),
            ArchiveBombStrategy(),
            ExtensionMismatchStrategy(),
            ExecutablePermissionStrategy()
        ]

        for strategy in strategies:
            result = strategy.validate(file_path, 'text')
            assert isinstance(result, ValidationResult)
            assert hasattr(result, 'is_valid')
            assert hasattr(result, 'file_type')
            assert hasattr(result, 'reason')
