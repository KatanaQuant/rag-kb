import sqlite3
from pathlib import Path
from typing import List, Dict, Tuple, Optional
import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
import logging
import sys
import warnings

from pypdf import PdfReader
from docx import Document
import markdown
import numpy as np

from config import default_config
from hybrid_search import HybridSearcher
from domain_models import ChunkData, DocumentFile, ExtractionResult
from ingestion.helpers import GhostscriptHelper
from ingestion.jupyter_extractor import JupyterExtractor
from ingestion.obsidian_extractor import ObsidianExtractor
from ingestion.obsidian_graph import ObsidianGraphBuilder
from ingestion.obsidian_detector import get_obsidian_detector

# Suppress verbose Docling/PDF warnings and errors
logging.getLogger('pdfminer').setLevel(logging.CRITICAL)
logging.getLogger('PIL').setLevel(logging.CRITICAL)
logging.getLogger('docling').setLevel(logging.CRITICAL)
logging.getLogger('docling_parse').setLevel(logging.CRITICAL)
logging.getLogger('docling_core').setLevel(logging.CRITICAL)
logging.getLogger('pdfium').setLevel(logging.CRITICAL)
# RapidOCR/EasyOCR warnings (like "text detection result is empty") are normal
# when OCR checks images/pages and finds no text to extract
warnings.filterwarnings('ignore', category=UserWarning, module='pypdf')

try:
    from docling.document_converter import DocumentConverter
    DOCLING_AVAILABLE = True
except ImportError as e:
    DOCLING_AVAILABLE = False
    print(f"Warning: Docling not available ({e})")

# Try to import chunking separately (may not be available in all versions)
try:
    from docling_core.transforms.chunker import HybridChunker
    from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
    from transformers import AutoTokenizer
    DOCLING_CHUNKING_AVAILABLE = True
except ImportError as e:
    DOCLING_CHUNKING_AVAILABLE = False
    if DOCLING_AVAILABLE:
        print(f"Warning: Docling HybridChunker not available ({e}), using fixed-size chunking")

@dataclass

class DoclingExtractor:
    """Extracts text from documents using Docling (advanced parsing)"""

    _converter = None
    _chunker = None

    @classmethod
    def get_converter(cls):
        """Lazy load converter (singleton pattern)

        Uses default Docling configuration with EasyOCR enabled:
        - Supports text-based PDFs (direct text extraction)
        - Supports scanned/image-only PDFs (full OCR)
        - Supports hybrid PDFs with images containing text (text + OCR)
        - EasyOCR backend: Slow but accurate (default)
        - Table structure detection enabled (default)

        Note: RapidOCR warnings like "text detection result is empty" are
        normal when OCR checks images/pages and finds no text.
        """
        if cls._converter is None and DOCLING_AVAILABLE:
            # Use default settings - comprehensive OCR support for all PDF types
            cls._converter = DocumentConverter()
        return cls._converter

    @classmethod
    def get_chunker(cls, max_tokens: int = 512):
        """Lazy load hybrid chunker (singleton pattern)"""
        if cls._chunker is None and DOCLING_CHUNKING_AVAILABLE:
            # HybridChunker with HuggingFaceTokenizer wrapper
            raw_tokenizer = AutoTokenizer.from_pretrained(default_config.model.name)
            hf_tokenizer = HuggingFaceTokenizer(tokenizer=raw_tokenizer, max_tokens=max_tokens)
            cls._chunker = HybridChunker(tokenizer=hf_tokenizer, merge_peers=True)
        return cls._chunker

    @staticmethod
    def extract(path: Path, retry_with_ghostscript: bool = True) -> ExtractionResult:
        """Extract text from PDF/DOCX using Docling with HybridChunker

        Args:
            path: Path to PDF/DOCX file
            retry_with_ghostscript: If True, automatically retry with Ghostscript on failure

        Returns:
            ExtractionResult with pages extracted using Docling + HybridChunker
        """
        try:
            return DoclingExtractor._convert_with_docling(path)
        except Exception as e:
            if DoclingExtractor._should_retry_with_ghostscript(path, retry_with_ghostscript):
                return DoclingExtractor._retry_after_ghostscript_fix(path, e)
            raise

    @staticmethod
    def _convert_with_docling(path: Path) -> ExtractionResult:
        """Convert document using Docling"""
        converter = DoclingExtractor.get_converter()
        result = converter.convert(str(path))

        DoclingExtractor._check_for_conversion_failure(result, path)

        document = result.document
        pages = DoclingExtractor._extract_hybrid_chunks(document)
        return ExtractionResult(pages=pages, method='docling')

    @staticmethod
    def _check_for_conversion_failure(result, path: Path):
        """Check if conversion failed and raise formatted error"""
        if hasattr(result, 'status'):
            from docling.datamodel.base_models import ConversionStatus
            if result.status == ConversionStatus.FAILURE:
                error_details = DoclingExtractor._extract_error_details(result)
                raise RuntimeError(
                    f"Docling conversion failed for: {path.name}\n"
                    f"  Status: FAILURE\n"
                    f"  Details:\n{error_details}"
                )

    @staticmethod
    def _extract_error_details(result) -> str:
        """Extract error messages from conversion result"""
        errors = []
        if hasattr(result, 'errors') and result.errors:
            for error in result.errors[:3]:  # Limit to first 3 errors
                errors.append(f"    - {str(error)}")
        return "\n".join(errors) if errors else "    - No specific error details available"

    @staticmethod
    def _should_retry_with_ghostscript(path: Path, retry_flag: bool) -> bool:
        """Determine if we should attempt Ghostscript retry"""
        return retry_flag and path.suffix.lower() == '.pdf'

    @staticmethod
    def _retry_after_ghostscript_fix(path: Path, original_error: Exception) -> ExtractionResult:
        """Attempt to fix PDF with Ghostscript and retry extraction"""
        error_reason = DoclingExtractor._get_condensed_error_reason(original_error)
        print(f"  → Docling failed ({error_reason}), attempting Ghostscript fix...")

        if not GhostscriptHelper.fix_pdf(path):
            print(f"  → Ghostscript fix failed")
            raise original_error

        print(f"  → Ghostscript succeeded, retrying extraction...")
        try:
            return DoclingExtractor.extract(path, retry_with_ghostscript=False)
        except Exception:
            print(f"  → Retry failed after Ghostscript fix")
            raise original_error

    @staticmethod
    def _get_condensed_error_reason(error: Exception) -> str:
        """Get first line of error message, condensed to 100 chars"""
        error_msg = str(error).split('\n')[0]
        return error_msg[:100] if error_msg else "Unknown error"

    @staticmethod
    def _extract_hybrid_chunks(document) -> List[Tuple[str, int]]:
        """Extract hybrid chunks using HybridChunker (structure + token-aware)"""
        chunker = DoclingExtractor.get_chunker(default_config.chunks.max_tokens)

        chunks_list = []
        chunk_iter = chunker.chunk(document)

        for chunk in chunk_iter:
            # Get chunk text (use text property or export to markdown)
            chunk_text = chunk.text if hasattr(chunk, 'text') else str(chunk)
            # Get page number from metadata if available
            page = chunk.meta.page if hasattr(chunk, 'meta') and hasattr(chunk.meta, 'page') else 0
            chunks_list.append((chunk_text, page))

        return chunks_list

