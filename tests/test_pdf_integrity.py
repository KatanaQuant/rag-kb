"""Tests for PDF integrity validation"""
import pytest
from pathlib import Path
import tempfile
import shutil

from ingestion.pdf_integrity import PDFIntegrityValidator, PDFIntegrityResult


class TestPDFIntegrityValidator:
    """Test suite for PDF integrity validation"""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for test files"""
        temp = tempfile.mkdtemp()
        yield Path(temp)
        shutil.rmtree(temp)

    @pytest.fixture
    def empty_file(self, temp_dir):
        """Create empty file"""
        path = temp_dir / "empty.pdf"
        path.touch()
        return path

    @pytest.fixture
    def no_header_file(self, temp_dir):
        """Create file without PDF header"""
        path = temp_dir / "no_header.pdf"
        path.write_bytes(b"This is not a PDF file\n%%EOF\n")
        return path

    @pytest.fixture
    def no_eof_file(self, temp_dir):
        """Create truncated PDF (missing EOF marker)"""
        path = temp_dir / "truncated.pdf"
        # Valid header but missing EOF - simulates partial download
        path.write_bytes(b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n")
        return path

    @pytest.fixture
    def minimal_valid_pdf(self, temp_dir):
        """Create minimal valid PDF"""
        path = temp_dir / "minimal.pdf"
        # Minimal PDF structure
        content = b"""%PDF-1.4
1 0 obj
<<
/Type /Catalog
/Pages 2 0 R
>>
endobj
2 0 obj
<<
/Type /Pages
/Kids [3 0 R]
/Count 1
>>
endobj
3 0 obj
<<
/Type /Page
/Parent 2 0 R
/MediaBox [0 0 612 792]
/Contents 4 0 R
/Resources <<
/Font <<
/F1 <<
/Type /Font
/Subtype /Type1
/BaseFont /Helvetica
>>
>>
>>
>>
endobj
4 0 obj
<<
/Length 44
>>
stream
BT
/F1 12 Tf
100 700 Td
(Hello World) Tj
ET
endstream
endobj
xref
0 5
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000317 00000 n
trailer
<<
/Size 5
/Root 1 0 R
>>
startxref
410
%%EOF
"""
        path.write_bytes(content)
        return path

    def test_nonexistent_file(self, temp_dir):
        """Test validation of non-existent file"""
        path = temp_dir / "nonexistent.pdf"
        result = PDFIntegrityValidator.validate(path)

        assert not result.is_valid
        assert "does not exist" in result.error

    def test_empty_file(self, empty_file):
        """Test validation of empty file"""
        result = PDFIntegrityValidator.validate(empty_file)

        assert not result.is_valid
        assert "empty" in result.error.lower()
        assert result.checks_passed['file_size'] is False

    def test_no_header(self, no_header_file):
        """Test validation of file without PDF header"""
        result = PDFIntegrityValidator.validate(no_header_file)

        assert not result.is_valid
        assert "header" in result.error.lower()
        assert result.checks_passed['file_size'] is True
        assert result.checks_passed['header'] is False

    def test_missing_eof_marker(self, no_eof_file):
        """Test validation of truncated file (missing EOF)"""
        result = PDFIntegrityValidator.validate(no_eof_file)

        assert not result.is_valid
        assert "EOF" in result.error or "truncated" in result.error.lower()
        assert result.checks_passed['file_size'] is True
        assert result.checks_passed['header'] is True
        assert result.checks_passed['eof_marker'] is False

    def test_minimal_valid_pdf(self, minimal_valid_pdf):
        """Test validation of minimal valid PDF"""
        result = PDFIntegrityValidator.validate(minimal_valid_pdf)

        assert result.is_valid
        assert result.error is None
        assert result.checks_passed['file_size'] is True
        assert result.checks_passed['header'] is True
        assert result.checks_passed['eof_marker'] is True
        assert result.checks_passed['pdf_structure'] is True
        assert result.checks_passed['first_page_readable'] is True

    def test_validate_or_raise_success(self, minimal_valid_pdf):
        """Test validate_or_raise with valid PDF"""
        # Should not raise
        PDFIntegrityValidator.validate_or_raise(minimal_valid_pdf)

    def test_validate_or_raise_failure(self, empty_file):
        """Test validate_or_raise with invalid PDF"""
        with pytest.raises(ValueError) as exc_info:
            PDFIntegrityValidator.validate_or_raise(empty_file)

        assert "integrity check failed" in str(exc_info.value).lower()

    def test_corrupt_xref_table(self, temp_dir):
        """Test validation of PDF with corrupt xref table"""
        path = temp_dir / "corrupt_xref.pdf"
        # PDF with broken xref
        content = b"""%PDF-1.4
1 0 obj
<<
/Type /Catalog
>>
endobj
xref
CORRUPTED XREF TABLE
trailer
<<
/Size 1
/Root 1 0 R
>>
startxref
50
%%EOF
"""
        path.write_bytes(content)
        result = PDFIntegrityValidator.validate(path)

        assert not result.is_valid
        # Should catch xref or structure error
        assert result.checks_passed['file_size'] is True
        assert result.checks_passed['header'] is True
        assert result.checks_passed['eof_marker'] is True

    def test_all_checks_passed_dict(self, minimal_valid_pdf):
        """Test that checks_passed contains all expected checks"""
        result = PDFIntegrityValidator.validate(minimal_valid_pdf)

        expected_checks = [
            'file_size',
            'header',
            'eof_marker',
            'pdf_structure',
            'first_page_readable'
        ]

        for check in expected_checks:
            assert check in result.checks_passed
            assert result.checks_passed[check] is True

    def test_partial_checks_on_early_failure(self, empty_file):
        """Test that checks_passed reflects partial validation on early failure"""
        result = PDFIntegrityValidator.validate(empty_file)

        # Only file_size check should have run
        assert 'file_size' in result.checks_passed
        assert result.checks_passed['file_size'] is False
        # Other checks should not be present (validation stopped early)
        assert 'header' not in result.checks_passed
