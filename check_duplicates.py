#!/usr/bin/env python3
"""Check for duplicate chunks in the database"""

import sqlite3
from collections import defaultdict

def check_duplicates():
    conn = sqlite3.connect('/app/data/rag.db')
    cursor = conn.cursor()

    print("=" * 60)
    print("DATABASE SANITY CHECK - Duplicate Chunks Analysis")
    print("=" * 60)
    print()

    # Get total stats
    cursor.execute("SELECT COUNT(*) FROM chunks")
    total_chunks = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM documents")
    total_docs = cursor.fetchone()[0]

    print(f"Total documents: {total_docs}")
    print(f"Total chunks: {total_chunks}")
    print()

    # Check for exact duplicate chunks (same content across ALL documents)
    print("Checking for duplicate chunk content (same content in multiple documents)...")
    cursor.execute("""
        SELECT content, COUNT(*) as cnt, GROUP_CONCAT(document_id) as doc_ids
        FROM chunks
        GROUP BY content
        HAVING cnt > 1
        ORDER BY cnt DESC
        LIMIT 20
    """)

    global_duplicates = cursor.fetchall()
    if global_duplicates:
        print(f"❌ Found {len(global_duplicates)} chunks with duplicate content across documents:")
        print()
        for content, count, doc_ids in global_duplicates[:5]:
            content_preview = content[:100].replace('\n', ' ')
            print(f"  - Content: \"{content_preview}...\"")
            print(f"    Count: {count} chunks")
            print(f"    Document IDs: {doc_ids}")
            print()
    else:
        print("✅ No duplicate chunk content found across documents")
        print()

    # Check for duplicate chunks within same document (same document_id + same content)
    print("Checking for duplicate chunks within individual documents...")
    cursor.execute("""
        SELECT document_id, content, COUNT(*) as cnt
        FROM chunks
        GROUP BY document_id, content
        HAVING cnt > 1
    """)

    doc_duplicates = cursor.fetchall()
    if doc_duplicates:
        print(f"❌ Found {len(doc_duplicates)} duplicate chunks within documents:")

        # Get file paths for these documents
        doc_ids = list(set([d[0] for d in doc_duplicates]))
        for doc_id in doc_ids[:10]:  # Show first 10
            cursor.execute("SELECT file_path FROM documents WHERE id = ?", (doc_id,))
            result = cursor.fetchone()
            if result:
                file_path = result[0]
                # Count duplicates for this doc
                dup_count = sum(1 for d in doc_duplicates if d[0] == doc_id)
                print(f"  - Document {doc_id}: {file_path}")
                print(f"    {dup_count} duplicate chunk(s)")
    else:
        print("✅ No duplicate chunks found within individual documents")
        print()

    # Check for chunks with same document_id + page + chunk_index (structural duplicates)
    print("Checking for structural duplicates (same document + page + index)...")
    cursor.execute("""
        SELECT document_id, page, chunk_index, COUNT(*) as cnt
        FROM chunks
        WHERE page IS NOT NULL AND chunk_index IS NOT NULL
        GROUP BY document_id, page, chunk_index
        HAVING cnt > 1
    """)

    structural_duplicates = cursor.fetchall()
    if structural_duplicates:
        print(f"❌ Found {len(structural_duplicates)} structural duplicates:")
        for doc_id, page, chunk_idx, count in structural_duplicates[:10]:
            cursor.execute("SELECT file_path FROM documents WHERE id = ?", (doc_id,))
            result = cursor.fetchone()
            if result:
                print(f"  - {result[0]}")
                print(f"    Page {page}, Index {chunk_idx}: {count} chunks")
    else:
        print("✅ No structural duplicates found")
        print()

    # Summary
    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)

    total_duplicate_issues = len(global_duplicates) + len(doc_duplicates) + len(structural_duplicates)

    if total_duplicate_issues == 0:
        print("✅ Database is CLEAN - No duplicate chunks detected")
        print("   Safe to proceed with E2E testing")
    else:
        print(f"⚠️  Found {total_duplicate_issues} duplicate issues:")
        if global_duplicates:
            print(f"   - {len(global_duplicates)} chunks duplicated across documents")
        if doc_duplicates:
            print(f"   - {len(doc_duplicates)} chunks duplicated within documents")
        if structural_duplicates:
            print(f"   - {len(structural_duplicates)} structural duplicates")
        print()
        print("   Recommend cleanup before E2E testing")

    print()

    conn.close()

    return total_duplicate_issues

if __name__ == "__main__":
    duplicate_count = check_duplicates()
    exit(0 if duplicate_count == 0 else 1)
