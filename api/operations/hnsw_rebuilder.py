"""HNSW index rebuilding service

CRITICAL: This is the recovery mechanism for HNSW index corruption.

Rebuilds the HNSW index from existing embeddings without re-embedding.
Use this to recover from:
- HNSW write errors (index corruption)
- Orphan embeddings in vec_chunks (rowid doesn't exist in chunks)
- Index inconsistencies after interrupted operations

What this does:
1. Enumerate all embeddings in vec_chunks via knn_search
2. Identify valid embeddings (where rowid exists in chunks table)
3. Identify orphan embeddings (where rowid does NOT exist in chunks)
4. If not dry_run: recreate vec_chunks with only valid embeddings

What this does NOT do:
- Re-run the embedding model (Arctic, etc.)
- Re-extract or re-chunk documents
- Touch the chunks or documents tables

Extracted from scripts/rebuild_hnsw_index.py for API use.
"""
import sqlite3
import time
import os
from dataclasses import dataclass
from typing import Set, List, Tuple, Optional


@dataclass
class HnswRebuildResult:
    """Result of HNSW index rebuild operation"""
    total_embeddings: int
    valid_embeddings: int
    orphan_embeddings: int
    final_embeddings: int
    dry_run: bool
    elapsed_time: float
    total_chunks: int = 0
    error: Optional[str] = None


