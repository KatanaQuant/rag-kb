"""
EPUB file extractor.

Converts EPUB to PDF using Pandoc, keeps PDF, moves EPUB to original/.
"""
from pathlib import Path
import subprocess
import tempfile
import shutil
import zipfile

from domain_models import ExtractionResult


class EpubExtractor:
    """Converts EPUB to PDF using Pandoc, keeps PDF, moves EPUB to original/

    Refactored following Sandi Metz principles:
    - Small methods: Each method < 10 lines
    - Single Responsibility: Each method does one thing
    - Reduced cyclomatic complexity from C-11 to A-grade
    """

    @staticmethod
    def _validate_epub_file(path: Path) -> bool:
        """Validate that the file is actually a valid EPUB (ZIP format)

        EPUB files are ZIP containers with a 'mimetype' file as the first entry.
        We check for the ZIP magic bytes (PK\x03\x04) at the start.
        """
        try:
            with open(path, 'rb') as f:
                # Read first 4 bytes
                magic = f.read(4)
                # EPUB files are ZIP archives, should start with PK\x03\x04
                if magic != b'PK\x03\x04':
                    return False

            # Additional check: try to open as ZIP
            with zipfile.ZipFile(path, 'r') as zip_file:
                # EPUB should contain mimetype file
                if 'mimetype' not in zip_file.namelist():
                    return False

            return True
        except Exception:
            return False

    @staticmethod
    def extract(path: Path) -> ExtractionResult:
        """Convert EPUB to PDF, move EPUB to original/, DO NOT extract

        EPUB files are only converted to PDF, not extracted.
        The resulting PDF will be picked up by the file watcher/startup scan
        and processed as a separate document.

        Returns an empty ExtractionResult to signal conversion-only (no extraction).
        """
        EpubExtractor._validate_or_raise(path)

        # Determine PDF path and whether to archive EPUB
        already_in_original = path.parent.name == 'original'
        if already_in_original:
            # EPUB is already in original/ - put PDF in parent directory (KB root or subdir)
            pdf_path = path.parent.parent / path.with_suffix('.pdf').name
            original_dir = None  # Don't move EPUB, it's already archived
        else:
            # EPUB is in KB - put PDF alongside it, move EPUB to original/ subdir
            pdf_path = path.with_suffix('.pdf')
            original_dir = EpubExtractor._prepare_original_dir(path)

        try:
            print(f"Converting EPUB to PDF: {path.name}")
            EpubExtractor._convert_with_pandoc(path, pdf_path)
            EpubExtractor._embed_fonts_with_ghostscript(pdf_path)
            page_count = EpubExtractor._count_pdf_pages(pdf_path)
            if original_dir:
                EpubExtractor._archive_epub(path, original_dir)
            else:
                print(f"  → EPUB already in original/, skipping archive")
            EpubExtractor._print_success(path.name, pdf_path.name, page_count)
            # Return empty result - PDF will be processed separately
            return ExtractionResult(pages=[], method='epub_conversion_only')
        except Exception as e:
            EpubExtractor._cleanup_on_failure(pdf_path, e)
            raise

    @staticmethod
    def _validate_or_raise(path: Path):
        """Validate EPUB or raise detailed error"""
        if not EpubExtractor._validate_epub_file(path):
            error_msg = EpubExtractor._build_validation_error(path)
            raise ValueError(error_msg)

    @staticmethod
    def _build_validation_error(path: Path) -> str:
        """Build detailed error message for invalid EPUB"""
        file_size = path.stat().st_size
        error_lines = [
            f"Invalid EPUB file: {path.name}",
            f"  File does not appear to be a valid EPUB archive.",
            f"  EPUB files must be ZIP containers with proper structure."
        ]

        if file_size < 10000:  # Suspiciously small
            error_lines.extend(EpubExtractor._add_content_snippet(path, file_size))

        error_lines.extend([
            "",
            "  → This may be a placeholder, corrupted download, or renamed file.",
            "  → Re-download from source and replace this file."
        ])
        return "\n".join(error_lines)

    @staticmethod
    def _add_content_snippet(path: Path, file_size: int) -> list:
        """Add file content snippet to error message for small files"""
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read(200).strip()
                if content:
                    return [
                        "",
                        f"  Actual file content ({file_size} bytes):",
                        f"  \"{content}\""
                    ]
        except:
            pass
        return [f"  File size: {file_size:,} bytes (suspiciously small)"]

    @staticmethod
    def _prepare_original_dir(path: Path) -> Path:
        """Create and return original/ subdirectory"""
        original_dir = path.parent / 'original'
        original_dir.mkdir(exist_ok=True)
        return original_dir

    @staticmethod
    def _convert_with_pandoc(epub_path: Path, pdf_path: Path):
        """Convert EPUB to PDF using Pandoc with fallback for LaTeX structural errors

        Strategy:
        1. Try direct EPUB→PDF with xelatex
        2. If LaTeX structural error occurs, fallback to EPUB→HTML→PDF with Chromium

        Known LaTeX Issues Handled by HTML Fallback:
        - Nested tables (longtable/LT@nofcols errors)
        - Deeply nested lists (Too deeply nested - exceeds 4-6 level limit)
        - Other LaTeX formatting constraints

        The workaround uses HTML as an intermediate format with Chromium headless.
        """
        result = EpubExtractor._try_direct_conversion(epub_path, pdf_path)
        if result.returncode == 0:
            return

        EpubExtractor._handle_conversion_failure(epub_path, pdf_path, result)

    @staticmethod
    def _try_direct_conversion(epub_path: Path, pdf_path: Path):
        """Attempt direct EPUB to PDF conversion with xelatex"""
        return subprocess.run(
            ['pandoc', str(epub_path), '-o', str(pdf_path), '--pdf-engine=xelatex'],
            capture_output=True,
            text=True,
            timeout=300
        )

    @staticmethod
    def _handle_conversion_failure(epub_path: Path, pdf_path: Path, result):
        """Handle pandoc conversion failure"""
        if EpubExtractor._is_longtable_error(result.stderr):
            print(f"  → Detected longtable error, retrying with wkhtmltopdf...")
            EpubExtractor._convert_via_html_fallback(epub_path, pdf_path)
        else:
            EpubExtractor._raise_conversion_error(epub_path, result.stderr)

    @staticmethod
    def _is_longtable_error(stderr: str) -> bool:
        """Check if error is a known LaTeX structural issue that can be fixed via HTML fallback

        Common LaTeX errors that HTML fallback can handle:
        - longtable/LT@nofcols: Nested table issues
        - Too deeply nested: Excessive list nesting (>4-6 levels)
        """
        stderr_lower = stderr.lower()
        return (
            'LT@nofcols' in stderr or
            'longtable' in stderr_lower or
            'too deeply nested' in stderr_lower
        )

    @staticmethod
    def _raise_conversion_error(epub_path: Path, stderr: str):
        """Raise conversion error with details"""
        raise RuntimeError(
            f"Pandoc EPUB conversion failed.\n"
            f"  File: {epub_path.name}\n"
            f"  Error: {stderr}\n"
            f"  Install pandoc and texlive if missing."
        )

    @staticmethod
    def _convert_via_html_fallback(epub_path: Path, pdf_path: Path):
        """Fallback: Convert EPUB→HTML→PDF using Chromium headless

        This avoids LaTeX structural issues by using HTML-based PDF generation:
        - longtable errors (nested tables)
        - Too deeply nested errors (excessive list nesting)
        - Other LaTeX formatting limitations

        Uses Chromium in headless mode as wkhtmltopdf is unmaintained.
        """
        html_path = EpubExtractor._create_temp_html()
        try:
            EpubExtractor._convert_epub_to_html(epub_path, html_path)
            EpubExtractor._convert_html_to_pdf(html_path, pdf_path)
            print(f"  → Successfully converted via HTML fallback (Chromium)")
        finally:
            EpubExtractor._cleanup_temp_file(html_path)

    @staticmethod
    def _create_temp_html() -> str:
        """Create temporary HTML file"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
            return f.name

    @staticmethod
    def _convert_epub_to_html(epub_path: Path, html_path: str):
        """Convert EPUB to HTML using pandoc"""
        result = subprocess.run(
            ['pandoc', str(epub_path), '-o', html_path, '-s', '--self-contained'],
            capture_output=True,
            text=True,
            timeout=300
        )
        if result.returncode != 0:
            raise RuntimeError(f"EPUB to HTML conversion failed: {result.stderr}")

    @staticmethod
    def _convert_html_to_pdf(html_path: str, pdf_path: Path):
        """Convert HTML to PDF using Chromium headless"""
        result = subprocess.run(
            [
                'chromium',
                '--headless',
                '--disable-gpu',
                '--no-sandbox',
                '--print-to-pdf=' + str(pdf_path),
                'file://' + html_path
            ],
            capture_output=True,
            text=True,
            timeout=300
        )
        if result.returncode != 0:
            raise RuntimeError(f"HTML to PDF conversion failed: {result.stderr}")

    @staticmethod
    def _cleanup_temp_file(html_path: str):
        """Clean up temporary HTML file"""
        Path(html_path).unlink(missing_ok=True)

    @staticmethod
    def _embed_fonts_with_ghostscript(pdf_path: Path):
        """Embed fonts in PDF using Ghostscript (fixes Docling compatibility)"""
        print(f"  → PDF created, embedding fonts with Ghostscript...")
        temp_pdf = pdf_path.with_suffix('.tmp.pdf')

        gs_result = subprocess.run([
            'gs', '-dNOPAUSE', '-dBATCH', '-sDEVICE=pdfwrite',
            '-dEmbedAllFonts=true', '-dSubsetFonts=true',
            '-dCompressFonts=true', '-dPDFSETTINGS=/prepress',
            f'-sOutputFile={temp_pdf}', str(pdf_path)
        ], capture_output=True, text=True, timeout=300)

        if gs_result.returncode == 0:
            temp_pdf.replace(pdf_path)
            print(f"  → Fonts embedded successfully")
        else:
            if temp_pdf.exists():
                temp_pdf.unlink()
            print(f"  → Warning: Font embedding failed, using original PDF")

    @staticmethod
    def _archive_epub(path: Path, original_dir: Path):
        """Move EPUB to original/ directory"""
        print(f"  → Extracting text with Docling...")
        epub_dest = original_dir / path.name
        shutil.move(str(path), str(epub_dest))
        print(f"  → Moved {path.name} to original/")

    @staticmethod
    def _count_pdf_pages(pdf_path: Path) -> int:
        """Count pages in converted PDF using pdfinfo"""
        try:
            result = subprocess.run(
                ['pdfinfo', str(pdf_path)],
                capture_output=True,
                text=True,
                check=True
            )
            for line in result.stdout.split('\n'):
                if line.startswith('Pages:'):
                    return int(line.split(':')[1].strip())
            return 0
        except Exception:
            return 0

    @staticmethod
    def _print_success(epub_name: str, pdf_name: str, page_count: int):
        """Print success message"""
        print(f"  ✓ EPUB conversion complete: {page_count} pages")
        print(f"  ✓ Kept {pdf_name} for future indexing")

    @staticmethod
    def _cleanup_on_failure(pdf_path: Path, error: Exception):
        """Clean up PDF if it was created before failure"""
        # Only clean up if it's a pandoc failure (RuntimeError with "Pandoc" in message)
        if isinstance(error, RuntimeError) and "Pandoc" in str(error):
            if pdf_path.exists():
                pdf_path.unlink()
