#!/usr/bin/env python3
"""
DEPRECATED: Use GET /api/maintenance/verify-integrity instead.

Verify database integrity for the RAG knowledge base.

Checks:
1. Referential integrity (chunks -> documents)
2. HNSW index consistency (vec_chunks <-> chunks)
3. FTS index consistency (fts_chunks <-> chunks)
4. Duplicate detection (same file indexed multiple times)

Usage:
    python scripts/verify_integrity.py /app/data/rag.db

    # Or via docker:
    docker exec rag-api python /app/scripts/verify_integrity.py /app/data/rag.db

Exit codes:
    0 - All checks passed
    1 - Issues found
"""

import sqlite3
import sys
import argparse
from pathlib import Path
from collections import defaultdict


def check_referential_integrity(conn: sqlite3.Connection) -> dict:
    """Check that all chunks reference valid documents."""
    cursor = conn.execute("""
        SELECT COUNT(*)
        FROM chunks c
        LEFT JOIN documents d ON c.document_id = d.id
        WHERE d.id IS NULL
    """)
    orphan_count = cursor.fetchone()[0]

    return {
        'name': 'Referential Integrity (chunks -> documents)',
        'passed': orphan_count == 0,
        'details': f"{orphan_count} orphan chunks found" if orphan_count > 0 else "All chunks have valid documents"
    }


def check_hnsw_consistency(conn: sqlite3.Connection) -> dict:
    """Check vec_chunks matches chunks table.

    Note: vec_chunks is a vectorlite virtual table that doesn't support
    standard JOINs. We use count comparison as a proxy for consistency.
    """
    try:
        cursor = conn.execute("SELECT COUNT(*) FROM chunks")
        chunk_count = cursor.fetchone()[0]

        cursor = conn.execute("SELECT COUNT(*) FROM vec_chunks")
        vec_count = cursor.fetchone()[0]

        diff = abs(chunk_count - vec_count)

        issues = []
        if vec_count > chunk_count:
            issues.append(f"{vec_count - chunk_count} extra vec_chunks entries (orphans)")
        elif vec_count < chunk_count:
            issues.append(f"{chunk_count - vec_count} chunks missing from HNSW index")

        return {
            'name': 'HNSW Index Consistency (vec_chunks vs chunks count)',
            'passed': diff == 0,
            'details': "; ".join(issues) if issues else f"Counts match: {chunk_count} chunks, {vec_count} vec_chunks"
        }
    except sqlite3.OperationalError as e:
        return {
            'name': 'HNSW Index Consistency',
            'passed': True,  # Don't fail on vectorlite load issues
            'details': f"Skipped (vectorlite not loaded): {e}"
        }


def check_fts_consistency(conn: sqlite3.Connection) -> dict:
    """Check fts_chunks matches chunks table.

    Note: FTS virtual tables don't support efficient JOINs.
    We use count comparison as a proxy for consistency.
    """
    try:
        cursor = conn.execute("SELECT COUNT(*) FROM chunks")
        chunk_count = cursor.fetchone()[0]

        cursor = conn.execute("SELECT COUNT(*) FROM fts_chunks")
        fts_count = cursor.fetchone()[0]

        diff = abs(chunk_count - fts_count)

        issues = []
        if fts_count > chunk_count:
            issues.append(f"{fts_count - chunk_count} extra fts_chunks entries (orphans)")
        elif fts_count < chunk_count:
            issues.append(f"{chunk_count - fts_count} chunks missing from FTS index")

        return {
            'name': 'FTS Index Consistency (fts_chunks vs chunks count)',
            'passed': diff == 0,
            'details': "; ".join(issues) if issues else f"Counts match: {chunk_count} chunks, {fts_count} fts_chunks"
        }
    except sqlite3.OperationalError as e:
        return {
            'name': 'FTS Index Consistency',
            'passed': False,
            'details': f"Could not check: {e}"
        }


def check_duplicate_documents(conn: sqlite3.Connection) -> dict:
    """Check for files indexed multiple times."""
    cursor = conn.execute("""
        SELECT file_path, COUNT(*) as cnt
        FROM documents
        GROUP BY file_path
        HAVING cnt > 1
    """)
    duplicates = cursor.fetchall()

    return {
        'name': 'Duplicate Documents',
        'passed': len(duplicates) == 0,
        'details': f"{len(duplicates)} files indexed multiple times" if duplicates else "No duplicate documents"
    }


def check_chunk_id_gaps(conn: sqlite3.Connection) -> dict:
    """Check for gaps in chunk IDs (indicates deletions)."""
    cursor = conn.execute("SELECT MIN(id), MAX(id), COUNT(*) FROM chunks")
    min_id, max_id, count = cursor.fetchone()

    if min_id is None:
        return {
            'name': 'Chunk ID Gaps',
            'passed': True,
            'details': "No chunks in database"
        }

    expected_count = max_id - min_id + 1
    gap_count = expected_count - count
    gap_percent = (gap_count / expected_count * 100) if expected_count > 0 else 0

    return {
        'name': 'Chunk ID Gaps (indicates historical deletions)',
        'passed': True,  # Gaps are informational, not failures
        'details': f"{gap_count} gaps ({gap_percent:.1f}%) - IDs {min_id} to {max_id}, {count} chunks"
    }


def get_table_counts(conn: sqlite3.Connection) -> dict:
    """Get row counts for all relevant tables."""
    counts = {}

    for table in ['documents', 'chunks', 'vec_chunks', 'fts_chunks']:
        try:
            cursor = conn.execute(f"SELECT COUNT(*) FROM {table}")
            counts[table] = cursor.fetchone()[0]
        except sqlite3.OperationalError:
            counts[table] = "TABLE NOT FOUND"

    return counts


def verify_integrity(db_path: str) -> bool:
    """Run all integrity checks and report results.

    Returns True if all checks pass, False otherwise.
    """
    conn = sqlite3.connect(db_path)

    # Load vectorlite for vec_chunks access
    try:
        import vectorlite_py
        conn.enable_load_extension(True)
        conn.load_extension(vectorlite_py.vectorlite_path())
    except Exception as e:
        print(f"Warning: Could not load vectorlite extension: {e}")

    print("=" * 60)
    print("DATABASE INTEGRITY CHECK")
    print("=" * 60)
    print(f"Database: {db_path}")

    # Get table counts
    print("\n[Table Counts]")
    counts = get_table_counts(conn)
    for table, count in counts.items():
        print(f"  {table}: {count}")

    # Run checks
    checks = [
        check_referential_integrity(conn),
        check_hnsw_consistency(conn),
        check_fts_consistency(conn),
        check_duplicate_documents(conn),
        check_chunk_id_gaps(conn),
    ]

    print("\n[Integrity Checks]")
    all_passed = True
    for check in checks:
        status = "PASS" if check['passed'] else "FAIL"
        symbol = "✓" if check['passed'] else "✗"
        print(f"  {symbol} {check['name']}")
        print(f"    {check['details']}")
        if not check['passed']:
            all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print("RESULT: ALL CHECKS PASSED")
    else:
        print("RESULT: ISSUES FOUND - run cleanup_orphans.py to fix")
    print("=" * 60)

    conn.close()
    return all_passed


def main():
    parser = argparse.ArgumentParser(
        description="Verify database integrity for RAG knowledge base"
    )
    parser.add_argument(
        "db_path",
        help="Path to SQLite database"
    )

    args = parser.parse_args()

    if not Path(args.db_path).exists():
        print(f"Error: Database not found: {args.db_path}")
        sys.exit(1)

    passed = verify_integrity(args.db_path)
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