class PDFExtractor:
    """Extracts text from PDF files (fallback when Docling fails)"""

    @staticmethod
    def extract(path: Path) -> ExtractionResult:
        """Extract text with page numbers"""
        reader = PdfReader(path)
        pages = PDFExtractor._extract_pages(reader)
        return ExtractionResult(pages=pages, method='pypdf')

    @staticmethod
    def _extract_pages(reader) -> List[Tuple[str, int]]:
        """Extract all pages"""
        results = []
        for num, page in enumerate(reader.pages, 1):
            PDFExtractor._add_page(results, page, num)
        return results

    @staticmethod
    def _add_page(results: List, page, num: int):
        """Add page if has text"""
        text = page.extract_text()
        if text.strip():
            results.append((text, num))

class DOCXExtractor:
    """Extracts text from DOCX files"""

    @staticmethod
    def extract(path: Path) -> ExtractionResult:
        """Extract text from DOCX"""
        doc = Document(path)
        text = DOCXExtractor._join_paragraphs(doc)
        return ExtractionResult(pages=[(text, None)], method='docx')

    @staticmethod
    def _join_paragraphs(doc) -> str:
        """Join all paragraphs"""
        return '\n'.join([p.text for p in doc.paragraphs])

class TextFileExtractor:
    """Extracts text from plain text files"""

    @staticmethod
    def extract(path: Path) -> ExtractionResult:
        """Extract text from file"""
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            text = f.read()
        return ExtractionResult(pages=[(text, None)], method='text')

