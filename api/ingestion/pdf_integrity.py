"""PDF integrity validation

Detects corrupted, truncated, or partially downloaded PDF files before processing.
Critical for preventing silent failures where broken PDFs produce 0 chunks.
"""
from pathlib import Path
from dataclasses import dataclass
from typing import Optional


@dataclass
class PDFIntegrityResult:
    """Result of PDF integrity validation"""
    is_valid: bool
    error: Optional[str] = None
    checks_passed: dict = None

    def __post_init__(self):
        if self.checks_passed is None:
            self.checks_passed = {}


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
        """Validate PDF file integrity

        Args:
            path: Path to PDF file

        Returns:
            PDFIntegrityResult with validation status and details
        """
        checks = {}

        # Check 1: File exists and has content
        if not path.exists():
            return PDFIntegrityResult(
                is_valid=False,
                error="File does not exist",
                checks_passed=checks
            )

        file_size = path.stat().st_size
        if file_size == 0:
            checks['file_size'] = False
            return PDFIntegrityResult(
                is_valid=False,
                error="File is empty (0 bytes)",
                checks_passed=checks
            )
        checks['file_size'] = True

        # Check 2: PDF header signature
        try:
            with open(path, 'rb') as f:
                header = f.read(8)
                if not header.startswith(b'%PDF-'):
                    checks['header'] = False
                    return PDFIntegrityResult(
                        is_valid=False,
                        error="Missing PDF header signature",
                        checks_passed=checks
                    )
                checks['header'] = True
        except Exception as e:
            checks['header'] = False
            return PDFIntegrityResult(
                is_valid=False,
                error=f"Cannot read file: {e}",
                checks_passed=checks
            )

        # Check 3: EOF marker (detect truncated files)
        try:
            with open(path, 'rb') as f:
                # Check last 1024 bytes for %%EOF
                f.seek(max(0, file_size - 1024))
                tail = f.read()
                if b'%%EOF' not in tail:
                    checks['eof_marker'] = False
                    return PDFIntegrityResult(
                        is_valid=False,
                        error="Missing %%EOF marker - file may be truncated",
                        checks_passed=checks
                    )
                checks['eof_marker'] = True
        except Exception as e:
            checks['eof_marker'] = False
            return PDFIntegrityResult(
                is_valid=False,
                error=f"Cannot read file tail: {e}",
                checks_passed=checks
            )

        # Check 4: pypdfium2 can parse the structure
        try:
            import pypdfium2 as pdfium
            pdf = pdfium.PdfDocument(str(path))

            # Verify we can access basic metadata
            num_pages = len(pdf)
            if num_pages == 0:
                checks['pdf_structure'] = False
                pdf.close()
                return PDFIntegrityResult(
                    is_valid=False,
                    error="PDF has 0 pages",
                    checks_passed=checks
                )
            checks['pdf_structure'] = True

            # Check 5: Can access first page (catches xref corruption)
            try:
                first_page = pdf[0]
                # Attempt to get text page as a smoke test
                textpage = first_page.get_textpage()
                textpage.close()
                first_page.close()
                checks['first_page_readable'] = True
            except Exception as e:
                pdf.close()
                checks['first_page_readable'] = False
                return PDFIntegrityResult(
                    is_valid=False,
                    error=f"Cannot read first page: {str(e)[:100]}",
                    checks_passed=checks
                )

            pdf.close()

        except Exception as e:
            checks['pdf_structure'] = False
            error_msg = str(e)

            # Provide helpful error messages for common issues
            if 'xref' in error_msg.lower():
                error = "Corrupt xref table - file structure damaged"
            elif 'trailer' in error_msg.lower():
                error = "Missing or corrupt PDF trailer"
            elif 'eof' in error_msg.lower() or 'syntax' in error_msg.lower():
                error = "Unexpected EOF - file truncated"
            else:
                error = f"PDF structure invalid: {error_msg[:100]}"

            return PDFIntegrityResult(
                is_valid=False,
                error=error,
                checks_passed=checks
            )

        # All checks passed
        return PDFIntegrityResult(
            is_valid=True,
            checks_passed=checks
        )

    @staticmethod
    def validate_or_raise(path: Path) -> None:
        """Validate PDF and raise exception if invalid

        Args:
            path: Path to PDF file

        Raises:
            ValueError: If PDF is invalid
        """
        result = PDFIntegrityValidator.validate(path)
        if not result.is_valid:
            raise ValueError(f"PDF integrity check failed: {result.error}")
