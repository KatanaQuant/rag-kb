#!/usr/bin/env python3
"""
Cleanup orphan data from the RAG database.

This script removes:
1. Orphan chunks - chunks referencing non-existent documents
2. Orphan vec_chunks - HNSW entries for deleted chunks
3. Orphan fts_chunks - FTS entries for deleted chunks

Usage:
    # Dry run (show what would be deleted)
    python scripts/cleanup_orphans.py /app/data/rag.db

    # Actually delete
    python scripts/cleanup_orphans.py /app/data/rag.db --execute

    # Or via docker:
    docker exec rag-api python /app/scripts/cleanup_orphans.py /app/data/rag.db --execute
"""

import sqlite3
import sys
import argparse
from pathlib import Path


def find_orphan_chunks(conn: sqlite3.Connection) -> list[int]:
    """Find chunks that reference non-existent documents."""
    cursor = conn.execute("""
        SELECT c.id
        FROM chunks c
        LEFT JOIN documents d ON c.document_id = d.id
        WHERE d.id IS NULL
    """)
    return [row[0] for row in cursor.fetchall()]


def estimate_orphan_vec_chunks(conn: sqlite3.Connection) -> int:
    """Estimate orphan vec_chunks by comparing counts.

    vec_chunks uses rowid = chunk.id. We can't enumerate rowids directly
    (vectorlite limitation), but we can compare counts.

    Returns estimated orphan count (vec_chunks - chunks).
    """
    try:
        cursor = conn.execute("SELECT COUNT(*) FROM chunks")
        chunk_count = cursor.fetchone()[0]

        cursor = conn.execute("SELECT COUNT(*) FROM vec_chunks")
        vec_count = cursor.fetchone()[0]

        return max(0, vec_count - chunk_count)
    except Exception:
        return 0


def estimate_orphan_fts_chunks(conn: sqlite3.Connection) -> int:
    """Estimate orphan fts_chunks by comparing counts.

    FTS virtual tables don't support efficient LEFT JOINs,
    so we use count comparison as a proxy.

    Returns estimated orphan count (fts_chunks - chunks).
    """
    try:
        cursor = conn.execute("SELECT COUNT(*) FROM chunks")
        chunk_count = cursor.fetchone()[0]

        cursor = conn.execute("SELECT COUNT(*) FROM fts_chunks")
        fts_count = cursor.fetchone()[0]

        return max(0, fts_count - chunk_count)
    except Exception:
        return 0


def get_stats(conn: sqlite3.Connection) -> dict:
    """Get database statistics."""
    stats = {}

    cursor = conn.execute("SELECT COUNT(*) FROM documents")
    stats['documents'] = cursor.fetchone()[0]

    cursor = conn.execute("SELECT COUNT(*) FROM chunks")
    stats['chunks'] = cursor.fetchone()[0]

    try:
        cursor = conn.execute("SELECT COUNT(*) FROM vec_chunks")
        stats['vec_chunks'] = cursor.fetchone()[0]
    except sqlite3.OperationalError:
        stats['vec_chunks'] = "N/A (vectorlite)"

    cursor = conn.execute("SELECT COUNT(*) FROM fts_chunks")
    stats['fts_chunks'] = cursor.fetchone()[0]

    return stats


