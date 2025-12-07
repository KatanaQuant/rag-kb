"""FTS index rebuilding service

Rebuilds the FTS5 full-text search index from existing chunk content.
Use when fts_chunks is out of sync with chunks table or has orphan entries.

Merged from:
- scripts/rebuild_fts.py - batch processing with progress reporting
- scripts/rebuild_fts_inline.py - explicit rowid mapping for JOIN compatibility
"""
import sqlite3
import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class FtsRebuildResult:
    """Result of FTS rebuild operation"""
    dry_run: bool
    chunks_found: int
    chunks_indexed: int
    fts_entries_before: int
    fts_entries_after: int
    time_taken: float
    message: str
    errors: Optional[list] = None


class FtsRebuilder:
    """FTS index rebuilder with injectable db_path

    Rebuilds the fts_chunks FTS5 virtual table from the chunks table.
    Critical: Sets rowid = chunk_id for JOIN compatibility with hybrid_search.

    Example:
        rebuilder = FtsRebuilder(db_path="/app/data/rag.db")
        result = rebuilder.rebuild(dry_run=True)
        if result.chunks_found > 0:
            result = rebuilder.rebuild(dry_run=False)
    """

    # FTS5 table schema - contentless with explicit rowid (SQLite 3.45.0+)
    FTS_SCHEMA_FULL = """
        CREATE VIRTUAL TABLE fts_chunks USING fts5(
            chunk_id UNINDEXED,
            content,
            content='',
            contentless_delete=1
        )
    """

    # Fallback schema for older SQLite versions
    FTS_SCHEMA_SIMPLE = """
        CREATE VIRTUAL TABLE fts_chunks USING fts5(
            chunk_id UNINDEXED,
            content
        )
    """

    def __init__(self, db_path: str, batch_size: int = 1000):
        """Initialize rebuilder with database path

        Args:
            db_path: Path to SQLite database file
            batch_size: Number of chunks to process per batch (default 1000)
        """
        self.db_path = db_path
        self.batch_size = batch_size

    def rebuild(self, dry_run: bool = False) -> FtsRebuildResult:
        """Rebuild FTS index from chunks table

        Args:
            dry_run: If True, report what would happen without modifying data

        Returns:
            FtsRebuildResult with operation statistics
        """
        start_time = time.time()
        errors = []

        conn = sqlite3.connect(self.db_path)

        # Get current counts
        chunks_found = self._count_chunks(conn)
        fts_entries_before = self._count_fts_entries(conn)

        # Handle empty database
        if chunks_found == 0:
            conn.close()
            return FtsRebuildResult(
                dry_run=dry_run,
                chunks_found=0,
                chunks_indexed=0,
                fts_entries_before=fts_entries_before,
                fts_entries_after=0 if not dry_run else fts_entries_before,
                time_taken=time.time() - start_time,
                message="No chunks found - database is empty"
            )

        # Dry run - just report stats
        if dry_run:
            conn.close()
            return FtsRebuildResult(
                dry_run=True,
                chunks_found=chunks_found,
                chunks_indexed=0,
                fts_entries_before=fts_entries_before,
                fts_entries_after=fts_entries_before,
                time_taken=time.time() - start_time,
                message=f"Would rebuild FTS index with {chunks_found} chunks"
            )

        # Drop and recreate FTS table
        conn.execute("DROP TABLE IF EXISTS fts_chunks")
        conn.commit()
        self._create_fts_table(conn)
        conn.commit()

        # Rebuild from chunks in batches
        chunks_indexed = self._populate_fts_batched(conn, errors)

        # Force WAL checkpoint for durability
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.commit()

        # Get final count
        fts_entries_after = self._count_fts_entries(conn)
        conn.close()

        elapsed = time.time() - start_time

        return FtsRebuildResult(
            dry_run=False,
            chunks_found=chunks_found,
            chunks_indexed=chunks_indexed,
            fts_entries_before=fts_entries_before,
            fts_entries_after=fts_entries_after,
            time_taken=elapsed,
            message=f"Rebuilt FTS index: {chunks_indexed} chunks indexed in {elapsed:.1f}s",
            errors=errors if errors else None
        )

    def _create_fts_table(self, conn: sqlite3.Connection) -> None:
        """Create FTS5 table with SQLite version compatibility

        Tries full contentless schema first (SQLite 3.45.0+), falls back
        to simple schema for older versions.
        """
        try:
            conn.execute(self.FTS_SCHEMA_FULL)
        except sqlite3.OperationalError:
            # Fallback for older SQLite versions
            conn.execute(self.FTS_SCHEMA_SIMPLE)

    def _count_chunks(self, conn: sqlite3.Connection) -> int:
        """Get total chunk count"""
        cursor = conn.execute("SELECT COUNT(*) FROM chunks")
        return cursor.fetchone()[0]

    def _count_fts_entries(self, conn: sqlite3.Connection) -> int:
        """Get current FTS entry count"""
        try:
            cursor = conn.execute("SELECT COUNT(*) FROM fts_chunks")
            return cursor.fetchone()[0]
        except sqlite3.OperationalError:
            # Table doesn't exist
            return 0

    def _populate_fts_batched(self, conn: sqlite3.Connection, errors: list) -> int:
        """Populate FTS table from chunks in batches

        Uses executemany for efficiency. Critical: rowid must equal chunk_id
        for JOIN compatibility with hybrid_search.

        Args:
            conn: Database connection
            errors: List to append error messages to

        Returns:
            Number of chunks successfully indexed
        """
        total_indexed = 0
        offset = 0

        while True:
            cursor = conn.execute(
                "SELECT id, content FROM chunks ORDER BY id LIMIT ? OFFSET ?",
                (self.batch_size, offset)
            )
            batch = cursor.fetchall()

            if not batch:
                break

            try:
                # Build batch data: (rowid, chunk_id, content)
                # rowid = chunk_id is critical for JOIN in hybrid_search
                batch_data = [(chunk_id, chunk_id, content) for chunk_id, content in batch]

                conn.executemany(
                    "INSERT INTO fts_chunks (rowid, chunk_id, content) VALUES (?, ?, ?)",
                    batch_data
                )
                conn.commit()
                total_indexed += len(batch)

            except Exception as e:
                errors.append(f"Batch at offset {offset}: {e}")

            offset += self.batch_size

        return total_indexed
