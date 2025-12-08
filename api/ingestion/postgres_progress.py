"""
Processing progress tracker using PostgreSQL.

Replaces SQLite progress tracking with PostgreSQL for consistency
with the main database layer.
"""
from typing import List, Optional
from datetime import datetime, timezone
import logging

from config import default_config
from ingestion.database_factory import DatabaseFactory
from ingestion.progress import ProcessingProgress

logger = logging.getLogger(__name__)


class PostgresProgressTracker:
    """Manages processing progress persistence using PostgreSQL."""

    def __init__(self, config=default_config.database):
        self.config = config
        self.db_conn = DatabaseFactory.create_connection(config)
        self.conn = None
        self._progress_cache: dict = None
        self._connect()

    def _connect(self):
        """Connect to database"""
        self.conn = self.db_conn.connect()

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
        with self.conn.cursor() as cur:
            cur.execute("DELETE FROM processing_progress WHERE file_path = %s", (file_path,))
        self.conn.commit()

    def _create_progress(self, file_path: str, file_hash: str) -> ProcessingProgress:
        """Create new progress record"""
        now = datetime.now(timezone.utc).isoformat()
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO processing_progress
                (file_path, file_hash, started_at, last_updated)
                VALUES (%s, %s, %s, %s)
            """, (file_path, file_hash, now, now))
        self.conn.commit()
        return ProcessingProgress(file_path, file_hash, started_at=now, last_updated=now)

    def set_total_chunks(self, file_path: str, total_chunks: int):
        """Set expected total chunk count for document"""
        now = datetime.now(timezone.utc).isoformat()
        with self.conn.cursor() as cur:
            cur.execute("""
                UPDATE processing_progress
                SET total_chunks = %s, last_updated = %s
                WHERE file_path = %s
            """, (total_chunks, now, file_path))
        self.conn.commit()

    def update_progress(self, file_path: str, chunks_processed: int, last_chunk_end: int):
        """Update progress after batch"""
        now = datetime.now(timezone.utc).isoformat()
        with self.conn.cursor() as cur:
            cur.execute("""
                UPDATE processing_progress
                SET chunks_processed = %s, last_chunk_end = %s, last_updated = %s
                WHERE file_path = %s
            """, (chunks_processed, last_chunk_end, now, file_path))
        self.conn.commit()

    def mark_completed(self, file_path: str):
        """Mark as completed"""
        now = datetime.now(timezone.utc).isoformat()
        with self.conn.cursor() as cur:
            cur.execute("""
                UPDATE processing_progress
                SET status = 'completed', completed_at = %s, last_updated = %s
                WHERE file_path = %s
            """, (now, now, file_path))
        self.conn.commit()

    def mark_failed(self, file_path: str, error_message: str):
        """Mark as failed"""
        now = datetime.now(timezone.utc).isoformat()
        with self.conn.cursor() as cur:
            cur.execute("""
                UPDATE processing_progress
                SET status = 'failed', error_message = %s, last_updated = %s
                WHERE file_path = %s
            """, (error_message, now, file_path))
        self.conn.commit()

    def mark_rejected(self, file_path: str, reason: str, validation_check: str = None):
        """Mark file as rejected due to validation failure"""
        now = datetime.now(timezone.utc).isoformat()
        existing = self.get_progress(file_path)

        error_msg = f"Validation failed: {reason}"
        if validation_check:
            error_msg = f"Validation failed ({validation_check}): {reason}"

        with self.conn.cursor() as cur:
            if existing:
                cur.execute("""
                    UPDATE processing_progress
                    SET status = 'rejected', error_message = %s, last_updated = %s
                    WHERE file_path = %s
                """, (error_msg, now, file_path))
            else:
                cur.execute("""
                    INSERT INTO processing_progress
                    (file_path, file_hash, status, error_message, started_at, last_updated)
                    VALUES (%s, '', 'rejected', %s, %s, %s)
                """, (file_path, error_msg, now, now))
        self.conn.commit()

    def get_incomplete_files(self) -> List[ProcessingProgress]:
        """Get all incomplete files"""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT file_path, file_hash, total_chunks, chunks_processed,
                       status, last_chunk_end, error_message, started_at,
                       last_updated, completed_at
                FROM processing_progress
                WHERE status = 'in_progress'
            """)
            return [self._row_to_progress(row) for row in cur.fetchall()]

    def get_rejected_files(self) -> List[ProcessingProgress]:
        """Get all rejected files"""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT file_path, file_hash, total_chunks, chunks_processed,
                       status, last_chunk_end, error_message, started_at,
                       last_updated, completed_at
                FROM processing_progress
                WHERE status = 'rejected'
                ORDER BY last_updated DESC
            """)
            return [self._row_to_progress(row) for row in cur.fetchall()]

    def get_progress(self, file_path: str) -> Optional[ProcessingProgress]:
        """Get progress for file (uses cache if available)"""
        if self._progress_cache is not None:
            return self._progress_cache.get(file_path)

        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT file_path, file_hash, total_chunks, chunks_processed,
                       status, last_chunk_end, error_message, started_at,
                       last_updated, completed_at
                FROM processing_progress
                WHERE file_path = %s
            """, (file_path,))
            row = cur.fetchone()
            return self._row_to_progress(row) if row else None

    def preload_all_progress(self) -> None:
        """Preload all progress records in single query (fixes N+1)"""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT file_path, file_hash, total_chunks, chunks_processed,
                       status, last_chunk_end, error_message, started_at,
                       last_updated, completed_at
                FROM processing_progress
            """)
            self._progress_cache = {}
            for row in cur.fetchall():
                progress = self._row_to_progress(row)
                self._progress_cache[progress.file_path] = progress

    def clear_cache(self) -> None:
        """Clear the progress cache"""
        self._progress_cache = None

    @staticmethod
    def _row_to_progress(row) -> ProcessingProgress:
        """Convert row to object"""
        return ProcessingProgress(
            file_path=row[0],
            file_hash=row[1],
            total_chunks=row[2] or 0,
            chunks_processed=row[3] or 0,
            status=row[4] or 'in_progress',
            last_chunk_end=row[5] or 0,
            error_message=row[6],
            started_at=row[7],
            last_updated=row[8],
            completed_at=row[9]
        )

    def delete_document(self, file_path: str) -> bool:
        """Delete processing progress for a document"""
        with self.conn.cursor() as cur:
            cur.execute(
                "DELETE FROM processing_progress WHERE file_path = %s",
                (file_path,)
            )
            rowcount = cur.rowcount
        self.conn.commit()
        return rowcount > 0

    def get_db_path(self) -> str:
        """Get database connection info (for compatibility)."""
        return self.config.database_url

    def close(self):
        """Close connection"""
        self.db_conn.close()


# Alias for compatibility
ProcessingProgressTracker = PostgresProgressTracker
