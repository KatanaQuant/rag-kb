#!/usr/bin/env python3
"""
Rebuild FTS (Full-Text Search) index from existing chunks.

Use this when fts_chunks has orphan entries or is out of sync with chunks table.

Usage:
    python scripts/rebuild_fts.py /app/data/rag.db

    # Or via docker:
    docker exec rag-api python /app/scripts/rebuild_fts.py /app/data/rag.db
"""

import sqlite3
import time
import sys
from pathlib import Path


def rebuild_fts(db_path: str, batch_size: int = 1000) -> dict:
    """Rebuild FTS index from existing chunks.

    Args:
        db_path: Path to SQLite database
        batch_size: Chunks to process per batch

    Returns:
        dict with rebuild stats
    """
    stats = {
        'start_time': time.time(),
        'chunks_processed': 0,
        'errors': []
    }

    conn = sqlite3.connect(db_path)

    # Get counts before
    cursor = conn.execute("SELECT COUNT(*) FROM chunks")
    total_chunks = cursor.fetchone()[0]

    cursor = conn.execute("SELECT COUNT(*) FROM fts_chunks")
    fts_before = cursor.fetchone()[0]

    print(f"Chunks: {total_chunks}")
    print(f"FTS entries before: {fts_before}")

    if total_chunks == 0:
        print("No chunks found. Nothing to do.")
        conn.close()
        return {'error': 'No chunks', 'chunks_processed': 0}

    # Drop and recreate fts_chunks
    print("\nDropping old fts_chunks table...")
    conn.execute("DROP TABLE IF EXISTS fts_chunks")
    conn.commit()

    print("Creating new fts_chunks FTS5 table...")
    conn.execute("""
        CREATE VIRTUAL TABLE fts_chunks USING fts5(
            chunk_id UNINDEXED,
            content,
            content='',
            contentless_delete=1
        )
    """)
    conn.commit()

    # Rebuild from chunks
    print(f"Rebuilding FTS index from {total_chunks} chunks...")

    offset = 0
    last_report = time.time()

    while offset < total_chunks:
        cursor = conn.execute(
            "SELECT id, content FROM chunks ORDER BY id LIMIT ? OFFSET ?",
            (batch_size, offset)
        )
        batch = cursor.fetchall()

        if not batch:
            break

        try:
            for chunk_id, content in batch:
                conn.execute(
                    "INSERT INTO fts_chunks (chunk_id, content) VALUES (?, ?)",
                    (chunk_id, content)
                )
            conn.commit()
            stats['chunks_processed'] += len(batch)
        except Exception as e:
            stats['errors'].append(f"Batch at offset {offset}: {e}")
            print(f"Error at offset {offset}: {e}")

        offset += batch_size

        # Progress report every 5 seconds
        if time.time() - last_report > 5:
            elapsed = time.time() - stats['start_time']
            rate = stats['chunks_processed'] / elapsed
            remaining = (total_chunks - stats['chunks_processed']) / rate if rate > 0 else 0
            print(f"Progress: {stats['chunks_processed']}/{total_chunks} "
                  f"({100*stats['chunks_processed']/total_chunks:.1f}%) "
                  f"- ETA: {remaining:.0f}s")
            last_report = time.time()

    stats['elapsed_time'] = time.time() - stats['start_time']

    # Verify
    cursor = conn.execute("SELECT COUNT(*) FROM fts_chunks")
    fts_after = cursor.fetchone()[0]
    stats['fts_entries_created'] = fts_after

    print(f"\nDone! Rebuilt FTS index with {fts_after} entries in {stats['elapsed_time']:.1f}s")
    print(f"FTS entries: {fts_before} -> {fts_after}")

    conn.close()
    return stats


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python rebuild_fts.py <db_path>")
        sys.exit(1)

    db_path = sys.argv[1]

    if not Path(db_path).exists():
        print(f"Error: Database not found: {db_path}")
        sys.exit(1)

    result = rebuild_fts(db_path)
    print(f"\nResult: {result}")
