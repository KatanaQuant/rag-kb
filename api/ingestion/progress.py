import sqlite3
from pathlib import Path
from typing import List, Dict, Tuple, Optional
import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
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

class ProcessingProgress:
    """Processing progress for a document"""
    file_path: str
    file_hash: str
    total_chunks: int = 0
    chunks_processed: int = 0
    status: str = 'in_progress'
    last_chunk_end: int = 0
    error_message: Optional[str] = None
    started_at: Optional[str] = None
    last_updated: Optional[str] = None
    completed_at: Optional[str] = None

class ProcessingProgressTracker:
    """Manages processing progress persistence"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = None
        self._connect()

    def _connect(self):
        """Connect to database"""
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        # Enable WAL mode for better concurrency
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=5000")  # Wait up to 5s for locks

    def start_processing(self, file_path: str, file_hash: str) -> ProcessingProgress:
        """Initialize or resume processing"""
        progress = self.get_progress(file_path)
        if progress and progress.file_hash == file_hash:
            return progress
        if progress:
            self._delete_progress(file_path)
        return self._create_progress(file_path, file_hash)

    def _delete_progress(self, file_path: str):
        """Delete old progress"""
        self.conn.execute("DELETE FROM processing_progress WHERE file_path = ?", (file_path,))
        self.conn.commit()

    def _create_progress(self, file_path: str, file_hash: str) -> ProcessingProgress:
        """Create new progress record"""
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute("""
            INSERT INTO processing_progress
            (file_path, file_hash, started_at, last_updated)
            VALUES (?, ?, ?, ?)
        """, (file_path, file_hash, now, now))
        self.conn.commit()
        return ProcessingProgress(file_path, file_hash, started_at=now, last_updated=now)

    def set_total_chunks(self, file_path: str, total_chunks: int):
        """Set expected total chunk count for document

        Called after extraction to record how many chunks were created.
        """
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute("""
            UPDATE processing_progress
            SET total_chunks = ?, last_updated = ?
            WHERE file_path = ?
        """, (total_chunks, now, file_path))
        self.conn.commit()

    def update_progress(self, file_path: str, chunks_processed: int, last_chunk_end: int):
        """Update progress after batch"""
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute("""
            UPDATE processing_progress
            SET chunks_processed = ?, last_chunk_end = ?, last_updated = ?
            WHERE file_path = ?
        """, (chunks_processed, last_chunk_end, now, file_path))
        self.conn.commit()

    def mark_completed(self, file_path: str):
        """Mark as completed"""
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute("""
            UPDATE processing_progress
            SET status = 'completed', completed_at = ?, last_updated = ?
            WHERE file_path = ?
        """, (now, now, file_path))
        self.conn.commit()

    def mark_failed(self, file_path: str, error_message: str):
        """Mark as failed"""
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute("""
            UPDATE processing_progress
            SET status = 'failed', error_message = ?, last_updated = ?
            WHERE file_path = ?
        """, (error_message, now, file_path))
        self.conn.commit()

    def mark_rejected(self, file_path: str, reason: str, validation_check: str = None):
        """Mark file as rejected due to validation failure

        Args:
            file_path: Path to rejected file
            reason: Rejection reason (e.g., "File too large: 600 MB")
            validation_check: Strategy name that rejected it (e.g., "FileSizeStrategy")
        """
        now = datetime.now(timezone.utc).isoformat()

        # Create or update progress record with rejected status
        existing = self.get_progress(file_path)

        error_msg = f"Validation failed: {reason}"
        if validation_check:
            error_msg = f"Validation failed ({validation_check}): {reason}"

        if existing:
            self.conn.execute("""
                UPDATE processing_progress
                SET status = 'rejected', error_message = ?, last_updated = ?
                WHERE file_path = ?
            """, (error_msg, now, file_path))
        else:
            # Create new record for rejected file (no hash available)
            self.conn.execute("""
                INSERT INTO processing_progress
                (file_path, file_hash, status, error_message, started_at, last_updated)
                VALUES (?, '', 'rejected', ?, ?, ?)
            """, (file_path, error_msg, now, now))

        self.conn.commit()

    def get_incomplete_files(self) -> List[ProcessingProgress]:
        """Get all incomplete files"""
        cursor = self.conn.execute("""
            SELECT file_path, file_hash, total_chunks, chunks_processed,
                   status, last_chunk_end, error_message, started_at,
                   last_updated, completed_at
            FROM processing_progress
            WHERE status = 'in_progress'
        """)
        return [self._row_to_progress(row) for row in cursor.fetchall()]

    def get_rejected_files(self) -> List[ProcessingProgress]:
        """Get all rejected files"""
        cursor = self.conn.execute("""
            SELECT file_path, file_hash, total_chunks, chunks_processed,
                   status, last_chunk_end, error_message, started_at,
                   last_updated, completed_at
            FROM processing_progress
            WHERE status = 'rejected'
            ORDER BY last_updated DESC
        """)
        return [self._row_to_progress(row) for row in cursor.fetchall()]

    def get_progress(self, file_path: str) -> Optional[ProcessingProgress]:
        """Get progress for file"""
        cursor = self.conn.execute("""
            SELECT file_path, file_hash, total_chunks, chunks_processed,
                   status, last_chunk_end, error_message, started_at,
                   last_updated, completed_at
            FROM processing_progress
            WHERE file_path = ?
        """, (file_path,))
        row = cursor.fetchone()
        return self._row_to_progress(row) if row else None

    @staticmethod
    def _row_to_progress(row) -> ProcessingProgress:
        """Convert row to object"""
        return ProcessingProgress(
            file_path=row[0],
            file_hash=row[1],
            total_chunks=row[2],
            chunks_processed=row[3],
            status=row[4],
            last_chunk_end=row[5],
            error_message=row[6],
            started_at=row[7],
            last_updated=row[8],
            completed_at=row[9]
        )

    def delete_document(self, file_path: str) -> bool:
        """Delete processing progress for a document

        Returns:
            True if progress was deleted, False if not found
        """
        cursor = self.conn.execute(
            "DELETE FROM processing_progress WHERE file_path = ?",
            (file_path,)
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def get_db_path(self) -> str:
        """Get database path.

        Delegation method to avoid Law of Demeter violation.
        """
        return self.db_path

    def close(self):
        """Close connection"""
        if self.conn:
            self.conn.close()