class MarkdownExtractor:
    """Extracts text from Markdown files using Docling HybridChunker

    NO FALLBACKS: Fails explicitly if Docling is unavailable or fails.
    """

    @staticmethod
    def extract(path: Path) -> ExtractionResult:
        """Extract markdown using Docling converter + HybridChunker

        NO FALLBACKS: Raises exceptions if Docling is unavailable or fails.

        Returns:
            ExtractionResult with Docling HybridChunker pages

        Raises:
            RuntimeError: If Docling or HybridChunker is unavailable
            Exception: If conversion fails
        """
        if not DOCLING_AVAILABLE:
            raise RuntimeError(
                f"Docling not available for markdown extraction: {path.name}\n"
                "Install docling to enable markdown processing."
            )

        if not DOCLING_CHUNKING_AVAILABLE:
            raise RuntimeError(
                f"Docling HybridChunker not available for markdown extraction: {path.name}\n"
                "Upgrade to docling>=2.9.0 to enable markdown processing."
            )

        # NO try-except: Let conversion errors propagate
        converter = DoclingExtractor.get_converter()
        result = converter.convert(str(path))

        document = result.document
        pages = DoclingExtractor._extract_hybrid_chunks(document)
        return ExtractionResult(pages=pages, method='docling_markdown')

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
            import zipfile
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
        import shutil

        EpubExtractor._validate_or_raise(path)
        pdf_path = path.with_suffix('.pdf')
        original_dir = EpubExtractor._prepare_original_dir(path)

        try:
            print(f"Converting EPUB to PDF: {path.name}")
            EpubExtractor._convert_with_pandoc(path, pdf_path)
            EpubExtractor._embed_fonts_with_ghostscript(pdf_path)
            page_count = EpubExtractor._count_pdf_pages(pdf_path)
            EpubExtractor._archive_epub(path, original_dir)
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
        """Convert EPUB to PDF using Pandoc with fallback for longtable errors

        Strategy:
        1. Try direct EPUB→PDF with xelatex
        2. If longtable error occurs, fallback to EPUB→HTML→PDF with wkhtmltopdf

        Known Issue: Pandoc has a bug with nested tables in EPUB files that causes
        "Forbidden control sequence found while scanning use of \\LT@nofcols" errors.
        The workaround is to use HTML as an intermediate format with wkhtmltopdf.
        """
        result = EpubExtractor._try_direct_conversion(epub_path, pdf_path)
        if result.returncode == 0:
            return

        EpubExtractor._handle_conversion_failure(epub_path, pdf_path, result)

    @staticmethod
    def _try_direct_conversion(epub_path: Path, pdf_path: Path):
        """Attempt direct EPUB to PDF conversion with xelatex"""
        import subprocess
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
        """Check if error is known longtable issue"""
        return 'LT@nofcols' in stderr or 'longtable' in stderr.lower()

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

        This avoids LaTeX longtable issues by using HTML-based PDF generation.
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
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
            return f.name

    @staticmethod
    def _convert_epub_to_html(epub_path: Path, html_path: str):
        """Convert EPUB to HTML using pandoc"""
        import subprocess
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
        import subprocess
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
        import subprocess

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
        import shutil
        print(f"  → Extracting text with Docling...")
        epub_dest = original_dir / path.name
        shutil.move(str(path), str(epub_dest))
        print(f"  → Moved {path.name} to original/")

    @staticmethod
    def _count_pdf_pages(pdf_path: Path) -> int:
        """Count pages in converted PDF using pdfinfo"""
        import subprocess
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

class CodeExtractor:
    """Extracts code with AST-based chunking using astchunk

    NO FALLBACKS: If AST chunking fails, we fail explicitly.
    This ensures we never silently degrade to inferior text extraction.
    """

    _chunker_cache = {}  # Cache chunkers by language

    @staticmethod
    def _get_language(path: Path) -> str:
        """Detect programming language from file extension"""
        ext_to_lang = {
            '.py': 'python',
            '.java': 'java',
            '.ts': 'typescript',
            '.tsx': 'tsx',
            '.js': 'javascript',
            '.jsx': 'jsx',
            '.cs': 'c_sharp',
            '.go': 'go',  # Go language support via tree-sitter-go
        }
        ext = path.suffix.lower()
        return ext_to_lang.get(ext, 'unknown')

    @staticmethod
    def _get_chunker(language: str):
        """Get or create AST chunker for language

        Args:
            language: Programming language (python, java, typescript, go, etc.)

        Raises:
            ImportError: If required chunker library is not available (FAIL FAST)
            Exception: If chunker creation fails (FAIL FAST)
        """
        if language in CodeExtractor._chunker_cache:
            return CodeExtractor._chunker_cache[language]

        # Go uses tree-sitter-go directly (astchunk doesn't support Go yet)
        if language == 'go':
            from ingestion.go_chunker import GoChunker
            chunker = GoChunker(max_chunk_size=2048, metadata_template='default')
        else:
            # Other languages use astchunk
            # NO try-except: Let import errors propagate
            from astchunk import ASTChunkBuilder

            # Create chunker with all required parameters
            # - max_chunk_size: 512 tokens ≈ 2048 chars (assuming 4 chars/token)
            # - language: programming language (python, java, etc.)
            # - metadata_template: 'default' includes filepath, chunk size, line numbers, node count
            #   Valid values: 'none', 'default', 'coderagbench-repoeval', 'coderagbench-swebench-lite'
            chunker = ASTChunkBuilder(
                max_chunk_size=2048,
                language=language,
                metadata_template='default'
            )

        CodeExtractor._chunker_cache[language] = chunker
        return chunker

    @staticmethod
    def extract(path: Path) -> ExtractionResult:
        """Extract code with AST-based chunking

        NO FALLBACKS: Raises exceptions if AST chunking fails.

        Returns:
            ExtractionResult with AST-chunked code blocks as pages

        Raises:
            ValueError: If language is unknown/unsupported
            ImportError: If astchunk is not available
            Exception: If AST parsing fails
        """
        language = CodeExtractor._get_language(path)

        if language == 'unknown':
            raise ValueError(f"Unsupported file extension: {path.suffix}")

        chunker = CodeExtractor._get_chunker(language)

        # Read source code
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            source_code = f.read()

        # Chunk with AST - NO try-except, let errors propagate
        # Note: language is already set in chunker, but chunkify may still need it
        result = chunker.chunkify(source_code)

        # Extract content from astchunk result format
        # astchunk returns list of dicts with 'content' and 'metadata' keys
        chunks = [chunk['content'] for chunk in result]

        # Convert chunks to pages format (text, page_number)
        # For code, we don't have page numbers, so use None
        pages = [(chunk, None) for chunk in chunks]

        return ExtractionResult(pages=pages, method=f'ast_{language}')

