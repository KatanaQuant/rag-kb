#!/usr/bin/env python3
"""Clean up duplicate chunks from the database"""

import sqlite3
from collections import defaultdict

def cleanup_duplicates():
    conn = sqlite3.connect('/app/data/rag.db')

    # Load sqlite-vec extension
    try:
        import sqlite_vec
        sqlite_vec.load(conn)
    except Exception as e:
        print(f"Warning: Could not load sqlite-vec: {e}")

    cursor = conn.cursor()

    print("=" * 60)
    print("DUPLICATE CHUNK CLEANUP")
    print("=" * 60)
    print()

    # Track deletions
    deleted_count = 0

    # Clean up duplicate chunks within same document (keep first occurrence)
    print("Cleaning up duplicate chunks within documents...")
    cursor.execute("""
        SELECT document_id, content, MIN(id) as keep_id, COUNT(*) as cnt
        FROM chunks
        GROUP BY document_id, content
        HAVING cnt > 1
    """)

    doc_duplicates = cursor.fetchall()

    if doc_duplicates:
        print(f"Found {len(doc_duplicates)} sets of duplicates within documents")

        for doc_id, content, keep_id, count in doc_duplicates:
            # Delete all chunks with same document_id + content EXCEPT the one with keep_id
            cursor.execute("""
                DELETE FROM chunks
                WHERE document_id = ? AND content = ? AND id != ?
            """, (doc_id, content, keep_id))

            deleted = count - 1  # We kept one
            deleted_count += deleted

            # Also clean up related vector and FTS entries
            # Note: These should cascade if foreign keys are set up correctly
            # But let's be explicit
            cursor.execute("""
                DELETE FROM vec_chunks
                WHERE chunk_id NOT IN (SELECT id FROM chunks)
            """)

            cursor.execute("""
                DELETE FROM fts_chunks
                WHERE chunk_id NOT IN (SELECT id FROM chunks)
            """)

        print(f"  ✓ Deleted {deleted_count} duplicate chunks within documents")
    else:
        print("  ✓ No duplicate chunks within documents")

    # Commit changes
    conn.commit()

    # Verify cleanup
    print()
    print("Verifying cleanup...")
    cursor.execute("""
        SELECT document_id, content, COUNT(*) as cnt
        FROM chunks
        GROUP BY document_id, content
        HAVING cnt > 1
    """)

    remaining = cursor.fetchall()
    if remaining:
        print(f"  ⚠️  Still {len(remaining)} duplicate sets remaining")
    else:
        print("  ✓ All duplicates within documents cleaned up")

    # Get final stats
    cursor.execute("SELECT COUNT(*) FROM chunks")
    final_chunks = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM documents")
    total_docs = cursor.fetchone()[0]

    print()
    print("=" * 60)
    print("CLEANUP SUMMARY")
    print("=" * 60)
    print(f"Documents: {total_docs}")
    print(f"Chunks after cleanup: {final_chunks}")
    print(f"Total chunks deleted: {deleted_count}")
    print()

    # Note about cross-document duplicates
    cursor.execute("""
        SELECT content, COUNT(DISTINCT document_id) as doc_count
        FROM chunks
        GROUP BY content
        HAVING doc_count > 1
        LIMIT 5
    """)

    cross_doc_dups = cursor.fetchall()
    if cross_doc_dups:
        print("NOTE: Cross-document duplicates detected but NOT removed")
        print("(Same content appearing in multiple documents may be intentional)")
        print()
        for content, doc_count in cross_doc_dups[:3]:
            content_preview = content[:80].replace('\n', ' ')
            print(f"  - \"{content_preview}...\" appears in {doc_count} documents")
        print()

    conn.close()

    return deleted_count

if __name__ == "__main__":
    deleted = cleanup_duplicates()
    print(f"✓ Cleanup complete - {deleted} duplicate chunks removed")
    exit(0)
