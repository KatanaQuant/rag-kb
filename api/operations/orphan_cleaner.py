"""Orphan data cleanup service

Cleans up orphan data from the RAG database:
1. Orphan chunks - chunks referencing non-existent documents
2. Orphan vec_chunks - HNSW entries for deleted chunks (estimated)
3. Orphan fts_chunks - FTS entries for deleted chunks

Extracted from scripts/cleanup_orphans.py for API use.
"""
import sqlite3
from dataclasses import dataclass
from typing import List


@dataclass
class OrphanCleanupResult:
    """Result of orphan cleanup operation"""
    dry_run: bool
    orphan_chunks_found: int
    orphan_chunks_deleted: int
    orphan_vec_chunks_estimate: int
    orphan_fts_chunks_estimate: int
    message: str


class OrphanCleaner:
    """Database orphan cleanup service with injectable db_path

    Cleans orphan chunks (invalid document_id), and their associated
    FTS and vec_chunks entries.

    Example:
        cleaner = OrphanCleaner(db_path="/app/data/rag.db")
        result = cleaner.clean(dry_run=True)
        if result.orphan_chunks_found > 0:
            result = cleaner.clean(dry_run=False)
    """

    def __init__(self, db_path: str):
        """Initialize cleaner with database path

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path

    def clean(self, dry_run: bool = False) -> OrphanCleanupResult:
        """Find and optionally remove orphan data

        Args:
            dry_run: If True, only report what would be deleted.
                     If False, actually delete orphans.

        Returns:
            OrphanCleanupResult with counts of orphans found and deleted
        """
        conn = sqlite3.connect(self.db_path)

        # Try to load vectorlite for vec_chunks access
        self._try_load_vectorlite(conn)

        # Find orphan chunks
        orphan_chunk_ids = self._find_orphan_chunks(conn)

        # Estimate orphan vec_chunks and fts_chunks
        vec_estimate = self._estimate_orphan_vec_chunks(conn)
        fts_estimate = self._estimate_orphan_fts_chunks(conn)

        deleted_count = 0
        if not dry_run and orphan_chunk_ids:
            deleted_count = self._delete_orphans(conn, orphan_chunk_ids)
            conn.commit()

        conn.close()

        return self._build_result(
            dry_run=dry_run,
            orphan_chunk_ids=orphan_chunk_ids,
            deleted_count=deleted_count,
            vec_estimate=vec_estimate,
            fts_estimate=fts_estimate
        )

    def _try_load_vectorlite(self, conn: sqlite3.Connection) -> None:
        """Attempt to load vectorlite extension for vec_chunks access"""
        try:
            import vectorlite_py
            conn.enable_load_extension(True)
            conn.load_extension(vectorlite_py.vectorlite_path())
        except Exception:
            # Vectorlite not available, vec_chunks operations will handle gracefully
            pass

    def _find_orphan_chunks(self, conn: sqlite3.Connection) -> List[int]:
        """Find chunks that reference non-existent documents

        Returns:
            List of chunk IDs that are orphans
        """
        cursor = conn.execute("""
            SELECT c.id
            FROM chunks c
            LEFT JOIN documents d ON c.document_id = d.id
            WHERE d.id IS NULL
        """)
        return [row[0] for row in cursor.fetchall()]

    def _estimate_orphan_vec_chunks(self, conn: sqlite3.Connection) -> int:
        """Estimate orphan vec_chunks by comparing counts

        vec_chunks uses rowid = chunk.id. We can't enumerate rowids directly
        (vectorlite limitation), but we can compare counts.

        Returns:
            Estimated orphan count (vec_chunks - chunks), or 0 if error
        """
        try:
            cursor = conn.execute("SELECT COUNT(*) FROM chunks")
            chunk_count = cursor.fetchone()[0]

            cursor = conn.execute("SELECT COUNT(*) FROM vec_chunks")
            vec_count = cursor.fetchone()[0]

            return max(0, vec_count - chunk_count)
        except sqlite3.OperationalError:
            # vec_chunks table may not exist or vectorlite not loaded
            return 0

    def _estimate_orphan_fts_chunks(self, conn: sqlite3.Connection) -> int:
        """Estimate orphan fts_chunks by comparing counts

        FTS virtual tables don't support efficient LEFT JOINs,
        so we use count comparison as a proxy.

        Returns:
            Estimated orphan count (fts_chunks - chunks), or 0 if error
        """
        try:
            cursor = conn.execute("SELECT COUNT(*) FROM chunks")
            chunk_count = cursor.fetchone()[0]

            cursor = conn.execute("SELECT COUNT(*) FROM fts_chunks")
            fts_count = cursor.fetchone()[0]

            return max(0, fts_count - chunk_count)
        except sqlite3.OperationalError:
            return 0

    def _delete_orphans(self, conn: sqlite3.Connection, orphan_ids: List[int]) -> int:
        """Delete orphan chunks and their related entries

        Deletes:
        1. vec_chunks entries (if vectorlite loaded)
        2. fts_chunks entries
        3. chunks themselves

        Args:
            conn: Database connection
            orphan_ids: List of orphan chunk IDs to delete

        Returns:
            Number of chunks deleted
        """
        if not orphan_ids:
            return 0

        placeholders = ','.join('?' * len(orphan_ids))

        # Delete from vec_chunks first (may fail if vectorlite not loaded)
        try:
            conn.execute(
                f"DELETE FROM vec_chunks WHERE rowid IN ({placeholders})",
                orphan_ids
            )
        except sqlite3.OperationalError:
            # vec_chunks table may not exist or vectorlite not loaded
            pass

        # Delete from fts_chunks
        conn.execute(
            f"DELETE FROM fts_chunks WHERE chunk_id IN ({placeholders})",
            orphan_ids
        )

        # Delete the orphan chunks themselves
        conn.execute(
            f"DELETE FROM chunks WHERE id IN ({placeholders})",
            orphan_ids
        )

        return len(orphan_ids)

    def _build_result(
        self,
        dry_run: bool,
        orphan_chunk_ids: List[int],
        deleted_count: int,
        vec_estimate: int,
        fts_estimate: int
    ) -> OrphanCleanupResult:
        """Build the cleanup result object"""
        found = len(orphan_chunk_ids)

        if dry_run:
            if found > 0:
                message = f"Would delete {found} orphan chunks"
            else:
                message = "No orphan chunks found"
        else:
            if deleted_count > 0:
                message = f"Deleted {deleted_count} orphan chunks"
            else:
                message = "No orphan chunks to delete"

        # Add note about vec_chunks/fts_chunks if estimates > 0
        notes = []
        if vec_estimate > 0:
            notes.append(f"{vec_estimate} orphan vec_chunks (requires HNSW rebuild)")
        if fts_estimate > 0:
            notes.append(f"{fts_estimate} orphan fts_chunks (estimated)")

        if notes:
            message += ". Also found: " + ", ".join(notes)

        return OrphanCleanupResult(
            dry_run=dry_run,
            orphan_chunks_found=found,
            orphan_chunks_deleted=deleted_count,
            orphan_vec_chunks_estimate=vec_estimate,
            orphan_fts_chunks_estimate=fts_estimate,
            message=message
        )
