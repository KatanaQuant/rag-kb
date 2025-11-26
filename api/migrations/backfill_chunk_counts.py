#!/usr/bin/env python3
"""
Migration: Backfill total_chunks for historical documents

Problem: Documents indexed before v1.1.0 have total_chunks=0 in processing_progress
but chunks_processed > 0, causing false "chunk_count_mismatch" in completeness checks.

Solution: Set total_chunks = chunks_processed for completed documents where
the actual chunk count in the chunks table matches chunks_processed.

Usage:
    # Dry run (see what would change)
    python migrations/backfill_chunk_counts.py --dry-run

    # Apply migration
    python migrations/backfill_chunk_counts.py

    # Via docker
    docker-compose exec rag-api python migrations/backfill_chunk_counts.py
"""
import sqlite3
import argparse
from pathlib import Path


def get_db_path() -> str:
    """Get database path from config or default"""
    try:
        from config import default_config
        return default_config.database.path
    except ImportError:
        return "/app/data/rag.db"


def backfill_chunk_counts(dry_run: bool = True) -> dict:
    """Backfill total_chunks AND chunks_processed for historical documents

    Args:
        dry_run: If True, only report what would change

    Returns:
        Summary dict with counts

    Historical context:
        Documents indexed before v1.1.0 have total_chunks=0 and chunks_processed
        was often set to 1 (as a completion flag) instead of actual count.
        The actual chunks ARE in the database, just the tracking was incomplete.

    Strategy:
        Use the ACTUAL chunk count from chunks table to set both
        total_chunks and chunks_processed for completed documents.
    """
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)

    # Find completed documents where total_chunks=0 but chunks exist in DB
    candidates = conn.execute("""
        SELECT
            pp.file_path,
            pp.chunks_processed as old_processed,
            d.id as document_id,
            (SELECT COUNT(*) FROM chunks c WHERE c.document_id = d.id) as actual_chunks
        FROM processing_progress pp
        JOIN documents d ON d.file_path = pp.file_path
        WHERE pp.total_chunks = 0
          AND pp.status = 'completed'
    """).fetchall()

    to_update = []
    zero_chunks = []

    for file_path, old_processed, doc_id, actual_chunks in candidates:
        if actual_chunks > 0:
            # Has chunks in DB - backfill with actual count
            to_update.append((file_path, actual_chunks))
        else:
            # No chunks in DB - these are true zero_chunks cases
            zero_chunks.append({
                'file_path': file_path,
                'document_id': doc_id
            })

    if dry_run:
        print(f"DRY RUN - Would update {len(to_update)} documents with actual chunk counts")
        print(f"Found {len(zero_chunks)} documents with zero chunks (legitimate or orphans)")
        if to_update[:5]:
            print("\nSample updates:")
            for fp, count in to_update[:5]:
                print(f"  {fp.split('/')[-1]}: will set total_chunks={count}, chunks_processed={count}")
    else:
        # Apply updates - set BOTH total_chunks and chunks_processed to actual count
        for file_path, actual_chunks in to_update:
            conn.execute("""
                UPDATE processing_progress
                SET total_chunks = ?, chunks_processed = ?
                WHERE file_path = ?
            """, (actual_chunks, actual_chunks, file_path))

        conn.commit()
        print(f"Updated {len(to_update)} documents with actual chunk counts")
        print(f"Skipped {len(zero_chunks)} documents with zero chunks")

    conn.close()

    return {
        'updated': len(to_update) if not dry_run else 0,
        'would_update': len(to_update),
        'zero_chunks': len(zero_chunks),
        'zero_chunk_details': zero_chunks[:10]
    }


def main():
    parser = argparse.ArgumentParser(
        description='Backfill total_chunks for historical documents'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would change without applying'
    )
    args = parser.parse_args()

    result = backfill_chunk_counts(dry_run=args.dry_run)

    if args.dry_run:
        print(f"\nRun without --dry-run to apply {result['would_update']} updates")


if __name__ == '__main__':
    main()
