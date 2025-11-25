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

class FileHasher:
    """Generates file hashes for change detection"""

    @staticmethod
    def hash_file(file_path: Path) -> str:
        """Generate SHA256 hash of file"""
        hasher = hashlib.sha256()
        FileHasher._update_hasher(hasher, file_path)
        return hasher.hexdigest()

    @staticmethod
    def _update_hasher(hasher, file_path: Path):
        """Update hasher with file chunks"""
        with open(file_path, 'rb') as f:
            for chunk in FileHasher._read_chunks(f):
                hasher.update(chunk)

    @staticmethod
    def _read_chunks(file_handle):
        """Yield file chunks for hashing"""
        return iter(lambda: file_handle.read(8192), b'')

class GhostscriptHelper:
    """Helper for PDF font embedding and structure fixes using Ghostscript"""

    @staticmethod
    def fix_pdf(pdf_path: Path) -> bool:
        """
        Process PDF with Ghostscript to embed fonts and fix structure.
        Returns True if successful, False otherwise.
        """
        temp_pdf = pdf_path.with_suffix('.gs_tmp.pdf')

        try:
            result = GhostscriptHelper._run_ghostscript(pdf_path, temp_pdf)
            return GhostscriptHelper._handle_result(result, temp_pdf, pdf_path)
        except Exception:
            GhostscriptHelper._cleanup_temp_file(temp_pdf)
            return False

    @staticmethod
    def _run_ghostscript(pdf_path: Path, temp_pdf: Path):
        """Run Ghostscript to process PDF"""
        import subprocess

        return subprocess.run([
            'gs', '-dNOPAUSE', '-dBATCH', '-sDEVICE=pdfwrite',
            '-dEmbedAllFonts=true', '-dSubsetFonts=true',
            '-dCompressFonts=true', '-dPDFSETTINGS=/prepress',
            f'-sOutputFile={temp_pdf}', str(pdf_path)
        ], capture_output=True, text=True, timeout=300)

    @staticmethod
    def _handle_result(result, temp_pdf: Path, pdf_path: Path) -> bool:
        """Handle Ghostscript execution result"""
        if result.returncode == 0 and temp_pdf.exists():
            temp_pdf.replace(pdf_path)
            return True
        else:
            GhostscriptHelper._cleanup_temp_file(temp_pdf)
            return False

    @staticmethod
    def _cleanup_temp_file(temp_pdf: Path):
        """Clean up temporary PDF file if it exists"""
        if temp_pdf.exists():
            temp_pdf.unlink()

