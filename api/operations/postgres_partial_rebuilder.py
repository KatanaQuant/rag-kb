"""PostgreSQL partial embedding rebuild service

Re-embeds chunks in a specific ID range for PostgreSQL + pgvector.
Unlike full rebuild, this ADDS to the existing vec_chunks table.
Use when specific chunks are missing from the index.
"""
import time
import os
from dataclasses import dataclass, field
from typing import Optional, List

from config import default_config
from ingestion.database_factory import DatabaseFactory


@dataclass
class PartialRebuildResult:
    """Result of partial embedding rebuild operation"""
    dry_run: bool
    start_id: Optional[int]
    end_id: Optional[int]
    chunks_in_range: int
    chunks_embedded: int
    time_taken: float
    message: str
    errors: List[str] = field(default_factory=list)
    model_name: Optional[str] = None


class PostgresPartialRebuilder:
    """Partial embedding rebuilder for PostgreSQL + pgvector

    Re-embeds chunks within a specified ID range. Unlike full rebuild,
    this ADDS to the existing vec_chunks table without dropping it.

    Example:
        rebuilder = PostgresPartialRebuilder()
        result = rebuilder.rebuild(start_id=1000, end_id=2000, dry_run=False)
    """

    def __init__(self, config=default_config.database, batch_size: int = 32):
        """Initialize rebuilder with config

        Args:
            config: Database configuration
            batch_size: Number of chunks to embed per batch (default 32)
        """
        self.config = config
        self.batch_size = batch_size

    def rebuild(self, start_id: Optional[int] = None, end_id: Optional[int] = None,
                dry_run: bool = False) -> PartialRebuildResult:
        """Re-embed chunks in specified ID range

        Args:
            start_id: Start of chunk ID range (inclusive, optional)
            end_id: End of chunk ID range (inclusive, optional)
            dry_run: If True, report what would happen without modifying data

        Returns:
            PartialRebuildResult with operation statistics
        """
        start_time = time.time()
        errors = []

        db = DatabaseFactory.create_connection(self.config)
        conn = db.connect()

        # Get chunks in range
        chunks_in_range = self._count_chunks_in_range(conn, start_id, end_id)

        # Get model info
        model_name = os.environ.get('MODEL_NAME', 'Snowflake/snowflake-arctic-embed-l-v2.0')

        # Handle empty range
        if chunks_in_range == 0:
            db.close()
            return PartialRebuildResult(
                dry_run=dry_run,
                start_id=start_id,
                end_id=end_id,
                chunks_in_range=0,
                chunks_embedded=0,
                time_taken=time.time() - start_time,
                message="No chunks found in specified range"
            )

        # Dry run
        if dry_run:
            db.close()
            return PartialRebuildResult(
                dry_run=True,
                start_id=start_id,
                end_id=end_id,
                chunks_in_range=chunks_in_range,
                chunks_embedded=0,
                time_taken=time.time() - start_time,
                message=f"Would rebuild {chunks_in_range} embeddings in range [{start_id}, {end_id}]",
                model_name=model_name
            )

        # Load model
        model, _ = self._load_model(model_name)
        if model is None:
            db.close()
            return PartialRebuildResult(
                dry_run=False,
                start_id=start_id,
                end_id=end_id,
                chunks_in_range=chunks_in_range,
                chunks_embedded=0,
                time_taken=time.time() - start_time,
                message="Failed to load embedding model",
                errors=[f"Could not load model: {model_name}"],
                model_name=model_name
            )

        # Delete existing embeddings in range (if any)
        self._delete_embeddings_in_range(conn, start_id, end_id)

        # Embed chunks
        chunks_embedded = self._embed_chunks_in_range(conn, model, start_id, end_id, errors)

        db.close()

        elapsed = time.time() - start_time

        return PartialRebuildResult(
            dry_run=False,
            start_id=start_id,
            end_id=end_id,
            chunks_in_range=chunks_in_range,
            chunks_embedded=chunks_embedded,
            time_taken=elapsed,
            message=f"Rebuilt {chunks_embedded}/{chunks_in_range} embeddings in {elapsed:.1f}s",
            errors=errors if errors else [],
            model_name=model_name
        )

    def _load_model(self, model_name: str):
        """Load the embedding model"""
        try:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer(model_name)
            embedding_dim = model.get_sentence_embedding_dimension()
            return model, embedding_dim
        except Exception:
            return None, None

    def _count_chunks_in_range(self, conn, start_id: Optional[int], end_id: Optional[int]) -> int:
        """Count chunks in specified ID range"""
        query = "SELECT COUNT(*) FROM chunks WHERE 1=1"
        params = []

        if start_id is not None:
            query += " AND id >= %s"
            params.append(start_id)
        if end_id is not None:
            query += " AND id <= %s"
            params.append(end_id)

        with conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchone()[0]

    def _delete_embeddings_in_range(self, conn, start_id: Optional[int], end_id: Optional[int]) -> int:
        """Delete existing embeddings in range"""
        query = "DELETE FROM vec_chunks WHERE 1=1"
        params = []

        if start_id is not None:
            query += " AND rowid >= %s"
            params.append(start_id)
        if end_id is not None:
            query += " AND rowid <= %s"
            params.append(end_id)

        with conn.cursor() as cur:
            cur.execute(query, params)
            deleted = cur.rowcount
        conn.commit()
        return deleted

    def _embed_chunks_in_range(self, conn, model, start_id: Optional[int],
                                end_id: Optional[int], errors: list) -> int:
        """Embed chunks in specified ID range"""
        total_embedded = 0
        offset = 0

        query = "SELECT id, content FROM chunks WHERE 1=1"
        params = []

        if start_id is not None:
            query += " AND id >= %s"
            params.append(start_id)
        if end_id is not None:
            query += " AND id <= %s"
            params.append(end_id)

        query += " ORDER BY id LIMIT %s OFFSET %s"

        while True:
            with conn.cursor() as cur:
                cur.execute(query, params + [self.batch_size, offset])
                batch = cur.fetchall()

            if not batch:
                break

            chunk_ids = [row[0] for row in batch]
            texts = [row[1] for row in batch]

            try:
                embeddings = model.encode(
                    texts,
                    normalize_embeddings=True,
                    show_progress_bar=False
                )

                with conn.cursor() as cur:
                    for chunk_id, embedding, text in zip(chunk_ids, embeddings, texts):
                        # Insert embedding
                        cur.execute(
                            """INSERT INTO vec_chunks (rowid, embedding) VALUES (%s, %s)
                               ON CONFLICT (rowid) DO UPDATE SET embedding = EXCLUDED.embedding""",
                            (chunk_id, embedding.tolist())
                        )
                        # Insert/update FTS entry
                        cur.execute(
                            """INSERT INTO fts_chunks (chunk_id, content) VALUES (%s, %s)
                               ON CONFLICT (chunk_id) DO UPDATE SET content = EXCLUDED.content""",
                            (chunk_id, text)
                        )

                conn.commit()
                total_embedded += len(batch)

            except Exception as e:
                errors.append(f"Batch at offset {offset}: {e}")
                conn.rollback()

            offset += self.batch_size

        return total_embedded
