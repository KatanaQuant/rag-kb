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

# Cross-module imports
from .progress import ProcessingProgressTracker, ProcessingProgress
from .extractors import ExtractionRouter
from .helpers import FileHasher

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
        print(f"Warning: Docling HybridChunker not available ({e})")


class MetadataEnricher:
    """Enriches chunks with file metadata"""

    def __init__(self, file_hasher: FileHasher):
        self.file_hasher = file_hasher

    def enrich(self, chunks: List[Dict], file_path: Path) -> List[Dict]:
        """Add metadata to all chunks from a file"""
        file_hash = self.file_hasher.hash_file(file_path)
        file_name = file_path.name

        for chunk in chunks:
            chunk['source'] = str(file_name)
            chunk['file_path'] = str(file_path)
            chunk['file_hash'] = file_hash

        return chunks


class DocumentProcessor:
    """Coordinates document processing

    All chunking is now handled by specialized extractors:
    - Docling HybridChunker for PDF/DOCX/EPUB/Markdown
    - AST-based chunking for code files
    - Cell-aware chunking for Jupyter notebooks
    - Graph-RAG for Obsidian vaults

    The legacy TextChunker has been removed.
    """

    SUPPORTED_EXTENSIONS = {
        # Documents
        '.pdf', '.md', '.markdown', '.docx', '.epub',
        # Code files
        '.py', '.java', '.ts', '.tsx', '.js', '.jsx', '.cs', '.go',
        # Jupyter notebooks
        '.ipynb'
    }

    # All extraction methods produce pre-chunked content
    PRE_CHUNKED_METHODS = {
        # Docling HybridChunker (structure + token-aware)
        'docling', 'docling_hybrid', 'docling_markdown',
        # AST-based code chunking (per-function, per-class)
        'ast_python', 'ast_java', 'ast_typescript', 'ast_tsx',
        'ast_javascript', 'ast_jsx', 'ast_c_sharp', 'ast_go',
        # Jupyter cell-aware chunking
        'jupyter_ast',
        # Obsidian Graph-RAG
        'obsidian_graph_rag',
        # EPUB (converts to PDF then Docling)
        'epub_pandoc_docling',
    }

    def __init__(self, progress_tracker: Optional[ProcessingProgressTracker] = None):
        self.hasher = FileHasher()
        self.extractor = ExtractionRouter()
        self.enricher = MetadataEnricher(self.hasher)
        self.tracker = progress_tracker

        # File type validator for security
        from .file_type_validator import FileTypeValidator, ValidationAction
        self.validator = FileTypeValidator()
        self.validation_enabled = default_config.file_validation.enabled
        self.validation_action = default_config.file_validation.action

    def get_file_hash(self, path: Path) -> str:
        """Get file hash"""
        return self.hasher.hash_file(path)

    def delete_from_tracker(self, file_path: str):
        """Delete document from progress tracker.

        Delegation method to avoid Law of Demeter violation.
        """
        if self.tracker:
            self.tracker.delete_document(file_path)

    def get_obsidian_graph(self):
        """Get Obsidian knowledge graph from extractor.

        Delegation method to avoid Law of Demeter violation.
        """
        return self.extractor.get_obsidian_graph()

    def process_file(self, doc_file: DocumentFile, force: bool = False) -> List[Dict]:
        """Process file into chunks

        Args:
            doc_file: Document file to process
            force: If True, bypass progress tracker check and reprocess
        """
        try:
            if not self._should_process(doc_file, force):
                return []
            return self._do_process(doc_file)
        except FileNotFoundError:
            return self._handle_file_not_found(doc_file)
        except Exception as e:
            return self._handle_processing_error(doc_file, e)

    def _should_process(self, doc_file: DocumentFile, force: bool = False) -> bool:
        """Check if file should be processed

        Args:
            doc_file: Document file to check
            force: If True, bypass the "already completed" check
        """
        if not doc_file.exists():
            return False

        if not self._passes_security_validation(doc_file):
            return False

        if force:
            return True

        return not self._is_already_completed(doc_file)

    def _passes_security_validation(self, doc_file: DocumentFile) -> bool:
        """Check if file passes security validation"""
        if not self.validation_enabled:
            return True

        validation_result = self.validator.validate(doc_file.path)
        if validation_result.is_valid:
            return True

        return self._handle_validation_failure(doc_file, validation_result)

    def _handle_validation_failure(self, doc_file: DocumentFile, validation_result) -> bool:
        """Handle validation failure based on configured action"""
        if self.validation_action == 'reject':
            print(f"REJECTED (security): {doc_file.name} - {validation_result.reason}")
            return False
        elif self.validation_action == 'warn':
            print(f"WARNING (security): {doc_file.name} - {validation_result.reason}")
            return True
        elif self.validation_action == 'skip':
            return False
        return True

    def _is_already_completed(self, doc_file: DocumentFile) -> bool:
        """Check if file has already been processed"""
        if not self.tracker:
            return False

        progress = self.tracker.get_progress(str(doc_file.path))
        return self._is_completed(progress, doc_file.hash)

    def _is_completed(self, progress, file_hash: str) -> bool:
        """Check if file already completed"""
        return progress and progress.status == 'completed' and progress.file_hash == file_hash

    def _do_process(self, doc_file: DocumentFile) -> List[Dict]:
        """Process file: extract and create chunks"""
        print(f"Processing: {doc_file.name}")

        # Initialize progress tracking (creates record for mark_completed to update)
        if self.tracker:
            self.tracker.start_processing(str(doc_file.path), doc_file.hash)

        result = self._extract_text(doc_file)
        all_chunks = self._create_chunks(doc_file, result)
        print(f"Chunking complete: {doc_file.name} - {len(all_chunks)} chunks created")
        return all_chunks

    def _extract_text(self, doc_file: DocumentFile):
        """Extract text from file"""
        result = self.extractor.extract(doc_file.path)
        extraction_method = self.extractor.get_last_method()
        print(f"Extraction complete ({extraction_method}): {doc_file.name} - "
              f"{result.total_chars:,} chars extracted")
        return result

    def _create_chunks(self, doc_file: DocumentFile, result) -> List[Dict]:
        """Create and annotate chunks from extraction result

        All extractors now produce pre-chunked content.
        """
        extraction_method = self.extractor.get_last_method()

        if not self._is_pre_chunked(extraction_method):
            raise RuntimeError(
                f"Unknown extraction method '{extraction_method}'. "
                f"All supported file types should use pre-chunked extractors."
            )

        all_chunks = self._use_chunks_directly(doc_file, result.pages)
        self._annotate_extraction_method(all_chunks, extraction_method)
        return all_chunks

    def _is_pre_chunked(self, method: str) -> bool:
        """Check if extraction method produces pre-chunked content"""
        if not method:
            return False
        return method in self.PRE_CHUNKED_METHODS or method.startswith('ast_')

    def _use_chunks_directly(self, doc_file: DocumentFile, pages: List) -> List[Dict]:
        """Use pre-chunked content directly without re-chunking

        All extractors (Docling, AST, Jupyter, Obsidian) produce semantic chunks.
        """
        all_chunks = []
        for text, page_num in pages:
            if not text or not text.strip():
                continue

            chunk_dict = {
                'content': text,
                'page': page_num
            }
            enriched = self.enricher.enrich([chunk_dict], doc_file.path)
            all_chunks.extend(enriched)

        # Update progress tracker
        if self.tracker:
            self.tracker.mark_completed(str(doc_file.path))

        return all_chunks

    def _annotate_extraction_method(self, chunks: List[Dict], method: str):
        """Add extraction method to all chunks"""
        for chunk in chunks:
            chunk['_extraction_method'] = method

    def _handle_file_not_found(self, doc_file: DocumentFile) -> List[Dict]:
        """Handle file not found during processing"""
        import traceback
        print(f"\nFile not found during processing: {doc_file.name}")
        print(f"Path: {doc_file.path}")
        print(f"File exists check: {doc_file.path.exists()}")
        print("Stack trace:")
        traceback.print_exc()
        print(f"Skipping (file moved/deleted): {doc_file.name}\n")
        return []

    def _handle_processing_error(self, doc_file: DocumentFile, error: Exception) -> List[Dict]:
        """Handle processing errors with cleanup and logging"""
        error_msg = str(error)
        if self.tracker:
            self.tracker.mark_failed(str(doc_file.path), error_msg)
        self._handle_problematic_file(error, error_msg, doc_file.path)
        self._log_error(doc_file.name, error_msg, error)
        return []

    def _handle_problematic_file(self, error: Exception, error_msg: str, path: Path):
        """Move problematic files to problematic/ directory"""
        if self._is_pdf_conversion_error(error, error_msg):
            self._move_to_problematic(path)

    def _is_pdf_conversion_error(self, error: Exception, error_msg: str) -> bool:
        """Check if error is a PDF conversion failure or invalid EPUB"""
        if isinstance(error, ValueError) and "Invalid EPUB file" in error_msg:
            return True
        return isinstance(error, RuntimeError) and "PDF conversion failed" in error_msg

    def _move_to_problematic(self, path: Path):
        """Move problematic file to problematic/ subdirectory"""
        import shutil
        problematic_dir = path.parent / 'problematic'
        problematic_dir.mkdir(exist_ok=True)
        dest = problematic_dir / path.name
        try:
            shutil.move(str(path), str(dest))
            print(f"→ Moved {path.name} to problematic/ subdirectory")
        except Exception as move_error:
            print(f"Warning: Could not move file to problematic/: {move_error}")

    def _log_error(self, filename: str, error_msg: str, error: Exception):
        """Log error with traceback if needed"""
        print(f"\n{'='*80}")
        print(f"ERROR: Failed to process {filename}")
        print(f"{'='*80}")
        print(error_msg)
        print(f"{'='*80}\n")
        if not isinstance(error, (RuntimeError, ValueError)):
            import traceback
            traceback.print_exc()