class TextExtractor:
    """Extracts text from various file formats"""

    def __init__(self, config=default_config):
        self.config = config
        self.last_method = None  # Track which method was used
        self.obsidian_graph = ObsidianGraphBuilder()  # Shared graph for vault
        self.obsidian_detector = get_obsidian_detector()
        self.jupyter_extractor = JupyterExtractor()  # Instance for notebook extraction
        self.extractors = self._build_extractors()

    def extract(self, file_path: Path) -> ExtractionResult:
        """Extract text based on file extension"""
        ext = file_path.suffix.lower()
        self._validate_extension(ext)

        # Special handling for markdown: detect Obsidian vs regular
        if ext in ['.md', '.markdown']:
            return self._extract_markdown_intelligently(file_path)

        # Track which extraction method is being used
        method_map = {
            '.pdf': 'docling_hybrid',
            '.docx': 'docling_hybrid',
            '.epub': 'epub_pandoc_docling',
            '.txt': 'semantic_text',
            '.py': 'ast_python',
            '.java': 'ast_java',
            '.ts': 'ast_typescript',
            '.tsx': 'ast_tsx',
            '.js': 'ast_javascript',
            '.jsx': 'ast_jsx',
            '.cs': 'ast_c_sharp',
            '.go': 'ast_go',
            '.ipynb': 'jupyter_ast'
        }
        self.last_method = method_map.get(ext, 'unknown')

        return self.extractors[ext](file_path)

    def _extract_markdown_intelligently(self, file_path: Path) -> ExtractionResult:
        """Choose between Obsidian Graph-RAG or regular markdown extraction"""
        if self.obsidian_detector.is_obsidian_note(file_path):
            self.last_method = 'obsidian_graph_rag'
            return ObsidianExtractor.extract(file_path, self.obsidian_graph)
        else:
            self.last_method = 'docling_markdown'
            return MarkdownExtractor.extract(file_path)

    def get_last_method(self) -> str:
        """Get the last extraction method used"""
        return self.last_method or 'unknown'

    def get_obsidian_graph(self) -> ObsidianGraphBuilder:
        """Get the shared Obsidian graph (for persistence)"""
        return self.obsidian_graph

    def _build_extractors(self) -> Dict:
        """Map extensions to extractors - Docling for docs, AST for code, Jupyter for notebooks, Graph-RAG for Obsidian"""
        print("Using Docling + HybridChunker for PDF/DOCX/EPUB, AST chunking for code, Jupyter for .ipynb, Graph-RAG for Obsidian vaults")
        return {
            # Documents
            '.pdf': DoclingExtractor.extract,
            '.docx': DoclingExtractor.extract,
            '.epub': EpubExtractor.extract,
            '.md': MarkdownExtractor.extract,
            '.markdown': MarkdownExtractor.extract,
            '.txt': TextFileExtractor.extract,
            # Code files (AST-based chunking)
            '.py': CodeExtractor.extract,
            '.java': CodeExtractor.extract,
            '.ts': CodeExtractor.extract,
            '.tsx': CodeExtractor.extract,
            '.js': CodeExtractor.extract,
            '.jsx': CodeExtractor.extract,
            '.cs': CodeExtractor.extract,
            '.go': CodeExtractor.extract,
            # Jupyter notebooks (AST + cell-aware chunking)
            '.ipynb': self.jupyter_extractor.extract
        }

    def _validate_extension(self, ext: str):
        """Validate extension is supported"""
        if ext not in self.extractors:
            raise ValueError(f"Unsupported: {ext}")

