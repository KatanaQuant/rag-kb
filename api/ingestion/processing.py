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

# Cross-module imports
from .chunking import TextChunker
from .progress import ProcessingProgressTracker, ProcessingProgress
from .extractors import TextExtractor
from .helpers import FileHasher

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

class ChunkedTextProcessor:
    """Processes text in resumable chunks"""

    def __init__(self, chunker: TextChunker,
                 progress_tracker: ProcessingProgressTracker,
                 batch_size: int = 50):
        self.chunker = chunker
        self.tracker = progress_tracker
        self.batch_size = batch_size

    def process_text(self, file_path: str, full_text: str,
                    file_hash: str, page_num: int = None) -> List[ChunkData]:
        """Process text with resume"""
        progress = self.tracker.start_processing(file_path, file_hash)

        # Skip if already completed
        if progress.status == 'completed':
            text = full_text
            return self._create_chunks(text, page_num)

        text = self._get_remaining(full_text, progress)
        chunks = self._create_chunks(text, page_num)
        return self._batch_process(file_path, chunks, progress)

    @staticmethod
    def _get_remaining(text: str, progress: ProcessingProgress) -> str:
        """Get unprocessed text"""
        if progress.last_chunk_end > 0:
            return text[progress.last_chunk_end:]
        return text

    def _create_chunks(self, text: str, page: int) -> List[Dict]:
        """Create chunks from text"""
        return self.chunker.chunk(text, page)

    def _batch_process(self, path: str, chunks: List[Dict],
                      progress: ProcessingProgress) -> List[Dict]:
        """Process in batches"""
        all_chunks = []
        chunks_count = progress.chunks_processed
        char_position = progress.last_chunk_end

        for i in range(0, len(chunks), self.batch_size):
            batch = chunks[i:i+self.batch_size]
            all_chunks.extend(batch)
            chunks_count += len(batch)
            char_position += sum(len(c.content) for c in batch)
            self.tracker.update_progress(path, chunks_count, char_position)

        self.tracker.mark_completed(path)
        return all_chunks

    def _update_tracker(self, path: str, batch: List[ChunkData],
                       progress: ProcessingProgress):
        """Update progress tracking"""
        processed = progress.chunks_processed + len(batch)
        chunk_end = progress.last_chunk_end + sum(len(c.content) for c in batch)
        self.tracker.update_progress(path, processed, chunk_end)

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
    """Coordinates document processing"""

    SUPPORTED_EXTENSIONS = {
        # Documents
        '.pdf', '.txt', '.md', '.markdown', '.docx', '.epub',
        # Code files
        '.py', '.java', '.ts', '.tsx', '.js', '.jsx', '.cs', '.go',
        # Jupyter notebooks
        '.ipynb'
    }

    def __init__(self, progress_tracker: Optional[ProcessingProgressTracker] = None):
        self.hasher = FileHasher()
        self.extractor = TextExtractor()
        self.chunker = TextChunker()
        self.enricher = MetadataEnricher(self.hasher)
        self.tracker = progress_tracker
        self.chunked_processor = None
        if self.tracker:
            self.chunked_processor = ChunkedTextProcessor(
                self.chunker, self.tracker, batch_size=50
            )

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

    def process_file(self, doc_file: DocumentFile) -> List[Dict]:
        """Process file into chunks"""
        if self.tracker:
            return self._process_with_resume(doc_file)
        return self._process_legacy(doc_file)

    def _process_with_resume(self, doc_file: DocumentFile) -> List[Dict]:
        """Process with resumable tracking"""
        try:
            if not self._should_process(doc_file):
                return []
            return self._do_resumable_process(doc_file)
        except FileNotFoundError:
            return self._handle_file_not_found(doc_file)
        except Exception as e:
            return self._handle_processing_error(doc_file, e)

    def _should_process(self, doc_file: DocumentFile) -> bool:
        """Check if file should be processed"""
        if not doc_file.exists():
            # Silent skip - file not found (avoid log spam)
            return False

        # Validate file type for security
        if self.validation_enabled:
            validation_result = self.validator.validate(doc_file.path)
            if not validation_result.is_valid:
                # Handle validation failure based on action
                if self.validation_action == 'reject':
                    print(f"REJECTED (security): {doc_file.name} - {validation_result.reason}")
                    return False
                elif self.validation_action == 'warn':
                    print(f"WARNING (security): {doc_file.name} - {validation_result.reason}")
                    # Continue processing
                elif self.validation_action == 'skip':
                    # Silently skip invalid files
                    return False

        progress = self.tracker.get_progress(str(doc_file.path))
        if self._is_completed(progress, doc_file.hash):
            # Silent skip - already completed (avoid log spam)
            return False

        return True

    def _handle_file_not_found(self, doc_file: DocumentFile) -> List[Dict]:
        """Handle file not found during processing"""
        print(f"Skipping (file moved): {doc_file.name}")
        return []

    def _handle_processing_error(self, doc_file: DocumentFile, error: Exception) -> List[Dict]:
        """Handle processing errors with cleanup and logging"""
        error_msg = str(error)
        self._mark_as_failed(doc_file.path, error_msg)
        self._handle_problematic_file(error, error_msg, doc_file.path)
        self._log_error(doc_file.name, error_msg, error)
        return []

    def _mark_as_failed(self, path: Path, error_msg: str):
        """Mark file as failed in tracker"""
        self.tracker.mark_failed(str(path), error_msg)

    def _handle_problematic_file(self, error: Exception, error_msg: str, path: Path):
        """Move problematic files to problematic/ directory"""
        if self._is_pdf_conversion_error(error, error_msg):
            self._move_to_problematic(path)

    def _log_error(self, filename: str, error_msg: str, error: Exception):
        """Log error with traceback if needed"""
        self._print_error(filename, error_msg)
        self._print_traceback_if_needed(error)

    def _is_pdf_conversion_error(self, error: Exception, error_msg: str) -> bool:
        """Check if error is a PDF conversion failure or invalid EPUB"""
        if isinstance(error, ValueError) and "Invalid EPUB file" in error_msg:
            return True
        return isinstance(error, RuntimeError) and "PDF conversion failed" in error_msg

    def _print_error(self, filename: str, error_msg: str):
        """Print formatted error message"""
        print(f"\n{'='*80}")
        print(f"ERROR: Failed to process {filename}")
        print(f"{'='*80}")
        print(error_msg)
        print(f"{'='*80}\n")

    def _print_traceback_if_needed(self, error: Exception):
        """Print traceback for non-RuntimeError/ValueError exceptions"""
        if not isinstance(error, (RuntimeError, ValueError)):
            import traceback
            traceback.print_exc()

    def _move_to_problematic(self, path: Path):
        """Move problematic file to problematic/ subdirectory"""
        import shutil

        # Create problematic directory if it doesn't exist
        problematic_dir = path.parent / 'problematic'
        problematic_dir.mkdir(exist_ok=True)

        # Move file
        dest = problematic_dir / path.name
        try:
            shutil.move(str(path), str(dest))
            print(f"→ Moved {path.name} to problematic/ subdirectory")
        except Exception as move_error:
            print(f"Warning: Could not move file to problematic/: {move_error}")

    def _is_completed(self, progress, file_hash: str) -> bool:
        """Check if file already completed"""
        return progress and progress.status == 'completed' and progress.file_hash == file_hash

    def _do_resumable_process(self, doc_file: DocumentFile) -> List[Dict]:
        """Process with resume capability"""
        print(f"Processing: {doc_file.name}")
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

    def _create_chunks(self, doc_file: DocumentFile, result):
        """Create and annotate chunks"""
        all_chunks = self._chunk_and_enrich_pages(doc_file, result.pages)
        extraction_method = self.extractor.get_last_method()
        self._annotate_extraction_method(all_chunks, extraction_method)
        return all_chunks

    def _chunk_and_enrich_pages(self, doc_file: DocumentFile, pages: List) -> List[Dict]:
        """Chunk and enrich all pages"""
        all_chunks = []
        for text, page_num in pages:
            chunks = self.chunked_processor.process_text(
                str(doc_file.path), text, doc_file.hash, page_num
            )
            chunk_dicts = [c.to_dict() for c in chunks]
            enriched = self.enricher.enrich(chunk_dicts, doc_file.path)
            all_chunks.extend(enriched)
        return all_chunks

    def _annotate_extraction_method(self, chunks: List[Dict], method: str):
        """Add extraction method to all chunks"""
        for chunk in chunks:
            chunk['_extraction_method'] = method

    def _process_legacy(self, doc_file: DocumentFile) -> List[Dict]:
        """Legacy processing without resume"""
        try:
            return self._do_process(doc_file)
        except Exception as e:
            print(f"\nError processing: {doc_file.name}")
            print(f"Error type: {type(e).__name__}: {str(e)}")
            import traceback
            traceback.print_exc()
            print(f"Returning empty chunks for: {doc_file.name}\n")
            return []

    def _do_process(self, doc_file: DocumentFile) -> List[Dict]:
        """Perform processing"""
        result = self.extractor.extract(doc_file.path)
        extraction_method = self.extractor.get_last_method()
        chunks = self._process_pages(result.pages, doc_file.path)
        self._annotate_extraction_method(chunks, extraction_method)
        return chunks

    def _process_pages(self, pages: List, path: Path) -> List[Dict]:
        """Process extracted pages"""
        all_chunks = []
        for text, page_num in pages:
            self._add_page_chunks(all_chunks, text, page_num, path)
        return all_chunks

    def _add_page_chunks(self, all_chunks, text, page, path):
        """Add chunks for one page"""
        chunks = self.chunker.chunk(text, page)
        # Convert ChunkData to dicts for metadata enrichment
        chunk_dicts = [c.to_dict() for c in chunks]
        enriched = self.enricher.enrich(chunk_dicts, path)
        all_chunks.extend(enriched)

