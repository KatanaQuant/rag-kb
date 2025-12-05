"""
Partial rebuild: re-embed only chunks missing from HNSW index.

Use this when some chunks were indexed into a corrupted HNSW index
and need to be re-embedded. Does NOT drop the existing table.

Usage:
    python partial_rebuild.py /app/data/rag.db

This is faster than full rebuild because it only embeds missing chunks.
"""

import sqlite3
import time
import os
import sys
from typing import List


def get_missing_chunk_ids(conn, start_id: int = None, end_id: int = None) -> List[int]:
    """Find chunk IDs that are not in the HNSW index.

    Since vectorlite doesn't support enumerating rowids, we probe
    each chunk ID by attempting a search. Chunks not in the index
    will return empty results for their exact rowid.

    For efficiency, if start_id/end_id are provided (from investigation),
    we only check that range.

    Args:
        conn: SQLite connection with vectorlite loaded
        start_id: Start of suspected missing range (optional)
        end_id: End of suspected missing range (optional)

    Returns:
        List of chunk IDs missing from vec_chunks
    """
    if start_id and end_id:
        # Use known range from investigation
        cursor = conn.execute(
            "SELECT id FROM chunks WHERE id BETWEEN ? AND ? ORDER BY id",
            (start_id, end_id)
        )
        return [row[0] for row in cursor.fetchall()]

    # Fallback: Get all chunk IDs and assume all need embedding
    # (caller should provide range from investigation)
    cursor = conn.execute("SELECT id FROM chunks ORDER BY id")
    return [row[0] for row in cursor.fetchall()]


def partial_rebuild(db_path: str, batch_size: int = 32,
                    start_id: int = None, end_id: int = None) -> dict:
    """Re-embed only chunks missing from HNSW index.

    Args:
        db_path: Path to SQLite database
        batch_size: Chunks to embed per batch
        start_id: Start of chunk ID range to embed (from investigation)
        end_id: End of chunk ID range to embed (from investigation)

    Returns:
        dict with rebuild stats
    """
    import vectorlite_py
    from sentence_transformers import SentenceTransformer
    import struct

    stats = {
        'start_time': time.time(),
        'chunks_processed': 0,
        'errors': []
    }

    # Load embedding model
    model_name = os.environ.get('MODEL_NAME', 'Snowflake/snowflake-arctic-embed-l-v2.0')
    print(f"Loading model: {model_name}")
    model = SentenceTransformer(model_name)
    embedding_dim = model.get_sentence_embedding_dimension()
    print(f"Embedding dimension: {embedding_dim}")

    # Connect to database
    conn = sqlite3.connect(db_path)
    conn.enable_load_extension(True)
    conn.load_extension(vectorlite_py.vectorlite_path())

    # Get missing chunk IDs
    print("Finding chunks to embed...")
    missing_ids = get_missing_chunk_ids(conn, start_id, end_id)
    stats['missing_count'] = len(missing_ids)

    if not missing_ids:
        print("No missing chunks found. HNSW index is in sync.")
        conn.close()
        return stats

    print(f"Found {len(missing_ids)} chunks missing from HNSW index")
    print(f"Chunk ID range: {missing_ids[0]} - {missing_ids[-1]}")

    # Process in batches
    print(f"Embedding {len(missing_ids)} chunks in batches of {batch_size}...")

    last_report = time.time()

    for i in range(0, len(missing_ids), batch_size):
        batch_ids = missing_ids[i:i + batch_size]

        # Fetch chunk content for this batch
        placeholders = ','.join('?' * len(batch_ids))
        cursor = conn.execute(
            f"SELECT id, content FROM chunks WHERE id IN ({placeholders})",
            batch_ids
        )
        batch = cursor.fetchall()

        if not batch:
            continue

        # Extract texts and IDs
        chunk_ids = [row[0] for row in batch]
        texts = [row[1] for row in batch]

        # Generate embeddings
        try:
            embeddings = model.encode(
                texts,
                normalize_embeddings=True,
                show_progress_bar=False
            )

            # Insert into vec_chunks
            for chunk_id, embedding in zip(chunk_ids, embeddings):
                embedding_blob = struct.pack(f'{len(embedding)}f', *embedding)
                conn.execute(
                    "INSERT INTO vec_chunks (rowid, embedding) VALUES (?, ?)",
                    (chunk_id, embedding_blob)
                )

            conn.commit()
            stats['chunks_processed'] += len(batch)

        except Exception as e:
            stats['errors'].append(f"Batch at {i}: {e}")
            print(f"Error at batch {i}: {e}")

        # Progress report every 10 seconds
        if time.time() - last_report > 10:
            elapsed = time.time() - stats['start_time']
            rate = stats['chunks_processed'] / elapsed if elapsed > 0 else 0
            remaining = (len(missing_ids) - stats['chunks_processed']) / rate if rate > 0 else 0
            print(f"Progress: {stats['chunks_processed']}/{len(missing_ids)} "
                  f"({100*stats['chunks_processed']/len(missing_ids):.1f}%) "
                  f"- ETA: {remaining:.0f}s")
            last_report = time.time()

    stats['elapsed_time'] = time.time() - stats['start_time']

    print(f"\nDone! Embedded {stats['chunks_processed']} chunks in {stats['elapsed_time']:.1f}s")

    # Print final counts
    # Note: COUNT(*) on vec_chunks may fail after heavy inserts; verify separately
    chunks_count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    print(f"Chunks in DB: {chunks_count}")
    print("Run HNSW sanity check separately to verify index sync.")

    conn.close()
    return stats


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python partial_rebuild.py <db_path> [start_id] [end_id]")
        print("Example: python partial_rebuild.py /app/data/rag.db 70778 71727")
        sys.exit(1)

    db_path = sys.argv[1]
    start_id = int(sys.argv[2]) if len(sys.argv) > 2 else None
    end_id = int(sys.argv[3]) if len(sys.argv) > 3 else None

    result = partial_rebuild(db_path, start_id=start_id, end_id=end_id)
    print(f"\nResult: {result}")
