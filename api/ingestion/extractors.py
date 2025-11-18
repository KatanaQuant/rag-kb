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

# Suppress verbose Docling/PDF warnings and errors
logging.getLogger('pdfminer').setLevel(logging.CRITICAL)
logging.getLogger('PIL').setLevel(logging.CRITICAL)
logging.getLogger('docling').setLevel(logging.CRITICAL)
logging.getLogger('docling_parse').setLevel(logging.CRITICAL)
logging.getLogger('docling_core').setLevel(logging.CRITICAL)
logging.getLogger('pdfium').setLevel(logging.CRITICAL)
warnings.filterwarnings('ignore', category=UserWarning, module='pypdf')

try:
    from docling.document_converter import DocumentConverter
    DOCLING_AVAILABLE = True
except ImportError as e:
    DOCLING_AVAILABLE = False
    print(f"Warning: Docling not available, falling back to pypdf ({e})")

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
        """Lazy load converter (singleton pattern)"""
        if cls._converter is None and DOCLING_AVAILABLE:
            # Use default settings - docling will auto-download models as needed
            # OCR and table structure extraction enabled by default
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
    """Extracts text from Markdown files preserving structure"""

    @staticmethod
    def extract(path: Path) -> ExtractionResult:
        """Extract markdown text preserving structure for semantic chunking"""
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            text = f.read()
        # Keep markdown as-is for semantic chunking to preserve structure
        return ExtractionResult(pages=[(text, None)], method='markdown')

    @staticmethod
    def _strip_html(text: str) -> str:
        """Strip HTML tags from text"""
        import re
        # Remove HTML tags
        clean = re.sub(r'<[^>]+>', '', text)
        return clean


class EpubExtractor:
    """Converts EPUB to PDF using Pandoc, keeps PDF, moves EPUB to original/"""

    @staticmethod
    def extract(path: Path) -> ExtractionResult:
        """Convert EPUB to PDF, move EPUB to original/, extract from PDF"""
        import subprocess
        import shutil

        # Create PDF path in same directory as EPUB
        pdf_path = path.with_suffix('.pdf')

        # Create original/ subdirectory if it doesn't exist
        original_dir = path.parent / 'original'
        original_dir.mkdir(exist_ok=True)

        pandoc_failed = False

        try:
            print(f"Converting EPUB to PDF: {path.name}")

            # Run pandoc to convert EPUB to PDF
            result = subprocess.run(
                ['pandoc', str(path), '-o', str(pdf_path), '--pdf-engine=xelatex'],
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )

            if result.returncode != 0:
                pandoc_failed = True
                raise RuntimeError(
                    f"Pandoc EPUB conversion failed.\n"
                    f"  File: {path.name}\n"
                    f"  Error: {result.stderr}\n"
                    f"  Install pandoc and texlive if missing."
                )

            print(f"  → PDF created, embedding fonts with Ghostscript...")

            # Post-process with Ghostscript to embed fonts (fixes Docling compatibility)
            temp_pdf = pdf_path.with_suffix('.tmp.pdf')
            gs_result = subprocess.run([
                'gs', '-dNOPAUSE', '-dBATCH', '-sDEVICE=pdfwrite',
                '-dEmbedAllFonts=true', '-dSubsetFonts=true',
                '-dCompressFonts=true', '-dPDFSETTINGS=/prepress',
                f'-sOutputFile={temp_pdf}', str(pdf_path)
            ], capture_output=True, text=True, timeout=300)

            if gs_result.returncode == 0:
                # Replace original with font-embedded version
                temp_pdf.replace(pdf_path)
                print(f"  → Fonts embedded successfully")
            else:
                # Ghostscript failed, clean up temp file and continue with original
                if temp_pdf.exists():
                    temp_pdf.unlink()
                print(f"  → Warning: Font embedding failed, using original PDF")

            print(f"  → Extracting text with Docling...")

            # Move EPUB to original/ BEFORE attempting Docling extraction
            # This way if Docling fails, EPUB is already safe in original/
            epub_dest = original_dir / path.name
            shutil.move(str(path), str(epub_dest))
            print(f"  → Moved {path.name} to original/")

            # Use Docling to extract from the generated PDF
            result = DoclingExtractor.extract(pdf_path)

            print(f"  ✓ EPUB conversion complete: {result.page_count} pages extracted")
            print(f"  ✓ Kept {pdf_path.name} for future indexing")

            return result

        except Exception as e:
            # If pandoc failed and PDF was created, clean it up
            if pandoc_failed and pdf_path.exists():
                pdf_path.unlink()
            # Re-raise the exception - PDF will be handled by auto-move feature
            raise


class TextExtractor:
    """Extracts text from various file formats"""

    def __init__(self, config=default_config):
        self.config = config
        self.extractors = self._build_extractors()
        self.last_method = None  # Track which method was used

    def extract(self, file_path: Path) -> ExtractionResult:
        """Extract text based on file extension"""
        ext = file_path.suffix.lower()
        self._validate_extension(ext)

        # Track which extraction method is being used
        method_map = {
            '.pdf': 'docling_hybrid',
            '.docx': 'docling_hybrid',
            '.epub': 'epub_pandoc_docling',
            '.md': 'semantic_markdown',
            '.markdown': 'semantic_markdown',
            '.txt': 'semantic_text'
        }
        self.last_method = method_map.get(ext, 'unknown')

        return self.extractors[ext](file_path)

    def get_last_method(self) -> str:
        """Get the last extraction method used"""
        return self.last_method or 'unknown'

    def _build_extractors(self) -> Dict:
        """Map extensions to extractors - Docling only, no fallbacks"""
        print("Using Docling + HybridChunker for PDF/DOCX/EPUB, semantic chunking for MD/TXT")
        return {
            '.pdf': DoclingExtractor.extract,
            '.docx': DoclingExtractor.extract,
            '.epub': EpubExtractor.extract,
            '.md': MarkdownExtractor.extract,
            '.markdown': MarkdownExtractor.extract,
            '.txt': TextFileExtractor.extract
        }

    def _validate_extension(self, ext: str):
        """Validate extension is supported"""
        if ext not in self.extractors:
            raise ValueError(f"Unsupported: {ext}")

