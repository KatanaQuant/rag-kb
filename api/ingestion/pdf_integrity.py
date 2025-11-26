"""PDF integrity validation

Detects corrupted, truncated, or partially downloaded PDF files before processing.
Critical for preventing silent failures where broken PDFs produce 0 chunks.
"""
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Tuple


@dataclass
class PDFIntegrityResult:
    """Result of PDF integrity validation"""
    is_valid: bool
    error: Optional[str] = None
    checks_passed: dict = field(default_factory=dict)


class PDFIntegrityValidator:
    """Validates PDF file integrity before extraction

    Detects common corruption patterns:
    - Empty files
    - Truncated downloads (missing EOF marker)
    - Missing PDF header
    - Corrupt xref tables
    - Unreadable page structure

    Uses pypdfium2 library (already available via docling dependency)
    """

    @staticmethod
    def validate(path: Path) -> PDFIntegrityResult:
        """Validate PDF file integrity"""
        validator = _PDFValidationChain(path)
        return validator.run()

    @staticmethod
    def validate_or_raise(path: Path) -> None:
        """Validate PDF and raise exception if invalid"""
        result = PDFIntegrityValidator.validate(path)
        if not result.is_valid:
            raise ValueError(f"PDF integrity check failed: {result.error}")


class _PDFValidationChain:
    """Internal chain of PDF validation checks"""

    def __init__(self, path: Path):
        self.path = path
        self.checks = {}
        self.file_size = 0

    def run(self) -> PDFIntegrityResult:
        """Run all validation checks in sequence"""
        checks = [
            self._check_exists,
            self._check_not_empty,
            self._check_header,
            self._check_eof_marker,
            self._check_structure,
            self._check_first_page,
        ]

        for check in checks:
            result = check()
            if result is not None:
                return result

        return PDFIntegrityResult(is_valid=True, checks_passed=self.checks)

    def _check_exists(self) -> Optional[PDFIntegrityResult]:
        """Check file exists"""
        if not self.path.exists():
            return self._fail("File does not exist")
        self.file_size = self.path.stat().st_size
        return None

    def _check_not_empty(self) -> Optional[PDFIntegrityResult]:
        """Check file has content"""
        if self.file_size == 0:
            self.checks['file_size'] = False
            return self._fail("File is empty (0 bytes)")
        self.checks['file_size'] = True
        return None

    def _check_header(self) -> Optional[PDFIntegrityResult]:
        """Check PDF header signature"""
        try:
            with open(self.path, 'rb') as f:
                header = f.read(8)
                if not header.startswith(b'%PDF-'):
                    self.checks['header'] = False
                    return self._fail("Missing PDF header signature")
                self.checks['header'] = True
                return None
        except Exception as e:
            self.checks['header'] = False
            return self._fail(f"Cannot read file: {e}")

    def _check_eof_marker(self) -> Optional[PDFIntegrityResult]:
        """Check EOF marker exists (detect truncated files)"""
        try:
            with open(self.path, 'rb') as f:
                f.seek(max(0, self.file_size - 1024))
                tail = f.read()
                if b'%%EOF' not in tail:
                    self.checks['eof_marker'] = False
                    return self._fail("Missing %%EOF marker - file may be truncated")
                self.checks['eof_marker'] = True
                return None
        except Exception as e:
            self.checks['eof_marker'] = False
            return self._fail(f"Cannot read file tail: {e}")

    def _check_structure(self) -> Optional[PDFIntegrityResult]:
        """Check pypdfium2 can parse the structure"""
        try:
            import pypdfium2 as pdfium
            self._pdf = pdfium.PdfDocument(str(self.path))

            if len(self._pdf) == 0:
                self.checks['pdf_structure'] = False
                self._pdf.close()
                return self._fail("PDF has 0 pages")

            self.checks['pdf_structure'] = True
            return None
        except Exception as e:
            self.checks['pdf_structure'] = False
            return self._fail(self._interpret_structure_error(str(e)))

    def _check_first_page(self) -> Optional[PDFIntegrityResult]:
        """Check first page is readable (catches xref corruption)"""
        try:
            first_page = self._pdf[0]
            textpage = first_page.get_textpage()
            textpage.close()
            first_page.close()
            self._pdf.close()
            self.checks['first_page_readable'] = True
            return None
        except Exception as e:
            self._pdf.close()
            self.checks['first_page_readable'] = False
            return self._fail(f"Cannot read first page: {str(e)[:100]}")

    def _interpret_structure_error(self, error_msg: str) -> str:
        """Provide helpful error messages for common issues"""
        error_lower = error_msg.lower()
        if 'xref' in error_lower:
            return "Corrupt xref table - file structure damaged"
        if 'trailer' in error_lower:
            return "Missing or corrupt PDF trailer"
        if 'eof' in error_lower or 'syntax' in error_lower:
            return "Unexpected EOF - file truncated"
        return f"PDF structure invalid: {error_msg[:100]}"

    def _fail(self, error: str) -> PDFIntegrityResult:
        """Create failure result"""
        return PDFIntegrityResult(
            is_valid=False,
            error=error,
            checks_passed=self.checks
        )