class HnswRebuilder:
    """HNSW index rebuilder with injectable db_path

    CRITICAL: This is the recovery mechanism for HNSW index corruption.

    Example:
        rebuilder = HnswRebuilder(db_path="/app/data/rag.db")
        result = rebuilder.rebuild(dry_run=True)  # Preview changes
        if result.orphan_embeddings > 0:
            result = rebuilder.rebuild(dry_run=False)  # Execute rebuild
    """

    EMBEDDING_DIM = 1024  # Arctic embedding dimension
    MAX_ELEMENTS = 200000  # HNSW max elements parameter

    def __init__(self, db_path: str):
        """Initialize rebuilder with database path

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path

    def rebuild(self, dry_run: bool = False) -> HnswRebuildResult:
        """Rebuild HNSW index from existing valid embeddings

        Args:
            dry_run: If True, only report what would be done without modifying

        Returns:
            HnswRebuildResult with rebuild statistics
        """
        start_time = time.time()

        conn = sqlite3.connect(self.db_path)

        # Try to load vectorlite
        if not self._try_load_vectorlite(conn):
            conn.close()
            return HnswRebuildResult(
                total_embeddings=0,
                valid_embeddings=0,
                orphan_embeddings=0,
                final_embeddings=0,
                dry_run=dry_run,
                elapsed_time=time.time() - start_time,
                error="Vectorlite extension not available"
            )

        # Get valid chunk IDs from chunks table
        valid_chunk_ids = self._get_valid_chunk_ids(conn)

        # Check if vec_chunks table exists
        if not self._vec_chunks_exists(conn):
            conn.close()
            return HnswRebuildResult(
                total_embeddings=0,
                valid_embeddings=0,
                orphan_embeddings=0,
                final_embeddings=0,
                total_chunks=len(valid_chunk_ids),
                dry_run=dry_run,
                elapsed_time=time.time() - start_time,
                error="vec_chunks table does not exist"
            )

        # Enumerate all embeddings in vec_chunks
        all_rowids = self._enumerate_vec_chunks(conn)

        # Calculate valid vs orphan
        valid_rowids = all_rowids & valid_chunk_ids
        orphan_rowids = all_rowids - valid_chunk_ids

        total_embeddings = len(all_rowids)
        valid_embeddings = len(valid_rowids)
        orphan_embeddings = len(orphan_rowids)

        # If no orphans, nothing to do
        if orphan_embeddings == 0:
            conn.close()
            return HnswRebuildResult(
                total_embeddings=total_embeddings,
                valid_embeddings=valid_embeddings,
                orphan_embeddings=0,
                final_embeddings=total_embeddings,
                total_chunks=len(valid_chunk_ids),
                dry_run=dry_run,
                elapsed_time=time.time() - start_time
            )

        # If dry_run, just report
        if dry_run:
            conn.close()
            return HnswRebuildResult(
                total_embeddings=total_embeddings,
                valid_embeddings=valid_embeddings,
                orphan_embeddings=orphan_embeddings,
                final_embeddings=total_embeddings,  # Unchanged in dry_run
                total_chunks=len(valid_chunk_ids),
                dry_run=dry_run,
                elapsed_time=time.time() - start_time
            )

        # Execute rebuild
        final_count = self._execute_rebuild(conn, valid_rowids)

        conn.close()

        return HnswRebuildResult(
            total_embeddings=total_embeddings,
            valid_embeddings=valid_embeddings,
            orphan_embeddings=orphan_embeddings,
            final_embeddings=final_count,
            total_chunks=len(valid_chunk_ids),
            dry_run=dry_run,
            elapsed_time=time.time() - start_time
        )

    def _try_load_vectorlite(self, conn: sqlite3.Connection) -> bool:
        """Attempt to load vectorlite extension

        Returns:
            True if vectorlite loaded successfully, False otherwise
        """
        try:
            import vectorlite_py
            conn.enable_load_extension(True)
            conn.load_extension(vectorlite_py.vectorlite_path())
            return True
        except Exception:
            return False

    def _get_valid_chunk_ids(self, conn: sqlite3.Connection) -> Set[int]:
        """Get all chunk IDs from chunks table"""
        cursor = conn.execute('SELECT id FROM chunks')
        return set(row[0] for row in cursor.fetchall())

    def _vec_chunks_exists(self, conn: sqlite3.Connection) -> bool:
        """Check if vec_chunks table exists"""
        try:
            conn.execute("SELECT 1 FROM vec_chunks LIMIT 1")
            return True
        except sqlite3.OperationalError:
            return False

    def _enumerate_vec_chunks(self, conn: sqlite3.Connection) -> Set[int]:
        """Enumerate all rowids in vec_chunks using knn_search

        Vectorlite doesn't support COUNT(*) or simple SELECT, so we use
        knn_search with a zero vector to enumerate all entries.
        """
        zero_vec = b'\x00' * (self.EMBEDDING_DIM * 4)  # float32 = 4 bytes

        try:
            cursor = conn.execute('''
                SELECT v.rowid FROM vec_chunks v
                WHERE knn_search(v.embedding, knn_param(?, ?))
            ''', (zero_vec, self.MAX_ELEMENTS))
            return set(row[0] for row in cursor.fetchall())
        except sqlite3.OperationalError:
            return set()

    def _execute_rebuild(self, conn: sqlite3.Connection, valid_rowids: Set[int]) -> int:
        """Execute the actual HNSW rebuild

        Steps:
        1. Extract valid embeddings to memory
        2. Drop vec_chunks table and index file
        3. Recreate vec_chunks table
        4. Re-insert valid embeddings

        Returns:
            Final count of embeddings after rebuild
        """
        # Step 1: Extract valid embeddings
        valid_embeddings = self._extract_embeddings(conn, valid_rowids)

        if not valid_embeddings:
            return 0

        # Determine embedding dimension from first embedding
        embedding_dim = len(valid_embeddings[0][1]) // 4  # float32 = 4 bytes

        # Step 2: Drop vec_chunks and index file
        db_dir = os.path.dirname(self.db_path)
        index_path = os.path.join(db_dir, "vec_chunks.idx")

        conn.execute("DROP TABLE IF EXISTS vec_chunks")
        conn.commit()

        if os.path.exists(index_path):
            os.remove(index_path)

        # Step 3: Recreate vec_chunks
        conn.execute(f"""
            CREATE VIRTUAL TABLE vec_chunks USING vectorlite(
                embedding float32[{embedding_dim}] cosine,
                hnsw(max_elements={self.MAX_ELEMENTS}),
                "{index_path}"
            )
        """)
        conn.commit()

        # Step 4: Re-insert valid embeddings
        self._insert_embeddings(conn, valid_embeddings)

        # Verify final count
        return self._verify_count(conn)

    def _extract_embeddings(self, conn: sqlite3.Connection,
                            valid_rowids: Set[int]) -> List[Tuple[int, bytes]]:
        """Extract embeddings for given rowids

        Vectorlite doesn't support bulk SELECT, so we extract one by one.
        """
        embeddings = []
        sorted_rowids = sorted(valid_rowids)

        for rowid in sorted_rowids:
            result = conn.execute(
                "SELECT embedding FROM vec_chunks WHERE rowid = ?",
                (rowid,)
            ).fetchone()
            if result:
                embeddings.append((rowid, result[0]))

        return embeddings

    def _insert_embeddings(self, conn: sqlite3.Connection,
                           embeddings: List[Tuple[int, bytes]]) -> None:
        """Insert embeddings into vec_chunks in batches"""
        batch_size = 1000

        for i in range(0, len(embeddings), batch_size):
            batch = embeddings[i:i + batch_size]
            for rowid, embedding in batch:
                conn.execute(
                    "INSERT INTO vec_chunks (rowid, embedding) VALUES (?, ?)",
                    (rowid, embedding)
                )
            conn.commit()

    def _verify_count(self, conn: sqlite3.Connection) -> int:
        """Verify final embedding count after rebuild

        Need to close and reopen connection to force HNSW to disk,
        then use knn_search to enumerate.
        """
        # Force sync
        conn.close()

        # Reopen and reload vectorlite
        conn = sqlite3.connect(self.db_path)
        self._try_load_vectorlite(conn)

        # Enumerate to verify
        final_rowids = self._enumerate_vec_chunks(conn)
        count = len(final_rowids)

        conn.close()
        return count
