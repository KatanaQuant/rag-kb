"""Full embedding rebuild service

Rebuilds all vector embeddings from existing chunks - full re-embed operation.
Use this when the HNSW index is completely corrupted or embeddings need
to be regenerated (e.g., after model change).

This is a LONG-RUNNING operation that:
1. Loads the embedding model
2. Iterates through all chunks in batches
3. Generates new embeddings for each chunk
4. Drops and recreates vec_chunks table
5. Inserts all new embeddings

This is MUCH faster than force-reindex because it skips:
- PDF extraction
- Chunking
- Security scanning

Extracted from scripts/rebuild_embeddings.py for API use.
"""
import sqlite3
import time
import os
from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class EmbeddingRebuildResult:
    """Result of full embedding rebuild operation"""
    dry_run: bool
    documents_found: int
    chunks_found: int
    chunks_embedded: int
    embeddings_before: int
    embeddings_after: int
    time_taken: float
    message: str
    errors: List[str] = field(default_factory=list)
    model_name: Optional[str] = None
    embedding_dim: Optional[int] = None


class EmbeddingRebuilder:
    """Full embedding rebuilder with injectable db_path

    Regenerates all vector embeddings from chunk content using the
    configured embedding model. This is a long-running operation
    suitable for recovery from complete index corruption.

    Example:
        rebuilder = EmbeddingRebuilder(db_path="/app/data/rag.db")
        result = rebuilder.rebuild(dry_run=True)  # Preview
        if result.chunks_found > 0:
            result = rebuilder.rebuild(dry_run=False)  # Execute
    """

    MAX_ELEMENTS = 200000  # HNSW max elements parameter

    def __init__(self, db_path: str, batch_size: int = 32):
        """Initialize rebuilder with database path

        Args:
            db_path: Path to SQLite database file
            batch_size: Number of chunks to embed per batch (default 32)
        """
        self.db_path = db_path
        self.batch_size = batch_size

    def rebuild(self, dry_run: bool = False) -> EmbeddingRebuildResult:
        """Rebuild all embeddings from chunk content

        Args:
            dry_run: If True, report what would happen without modifying data

        Returns:
            EmbeddingRebuildResult with operation statistics
        """
        start_time = time.time()
        errors = []

        conn = sqlite3.connect(self.db_path)

        # Get current counts
        documents_found = self._count_documents(conn)
        chunks_found = self._count_chunks(conn)
        embeddings_before = self._count_embeddings(conn)

        # Handle empty database
        if chunks_found == 0:
            conn.close()
            return EmbeddingRebuildResult(
                dry_run=dry_run,
                documents_found=documents_found,
                chunks_found=0,
                chunks_embedded=0,
                embeddings_before=embeddings_before,
                embeddings_after=0 if not dry_run else embeddings_before,
                time_taken=time.time() - start_time,
                message="No chunks found - database is empty"
            )

        # Get model info for reporting
        model_name = os.environ.get('MODEL_NAME', 'Snowflake/snowflake-arctic-embed-l-v2.0')

        # Dry run - just report stats
        if dry_run:
            conn.close()
            return EmbeddingRebuildResult(
                dry_run=True,
                documents_found=documents_found,
                chunks_found=chunks_found,
                chunks_embedded=0,
                embeddings_before=embeddings_before,
                embeddings_after=embeddings_before,
                time_taken=time.time() - start_time,
                message=f"Would rebuild {chunks_found} embeddings from {documents_found} documents",
                model_name=model_name
            )

        # Load vectorlite
        if not self._try_load_vectorlite(conn):
            conn.close()
            return EmbeddingRebuildResult(
                dry_run=False,
                documents_found=documents_found,
                chunks_found=chunks_found,
                chunks_embedded=0,
                embeddings_before=embeddings_before,
                embeddings_after=embeddings_before,
                time_taken=time.time() - start_time,
                message="Failed to load vectorlite extension",
                errors=["Vectorlite extension not available"]
            )

        # Load embedding model
        model, embedding_dim = self._load_model(model_name)
        if model is None:
            conn.close()
            return EmbeddingRebuildResult(
                dry_run=False,
                documents_found=documents_found,
                chunks_found=chunks_found,
                chunks_embedded=0,
                embeddings_before=embeddings_before,
                embeddings_after=embeddings_before,
                time_taken=time.time() - start_time,
                message="Failed to load embedding model",
                errors=[f"Could not load model: {model_name}"],
                model_name=model_name
            )

        # Drop and recreate vec_chunks
        self._recreate_vec_chunks(conn, embedding_dim)

        # Embed all chunks in batches
        chunks_embedded = self._embed_all_chunks(conn, model, errors)

        # Get final count
        embeddings_after = self._count_embeddings(conn)

        conn.close()

        elapsed = time.time() - start_time

        return EmbeddingRebuildResult(
            dry_run=False,
            documents_found=documents_found,
            chunks_found=chunks_found,
            chunks_embedded=chunks_embedded,
            embeddings_before=embeddings_before,
            embeddings_after=embeddings_after,
            time_taken=elapsed,
            message=f"Rebuilt embeddings: {chunks_embedded}/{chunks_found} chunks in {elapsed:.1f}s",
            errors=errors if errors else [],
            model_name=model_name,
            embedding_dim=embedding_dim
        )

    def _try_load_vectorlite(self, conn: sqlite3.Connection) -> bool:
        """Attempt to load vectorlite extension"""
        try:
            import vectorlite_py
            conn.enable_load_extension(True)
            conn.load_extension(vectorlite_py.vectorlite_path())
            return True
        except Exception:
            return False

    def _load_model(self, model_name: str):
        """Load the embedding model

        Returns:
            Tuple of (model, embedding_dim) or (None, None) on failure
        """
        try:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer(model_name)
            embedding_dim = model.get_sentence_embedding_dimension()
            return model, embedding_dim
        except Exception:
            return None, None

    def _count_documents(self, conn: sqlite3.Connection) -> int:
        """Get total document count"""
        cursor = conn.execute("SELECT COUNT(*) FROM documents")
        return cursor.fetchone()[0]

    def _count_chunks(self, conn: sqlite3.Connection) -> int:
        """Get total chunk count"""
        cursor = conn.execute("SELECT COUNT(*) FROM chunks")
        return cursor.fetchone()[0]

    def _count_embeddings(self, conn: sqlite3.Connection) -> int:
        """Get current embedding count from vec_chunks

        Uses knn_search enumeration since vectorlite doesn't support COUNT(*)
        """
        try:
            import vectorlite_py
            conn.enable_load_extension(True)
            conn.load_extension(vectorlite_py.vectorlite_path())

            # Try to enumerate via knn_search with zero vector
            # Assume 1024 dim (Arctic) - will fail gracefully if wrong
            zero_vec = b'\x00' * (1024 * 4)
            cursor = conn.execute('''
                SELECT COUNT(*) FROM (
                    SELECT v.rowid FROM vec_chunks v
                    WHERE knn_search(v.embedding, knn_param(?, ?))
                )
            ''', (zero_vec, self.MAX_ELEMENTS))
            return cursor.fetchone()[0]
        except Exception:
            return 0

    def _recreate_vec_chunks(self, conn: sqlite3.Connection, embedding_dim: int) -> None:
        """Drop and recreate vec_chunks table"""
        db_dir = os.path.dirname(self.db_path)
        index_path = os.path.join(db_dir, "vec_chunks.idx")

        # Drop existing table
        conn.execute("DROP TABLE IF EXISTS vec_chunks")
        conn.commit()

        # Remove index file if exists
        if os.path.exists(index_path):
            os.remove(index_path)

        # Create new table
        conn.execute(f"""
            CREATE VIRTUAL TABLE vec_chunks USING vectorlite(
                embedding float32[{embedding_dim}] cosine,
                hnsw(max_elements={self.MAX_ELEMENTS}),
                "{index_path}"
            )
        """)
        conn.commit()

    def _embed_all_chunks(self, conn: sqlite3.Connection, model, errors: list) -> int:
        """Embed all chunks in batches

        Args:
            conn: Database connection
            model: SentenceTransformer model
            errors: List to append error messages to

        Returns:
            Number of chunks successfully embedded
        """
        import struct

        total_embedded = 0
        offset = 0

        while True:
            cursor = conn.execute(
                "SELECT id, content FROM chunks ORDER BY id LIMIT ? OFFSET ?",
                (self.batch_size, offset)
            )
            batch = cursor.fetchall()

            if not batch:
                break

            chunk_ids = [row[0] for row in batch]
            texts = [row[1] for row in batch]

            try:
                # Generate embeddings
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
                total_embedded += len(batch)

            except Exception as e:
                errors.append(f"Batch at offset {offset}: {e}")

            offset += self.batch_size

        return total_embedded
