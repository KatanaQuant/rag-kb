"""
DEPRECATED: Use POST /api/maintenance/rebuild-hnsw instead.

Rebuild HNSW index from EXISTING embeddings (no re-embedding).

Use this to remove orphan embeddings from vec_chunks without
re-running the embedding model. Much faster than rebuild_embeddings.py.

What this does:
1. Copy valid embeddings (where rowid exists in chunks) to temp storage
2. Drop vec_chunks table and delete index file
3. Recreate vec_chunks table
4. Re-insert only valid embeddings

What this does NOT do:
- Re-run the embedding model (Arctic, etc.)
- Re-extract or re-chunk documents
- Touch the chunks or documents tables

Usage:
    docker exec rag-api python /app/scripts/rebuild_hnsw_index.py /app/data/rag.db

    # Dry run (show what would be done):
    docker exec rag-api python /app/scripts/rebuild_hnsw_index.py /app/data/rag.db --dry-run
"""

import sqlite3
import time
import os
import sys


def rebuild_hnsw_index(db_path: str, dry_run: bool = False) -> dict:
    """Rebuild HNSW index from existing valid embeddings.

    Args:
        db_path: Path to SQLite database
        dry_run: If True, only report what would be done

    Returns:
        dict with rebuild stats
    """
    import vectorlite_py

    stats = {
        'start_time': time.time(),
        'valid_embeddings': 0,
        'orphan_embeddings': 0,
        'total_embeddings': 0,
        'dry_run': dry_run
    }

    # Connect to database
    conn = sqlite3.connect(db_path)
    conn.enable_load_extension(True)
    conn.load_extension(vectorlite_py.vectorlite_path())

    # Get valid chunk IDs
    valid_ids = set(row[0] for row in conn.execute('SELECT id FROM chunks').fetchall())
    stats['total_chunks'] = len(valid_ids)

    # Vectorlite doesn't support COUNT(*) - use knn_search to enumerate rowids
    # Use zero vector to get all embeddings (distance doesn't matter for enumeration)
    embedding_dim = 1024  # Arctic embedding dimension
    zero_vec = b'\x00' * (embedding_dim * 4)

    print("Enumerating vec_chunks rowids via knn_search...")
    all_rowids = conn.execute('''
        SELECT v.rowid FROM vec_chunks v
        WHERE knn_search(v.embedding, knn_param(?, 200000))
    ''', (zero_vec,)).fetchall()
    all_rowids = set(row[0] for row in all_rowids)

    stats['total_embeddings'] = len(all_rowids)
    valid_rowids = all_rowids & valid_ids
    stats['valid_embeddings'] = len(valid_rowids)
    orphan_rowids = all_rowids - valid_ids
    stats['orphan_embeddings'] = len(orphan_rowids)

    print("=== HNSW Index Rebuild (Fast Mode) ===")
    print(f"Database: {db_path}")
    print(f"Total embeddings in vec_chunks: {stats['total_embeddings']:,}")
    print(f"Total chunks in chunks table: {stats['total_chunks']:,}")
    print(f"Valid embeddings (have matching chunk): {stats['valid_embeddings']:,}")
    print(f"Orphan embeddings (to remove): {stats['orphan_embeddings']:,}")

    if stats['orphan_embeddings'] == 0:
        print("\nNo orphans found - index is clean!")
        conn.close()
        return stats

    if dry_run:
        print(f"\n[DRY RUN] Would remove {stats['orphan_embeddings']:,} orphan embeddings")
        conn.close()
        return stats

    # Get embedding dimension from first valid embedding
    sample_rowid = next(iter(valid_rowids))
    sample = conn.execute(
        "SELECT embedding FROM vec_chunks WHERE rowid = ?", (sample_rowid,)
    ).fetchone()

    if not sample:
        print("ERROR: No valid embeddings found!")
        conn.close()
        return {'error': 'No valid embeddings'}

    embedding_blob = sample[0]
    embedding_dim = len(embedding_blob) // 4  # float32 = 4 bytes
    print(f"\nEmbedding dimension: {embedding_dim}")

    # Step 1: Extract valid embeddings to memory
    print(f"\nStep 1/4: Extracting {stats['valid_embeddings']:,} valid embeddings...")
    start = time.time()

    # Must extract one by one - vectorlite doesn't support bulk SELECT
    valid_embeddings = []
    sorted_rowids = sorted(valid_rowids)
    for i, rowid in enumerate(sorted_rowids):
        emb = conn.execute(
            "SELECT embedding FROM vec_chunks WHERE rowid = ?", (rowid,)
        ).fetchone()
        if emb:
            valid_embeddings.append((rowid, emb[0]))
        if (i + 1) % 10000 == 0:
            print(f"  Extracted {i + 1:,}/{len(sorted_rowids):,}...")

    print(f"  Extracted {len(valid_embeddings):,} embeddings in {time.time() - start:.1f}s")

    # Step 2: Drop vec_chunks and index file
    print("\nStep 2/4: Dropping old vec_chunks table...")
    db_dir = os.path.dirname(db_path)
    index_path = os.path.join(db_dir, "vec_chunks.idx")

    conn.execute("DROP TABLE IF EXISTS vec_chunks")
    conn.commit()

    if os.path.exists(index_path):
        os.remove(index_path)
        print(f"  Removed index file: {index_path}")

    # Step 3: Recreate vec_chunks
    print(f"\nStep 3/4: Creating new vec_chunks table (dim={embedding_dim})...")
    conn.execute(f"""
        CREATE VIRTUAL TABLE vec_chunks USING vectorlite(
            embedding float32[{embedding_dim}] cosine,
            hnsw(max_elements=200000),
            "{index_path}"
        )
    """)
    conn.commit()

    # Step 4: Re-insert valid embeddings
    print(f"\nStep 4/4: Inserting {len(valid_embeddings):,} valid embeddings...")
    start = time.time()
    batch_size = 1000
    inserted = 0

    for i in range(0, len(valid_embeddings), batch_size):
        batch = valid_embeddings[i:i + batch_size]
        for rowid, embedding in batch:
            conn.execute(
                "INSERT INTO vec_chunks (rowid, embedding) VALUES (?, ?)",
                (rowid, embedding)
            )
        conn.commit()
        inserted += len(batch)

        if inserted % 10000 == 0:
            print(f"  Progress: {inserted:,}/{len(valid_embeddings):,}")

    print(f"  Inserted in {time.time() - start:.1f}s")

    # Force HNSW to disk by closing connection
    conn.close()

    # Verify by counting via knn_search
    conn = sqlite3.connect(db_path)
    conn.enable_load_extension(True)
    conn.load_extension(vectorlite_py.vectorlite_path())

    # Enumerate to verify count
    verify_rowids = conn.execute('''
        SELECT v.rowid FROM vec_chunks v
        WHERE knn_search(v.embedding, knn_param(?, 200000))
    ''', (zero_vec,)).fetchall()
    final_count = len(verify_rowids)
    stats['final_embeddings'] = final_count
    stats['elapsed_time'] = time.time() - stats['start_time']

    print(f"\n=== Complete ===")
    print(f"Embeddings before: {stats['total_embeddings']:,}")
    print(f"Embeddings after: {final_count:,}")
    print(f"Orphans removed: {stats['orphan_embeddings']:,}")
    print(f"Time elapsed: {stats['elapsed_time']:.1f}s")

    if os.path.exists(index_path):
        size_mb = os.path.getsize(index_path) / 1024 / 1024
        print(f"Index file size: {size_mb:.1f} MB")

    conn.close()
    return stats


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python rebuild_hnsw_index.py <db_path> [--dry-run]")
        print("\nThis rebuilds the HNSW index from existing embeddings,")
        print("removing orphan entries without re-running the embedding model.")
        sys.exit(1)

    db_path = sys.argv[1]
    dry_run = '--dry-run' in sys.argv

    result = rebuild_hnsw_index(db_path, dry_run=dry_run)

    if 'error' in result:
        print(f"\nError: {result['error']}")
        sys.exit(1)
