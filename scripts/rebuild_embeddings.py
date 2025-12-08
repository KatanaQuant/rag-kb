"""
DEPRECATED: Use POST /api/maintenance/rebuild-embeddings instead.

Rebuild vector embeddings from existing chunks.

Use this when the vectorlite HNSW index file is corrupted/missing
but the chunks table still has content.

Usage:
    python rebuild_embeddings.py /app/data/rag.db

This is MUCH faster than force-reindex because it skips:
- PDF extraction
- Chunking
- Security scanning
"""

import sqlite3
import time
import os
import sys


def rebuild_embeddings(db_path: str, batch_size: int = 32) -> dict:
    """Rebuild vector embeddings from existing chunks.

    Args:
        db_path: Path to SQLite database
        batch_size: Chunks to embed per batch

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

    # Get total chunks
    cursor = conn.execute("SELECT COUNT(*) FROM chunks")
    total_chunks = cursor.fetchone()[0]
    print(f"Total chunks to embed: {total_chunks}")

    if total_chunks == 0:
        return {'error': 'No chunks found', 'chunks_processed': 0}

    # Drop and recreate vec_chunks
    db_dir = os.path.dirname(db_path)
    index_path = os.path.join(db_dir, "vec_chunks.idx")

    print("Dropping old vec_chunks table...")
    conn.execute("DROP TABLE IF EXISTS vec_chunks")
    conn.commit()

    if os.path.exists(index_path):
        os.remove(index_path)
        print(f"Removed old index file: {index_path}")

    print(f"Creating new vec_chunks table (dim={embedding_dim})...")
    conn.execute(f"""
        CREATE VIRTUAL TABLE vec_chunks USING vectorlite(
            embedding float32[{embedding_dim}] cosine,
            hnsw(max_elements=200000),
            "{index_path}"
        )
    """)
    conn.commit()

    # Process chunks in batches
    print(f"Embedding {total_chunks} chunks in batches of {batch_size}...")

    offset = 0
    last_report = time.time()

    while offset < total_chunks:
        # Fetch batch
        cursor = conn.execute(
            "SELECT id, content FROM chunks ORDER BY id LIMIT ? OFFSET ?",
            (batch_size, offset)
        )
        batch = cursor.fetchall()

        if not batch:
            break

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
            stats['errors'].append(f"Batch at offset {offset}: {e}")
            print(f"Error at offset {offset}: {e}")

        offset += batch_size

        # Progress report every 10 seconds
        if time.time() - last_report > 10:
            elapsed = time.time() - stats['start_time']
            rate = stats['chunks_processed'] / elapsed
            remaining = (total_chunks - stats['chunks_processed']) / rate if rate > 0 else 0
            print(f"Progress: {stats['chunks_processed']}/{total_chunks} "
                  f"({100*stats['chunks_processed']/total_chunks:.1f}%) "
                  f"- ETA: {remaining:.0f}s")
            last_report = time.time()

    stats['elapsed_time'] = time.time() - stats['start_time']

    # Verify
    cursor = conn.execute("SELECT COUNT(*) FROM vec_chunks")
    stats['embeddings_created'] = cursor.fetchone()[0]

    print(f"\nDone! Created {stats['embeddings_created']} embeddings in {stats['elapsed_time']:.1f}s")

    if os.path.exists(index_path):
        print(f"Index file size: {os.path.getsize(index_path) / 1024 / 1024:.1f} MB")

    conn.close()
    return stats


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python rebuild_embeddings.py <db_path>")
        sys.exit(1)

    db_path = sys.argv[1]
    result = rebuild_embeddings(db_path)
    print(f"\nResult: {result}")
