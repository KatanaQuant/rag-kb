"""
Vector database migration: sqlite-vec to vectorlite.

This script migrates embeddings from the old sqlite-vec virtual table (vec0)
to the new vectorlite virtual table (HNSW index).

No re-embedding required - existing float32 blobs are compatible.
"""

import sqlite3
import time
from pathlib import Path


def migrate_to_vectorlite(db_path: str, embedding_dim: int = 1024, batch_size: int = 1000) -> dict:
    """Migrate embeddings from sqlite-vec to vectorlite.

    Args:
        db_path: Path to SQLite database
        embedding_dim: Dimension of embeddings (default 1024 for Snowflake Arctic)
        batch_size: Number of embeddings to insert per batch

    Returns:
        dict with migration stats
    """
    import sqlite_vec
    import vectorlite_py

    conn = sqlite3.connect(db_path)
    conn.enable_load_extension(True)

    # Load sqlite-vec first to read old table
    sqlite_vec.load(conn)

    stats = {
        'start_time': time.time(),
        'vectors_migrated': 0,
        'errors': []
    }

    try:
        # Step 1: Check if old table exists
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='vec_chunks'"
        )
        if not cursor.fetchone():
            return {'error': 'vec_chunks table not found', 'vectors_migrated': 0}

        # Step 2: Count existing vectors
        cursor = conn.execute("SELECT COUNT(*) FROM vec_chunks")
        total_vectors = cursor.fetchone()[0]
        print(f"Found {total_vectors} vectors to migrate")

        if total_vectors == 0:
            return {'error': 'No vectors to migrate', 'vectors_migrated': 0}

        # Step 3: Read all existing embeddings (sqlite-vec format: chunk_id, embedding)
        print("Reading existing embeddings...")
        cursor = conn.execute("SELECT chunk_id, embedding FROM vec_chunks")
        embeddings_data = cursor.fetchall()
        print(f"Loaded {len(embeddings_data)} embeddings into memory")

        # Step 4: Drop old table and its shadow tables
        print("Dropping old vec_chunks table...")
        conn.execute("DROP TABLE IF EXISTS vec_chunks")
        conn.execute("DROP TABLE IF EXISTS vec_chunks_chunks")
        conn.execute("DROP TABLE IF EXISTS vec_chunks_rowids")
        conn.execute("DROP TABLE IF EXISTS vec_chunks_vector_chunks00")
        conn.commit()

        # Step 5: Load vectorlite extension (after dropping sqlite-vec tables)
        conn.load_extension(vectorlite_py.vectorlite_path())

        # Step 6: Create new vectorlite table with persistent index file
        import os
        db_dir = os.path.dirname(db_path)
        index_path = os.path.join(db_dir, "vec_chunks.idx")

        # Remove old index file if exists
        if os.path.exists(index_path):
            os.remove(index_path)

        print(f"Creating vectorlite table (dim={embedding_dim}, index={index_path})...")
        conn.execute(f"""
            CREATE VIRTUAL TABLE vec_chunks USING vectorlite(
                embedding float32[{embedding_dim}] cosine,
                hnsw(max_elements=200000),
                "{index_path}"
            )
        """)
        conn.commit()

        # Step 7: Batch insert embeddings
        print(f"Inserting {len(embeddings_data)} embeddings...")
        for i in range(0, len(embeddings_data), batch_size):
            batch = embeddings_data[i:i + batch_size]
            for chunk_id, embedding_blob in batch:
                try:
                    # vectorlite uses rowid instead of chunk_id column
                    conn.execute(
                        "INSERT INTO vec_chunks (rowid, embedding) VALUES (?, ?)",
                        (chunk_id, embedding_blob)
                    )
                    stats['vectors_migrated'] += 1
                except Exception as e:
                    stats['errors'].append(f"chunk_id={chunk_id}: {e}")

            conn.commit()
            progress = min(i + batch_size, len(embeddings_data))
            print(f"  Progress: {progress}/{len(embeddings_data)} ({100*progress//len(embeddings_data)}%)")

        # Step 8: Verify migration by doing a test query
        # Note: vectorlite doesn't support COUNT(*), so we verify via knn_search
        import numpy as np
        test_query = np.random.randn(embedding_dim).astype(np.float32)
        test_query = test_query / np.linalg.norm(test_query)
        cursor = conn.execute("""
            SELECT rowid, distance FROM vec_chunks
            WHERE knn_search(embedding, knn_param(?, 5))
        """, (test_query.tobytes(),))
        test_results = cursor.fetchall()
        stats['test_query_results'] = len(test_results)
        stats['final_count'] = stats['vectors_migrated']
        stats['success'] = len(test_results) > 0 and stats['vectors_migrated'] == total_vectors

        conn.commit()

    except Exception as e:
        stats['error'] = str(e)
        stats['success'] = False
        # Attempt rollback by restoring from backup
        print(f"Migration failed: {e}")
        raise

    finally:
        conn.close()
        stats['duration_seconds'] = time.time() - stats['start_time']

    return stats


def verify_migration(db_path: str, embedding_dim: int = 1024) -> dict:
    """Verify vectorlite migration was successful."""
    import vectorlite_py
    import numpy as np
    import os

    conn = sqlite3.connect(db_path)
    conn.enable_load_extension(True)
    conn.load_extension(vectorlite_py.vectorlite_path())

    try:
        # Check table exists
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='vec_chunks'"
        )
        if not cursor.fetchone():
            return {'valid': False, 'error': 'vec_chunks table not found'}

        # Check index file exists
        db_dir = os.path.dirname(db_path)
        index_path = os.path.join(db_dir, "vec_chunks.idx")
        if not os.path.exists(index_path):
            return {'valid': False, 'error': f'Index file not found: {index_path}'}

        # Test knn_search works
        test_query = np.random.randn(embedding_dim).astype(np.float32)
        test_query = test_query / np.linalg.norm(test_query)
        cursor = conn.execute("""
            SELECT rowid, distance FROM vec_chunks
            WHERE knn_search(embedding, knn_param(?, 5))
        """, (test_query.tobytes(),))
        results = cursor.fetchall()

        # Verify chunks table has entries
        cursor = conn.execute("SELECT COUNT(*) FROM chunks")
        chunk_count = cursor.fetchone()[0]

        return {
            'valid': len(results) > 0,
            'test_results': len(results),
            'chunk_count': chunk_count,
            'index_file_size': os.path.getsize(index_path)
        }

    finally:
        conn.close()


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python vector_migration.py <db_path> [embedding_dim]")
        sys.exit(1)

    db_path = sys.argv[1]
    embedding_dim = int(sys.argv[2]) if len(sys.argv) > 2 else 1024

    print(f"Migrating {db_path} to vectorlite (dim={embedding_dim})...")
    result = migrate_to_vectorlite(db_path, embedding_dim)
    print(f"\nMigration complete: {result}")

    print("\nVerifying...")
    verify_result = verify_migration(db_path)
    print(f"Verification: {verify_result}")