def cleanup_orphans(db_path: str, execute: bool = False) -> dict:
    """Find and optionally remove orphan data.

    Args:
        db_path: Path to SQLite database
        execute: If True, actually delete. If False, dry run only.

    Returns:
        dict with orphan counts and actions taken
    """
    conn = sqlite3.connect(db_path)

    # Load vectorlite for vec_chunks access
    try:
        import vectorlite_py
        conn.enable_load_extension(True)
        conn.load_extension(vectorlite_py.vectorlite_path())
    except Exception as e:
        print(f"Warning: Could not load vectorlite extension: {e}")
        print("vec_chunks cleanup may not work correctly.")

    print("=" * 60)
    print("ORPHAN CLEANUP SCRIPT")
    print("=" * 60)

    # Get initial stats
    print("\n[1/5] Getting database statistics...")
    stats_before = get_stats(conn)
    print(f"  Documents: {stats_before['documents']}")
    print(f"  Chunks: {stats_before['chunks']}")
    print(f"  vec_chunks: {stats_before['vec_chunks']}")
    print(f"  fts_chunks: {stats_before['fts_chunks']}")

    # Find orphans
    print("\n[2/5] Finding orphan chunks (invalid document_id)...")
    orphan_chunks = find_orphan_chunks(conn)
    print(f"  Found: {len(orphan_chunks)} orphan chunks")

    print("\n[3/5] Estimating orphan vec_chunks (count mismatch)...")
    orphan_vec_estimate = estimate_orphan_vec_chunks(conn)
    print(f"  Estimated: {orphan_vec_estimate} extra vec_chunks entries")
    if orphan_vec_estimate > 0:
        print("  Note: vec_chunks cleanup requires HNSW rebuild (use rebuild_embeddings.py)")

    print("\n[4/5] Estimating orphan fts_chunks (count mismatch)...")
    orphan_fts_estimate = estimate_orphan_fts_chunks(conn)
    print(f"  Estimated: {orphan_fts_estimate} extra fts_chunks entries")
    if orphan_fts_estimate > 0:
        print("  Note: fts_chunks cleanup requires FTS rebuild")

    result = {
        'orphan_chunks': len(orphan_chunks),
        'orphan_vec_chunks_estimate': orphan_vec_estimate,
        'orphan_fts_chunks_estimate': orphan_fts_estimate,
        'executed': execute,
        'stats_before': stats_before,
    }

    if not execute:
        print("\n[5/5] DRY RUN - No changes made")
        print("      Run with --execute to actually delete orphans")
        conn.close()
        return result

    # Execute cleanup
    print("\n[5/5] Executing cleanup...")

    if orphan_chunks:
        # First delete vec_chunks and fts_chunks for these chunks
        placeholders = ','.join('?' * len(orphan_chunks))
        try:
            conn.execute(
                f"DELETE FROM vec_chunks WHERE rowid IN ({placeholders})",
                orphan_chunks
            )
        except sqlite3.OperationalError as e:
            print(f"  Warning: Could not delete from vec_chunks: {e}")
        conn.execute(
            f"DELETE FROM fts_chunks WHERE chunk_id IN ({placeholders})",
            orphan_chunks
        )
        # Then delete the orphan chunks themselves
        conn.execute(
            f"DELETE FROM chunks WHERE id IN ({placeholders})",
            orphan_chunks
        )
        print(f"  Deleted {len(orphan_chunks)} orphan chunks (and their fts entries)")

    # Note: orphan vec_chunks can't be cleaned up directly due to vectorlite limitations
    # Use rebuild_embeddings.py for full HNSW index rebuild instead
    if orphan_vec_estimate > 0:
        print(f"  Skipped {orphan_vec_estimate} orphan vec_chunks (requires HNSW rebuild)")

    # Note: orphan fts_chunks can't be efficiently enumerated due to FTS limitations
    # The count mismatch is informational only
    if orphan_fts_estimate > 0:
        print(f"  Skipped {orphan_fts_estimate} orphan fts_chunks (requires FTS rebuild)")

    conn.commit()

    # Get final stats
    stats_after = get_stats(conn)
    result['stats_after'] = stats_after

    print("\n" + "=" * 60)
    print("CLEANUP COMPLETE")
    print("=" * 60)
    print(f"  Chunks: {stats_before['chunks']} -> {stats_after['chunks']}")
    print(f"  vec_chunks: {stats_before['vec_chunks']} -> {stats_after['vec_chunks']}")
    print(f"  fts_chunks: {stats_before['fts_chunks']} -> {stats_after['fts_chunks']}")

    conn.close()
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Cleanup orphan data from RAG database"
    )
    parser.add_argument(
        "db_path",
        help="Path to SQLite database"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually delete orphans (default is dry run)"
    )

    args = parser.parse_args()

    if not Path(args.db_path).exists():
        print(f"Error: Database not found: {args.db_path}")
        sys.exit(1)

    result = cleanup_orphans(args.db_path, execute=args.execute)

    # Exit with error if orphans found but not cleaned
    if not args.execute and (
        result['orphan_chunks'] > 0 or
        result['orphan_vec_chunks_estimate'] > 0 or
        result['orphan_fts_chunks_estimate'] > 0
    ):
        sys.exit(1)


if __name__ == "__main__":
    main()
