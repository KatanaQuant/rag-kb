"""PostgreSQL embedding rebuild service

Rebuilds all vector embeddings from existing chunks for PostgreSQL + pgvector.
Use this when embeddings are missing or need to be regenerated.

This is a LONG-RUNNING operation that:
1. Loads the embedding model
2. Iterates through all chunks in batches
3. Generates new embeddings for each chunk
4. Truncates and repopulates vec_chunks table
5. Also rebuilds fts_chunks table (tsvector)
"""
import time
import os
from dataclasses import dataclass, field
from typing import Optional, List

from config import default_config
from ingestion.database_factory import DatabaseFactory


@dataclass
class EmbeddingRebuildResult:
    """Result of full embedding rebuild operation"""
    dry_run: bool
    documents_found: int
    chunks_found: int
    chunks_embedded: int
    embeddings_before: int
    embeddings_after: int
    fts_before: int
    fts_after: int
    time_taken: float
    message: str
    errors: List[str] = field(default_factory=list)
    model_name: Optional[str] = None
    embedding_dim: Optional[int] = None


class PostgresEmbeddingRebuilder:
    """Full embedding rebuilder for PostgreSQL + pgvector

    Regenerates all vector embeddings from chunk content using the
    configured embedding model. This is a long-running operation
    suitable for recovery from complete index corruption.

    Example:
        rebuilder = PostgresEmbeddingRebuilder()
        result = rebuilder.rebuild(dry_run=True)  # Preview
        if result.chunks_found > 0:
            result = rebuilder.rebuild(dry_run=False)  # Execute
    """

    def __init__(self, config=default_config.database, batch_size: int = 32):
        """Initialize rebuilder with config

        Args:
            config: Database configuration
            batch_size: Number of chunks to embed per batch (default 32)
        """
        self.config = config
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

        db = DatabaseFactory.create_connection(self.config)
        conn = db.connect()

        # Get current counts
        documents_found = self._count_documents(conn)
        chunks_found = self._count_chunks(conn)
        embeddings_before = self._count_embeddings(conn)
        fts_before = self._count_fts(conn)

        # Handle empty database
        if chunks_found == 0:
            db.close()
            return EmbeddingRebuildResult(
                dry_run=dry_run,
                documents_found=documents_found,
                chunks_found=0,
                chunks_embedded=0,
                embeddings_before=embeddings_before,
                embeddings_after=0 if not dry_run else embeddings_before,
                fts_before=fts_before,
                fts_after=0 if not dry_run else fts_before,
                time_taken=time.time() - start_time,
                message="No chunks found - database is empty"
            )

        # Get model info for reporting
        model_name = os.environ.get('MODEL_NAME', 'Snowflake/snowflake-arctic-embed-l-v2.0')

        # Dry run - just report stats
        if dry_run:
            db.close()
            return EmbeddingRebuildResult(
                dry_run=True,
                documents_found=documents_found,
                chunks_found=chunks_found,
                chunks_embedded=0,
                embeddings_before=embeddings_before,
                embeddings_after=embeddings_before,
                fts_before=fts_before,
                fts_after=fts_before,
                time_taken=time.time() - start_time,
                message=f"Would rebuild {chunks_found} embeddings from {documents_found} documents",
                model_name=model_name
            )

        # Load embedding model
        model, embedding_dim = self._load_model(model_name)
        if model is None:
            db.close()
            return EmbeddingRebuildResult(
                dry_run=False,
                documents_found=documents_found,
                chunks_found=chunks_found,
                chunks_embedded=0,
                embeddings_before=embeddings_before,
                embeddings_after=embeddings_before,
                fts_before=fts_before,
                fts_after=fts_before,
                time_taken=time.time() - start_time,
                message="Failed to load embedding model",
                errors=[f"Could not load model: {model_name}"],
                model_name=model_name
            )

        # Truncate vec_chunks and fts_chunks
        self._truncate_indexes(conn)

        # Embed all chunks in batches (also rebuilds FTS)
        chunks_embedded = self._embed_all_chunks(conn, model, errors)

        # Get final counts
        embeddings_after = self._count_embeddings(conn)
        fts_after = self._count_fts(conn)

        db.close()

        elapsed = time.time() - start_time

        return EmbeddingRebuildResult(
            dry_run=False,
            documents_found=documents_found,
            chunks_found=chunks_found,
            chunks_embedded=chunks_embedded,
            embeddings_before=embeddings_before,
            embeddings_after=embeddings_after,
            fts_before=fts_before,
            fts_after=fts_after,
            time_taken=elapsed,
            message=f"Rebuilt {chunks_embedded}/{chunks_found} embeddings + FTS in {elapsed:.1f}s",
            errors=errors if errors else [],
            model_name=model_name,
            embedding_dim=embedding_dim
        )

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

    def _count_documents(self, conn) -> int:
        """Get total document count"""
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM documents")
            return cur.fetchone()[0]

    def _count_chunks(self, conn) -> int:
        """Get total chunk count"""
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM chunks")
            return cur.fetchone()[0]

    def _count_embeddings(self, conn) -> int:
        """Get current embedding count from vec_chunks"""
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM vec_chunks")
            return cur.fetchone()[0]

    def _count_fts(self, conn) -> int:
        """Get current FTS entry count"""
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM fts_chunks")
            return cur.fetchone()[0]

    def _truncate_indexes(self, conn) -> None:
        """Truncate vec_chunks and fts_chunks tables"""
        with conn.cursor() as cur:
            cur.execute("TRUNCATE vec_chunks")
            cur.execute("TRUNCATE fts_chunks")
        conn.commit()
        print("[PostgresEmbeddingRebuilder] Truncated vec_chunks and fts_chunks")

    def _embed_all_chunks(self, conn, model, errors: list) -> int:
        """Embed all chunks in batches

        Args:
            conn: Database connection
            model: SentenceTransformer model
            errors: List to append error messages to

        Returns:
            Number of chunks successfully embedded
        """
        total_embedded = 0
        offset = 0
        total_chunks = self._count_chunks(conn)

        print(f"[PostgresEmbeddingRebuilder] Embedding {total_chunks} chunks...")

        while True:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, content FROM chunks ORDER BY id LIMIT %s OFFSET %s",
                    (self.batch_size, offset)
                )
                batch = cur.fetchall()

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

                # Insert into vec_chunks and fts_chunks
                with conn.cursor() as cur:
                    for chunk_id, embedding, text in zip(chunk_ids, embeddings, texts):
                        # Insert embedding as pgvector format
                        cur.execute(
                            "INSERT INTO vec_chunks (rowid, embedding) VALUES (%s, %s)",
                            (chunk_id, embedding.tolist())
                        )
                        # Insert FTS entry
                        cur.execute(
                            "INSERT INTO fts_chunks (chunk_id, content) VALUES (%s, %s)",
                            (chunk_id, text)
                        )

                conn.commit()
                total_embedded += len(batch)

                # Progress report every 1000 chunks
                if total_embedded % 1000 == 0:
                    print(f"[PostgresEmbeddingRebuilder] Progress: {total_embedded}/{total_chunks}")

            except Exception as e:
                errors.append(f"Batch at offset {offset}: {e}")
                conn.rollback()

            offset += self.batch_size

        print(f"[PostgresEmbeddingRebuilder] Completed: {total_embedded} chunks embedded")
        return total_embedded
