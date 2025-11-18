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
        import subprocess

        temp_pdf = pdf_path.with_suffix('.gs_tmp.pdf')

        try:
            result = subprocess.run([
                'gs', '-dNOPAUSE', '-dBATCH', '-sDEVICE=pdfwrite',
                '-dEmbedAllFonts=true', '-dSubsetFonts=true',
                '-dCompressFonts=true', '-dPDFSETTINGS=/prepress',
                f'-sOutputFile={temp_pdf}', str(pdf_path)
            ], capture_output=True, text=True, timeout=300)

            if result.returncode == 0 and temp_pdf.exists():
                # Replace original with fixed version
                temp_pdf.replace(pdf_path)
                return True
            else:
                # Clean up temp file if it exists
                if temp_pdf.exists():
                    temp_pdf.unlink()
                return False

        except Exception:
            # Clean up temp file if it exists
            if temp_pdf.exists():
                temp_pdf.unlink()
            return False

