"""Partial embedding rebuild service

Re-embed only chunks missing from HNSW index (by ID range).
Use this when some chunks were indexed into a corrupted HNSW index
and need to be re-embedded. Does NOT drop the existing table.

This is faster than full rebuild because it only embeds missing chunks.
Best used with known ID ranges from investigation/diagnostics.

Extracted from scripts/partial_rebuild.py for API use.
"""
import sqlite3
import time
import os
from dataclasses import dataclass, field
from typing import Optional, List, Set


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


class PartialRebuilder:
    """Partial embedding rebuilder with injectable db_path

    Re-embeds only chunks in a specified ID range. Unlike full rebuild,
    this ADDS to the existing vec_chunks table without dropping it.

    Example:
        rebuilder = PartialRebuilder(db_path="/app/data/rag.db")
        # Re-embed chunks 70778-71727 (from investigation)
        result = rebuilder.rebuild(
            start_id=70778,
            end_id=71727,
            dry_run=True
        )
    """

    def __init__(self, db_path: str, batch_size: int = 32):
        """Initialize rebuilder with database path

        Args:
            db_path: Path to SQLite database file
            batch_size: Number of chunks to embed per batch (default 32)
        """
        self.db_path = db_path
        self.batch_size = batch_size

    def rebuild(
        self,
        start_id: Optional[int] = None,
        end_id: Optional[int] = None,
        dry_run: bool = False
    ) -> PartialRebuildResult:
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

        conn = sqlite3.connect(self.db_path)

        # Get chunks in range
        chunk_ids = self._get_chunk_ids_in_range(conn, start_id, end_id)
        chunks_in_range = len(chunk_ids)

        # Handle empty range
        if chunks_in_range == 0:
            conn.close()
            return PartialRebuildResult(
                dry_run=dry_run,
                start_id=start_id,
                end_id=end_id,
                chunks_in_range=0,
                chunks_embedded=0,
                time_taken=time.time() - start_time,
                message="No chunks found in specified range"
            )

        # Get model info for reporting
        model_name = os.environ.get('MODEL_NAME', 'Snowflake/snowflake-arctic-embed-l-v2.0')

        # Dry run - just report stats
        if dry_run:
            conn.close()
            range_desc = self._format_range(start_id, end_id, chunk_ids)
            return PartialRebuildResult(
                dry_run=True,
                start_id=start_id,
                end_id=end_id,
                chunks_in_range=chunks_in_range,
                chunks_embedded=0,
                time_taken=time.time() - start_time,
                message=f"Would embed {chunks_in_range} chunks in range {range_desc}",
                model_name=model_name
            )

        # Load vectorlite
        if not self._try_load_vectorlite(conn):
            conn.close()
            return PartialRebuildResult(
                dry_run=False,
                start_id=start_id,
                end_id=end_id,
                chunks_in_range=chunks_in_range,
                chunks_embedded=0,
                time_taken=time.time() - start_time,
                message="Failed to load vectorlite extension",
                errors=["Vectorlite extension not available"]
            )

        # Load embedding model
        model = self._load_model(model_name)
        if model is None:
            conn.close()
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

        # Embed chunks in range
        chunks_embedded = self._embed_chunks(conn, model, chunk_ids, errors)

        conn.close()

        elapsed = time.time() - start_time
        range_desc = self._format_range(start_id, end_id, chunk_ids)

        return PartialRebuildResult(
            dry_run=False,
            start_id=start_id,
            end_id=end_id,
            chunks_in_range=chunks_in_range,
            chunks_embedded=chunks_embedded,
            time_taken=elapsed,
            message=f"Embedded {chunks_embedded}/{chunks_in_range} chunks in range {range_desc} ({elapsed:.1f}s)",
            errors=errors if errors else [],
            model_name=model_name
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
            SentenceTransformer model or None on failure
        """
        try:
            from sentence_transformers import SentenceTransformer
            return SentenceTransformer(model_name)
        except Exception:
            return None

    def _get_chunk_ids_in_range(
        self,
        conn: sqlite3.Connection,
        start_id: Optional[int],
        end_id: Optional[int]
    ) -> List[int]:
        """Get chunk IDs in the specified range

        If no range specified, returns all chunk IDs.
        """
        if start_id is not None and end_id is not None:
            cursor = conn.execute(
                "SELECT id FROM chunks WHERE id BETWEEN ? AND ? ORDER BY id",
                (start_id, end_id)
            )
        elif start_id is not None:
            cursor = conn.execute(
                "SELECT id FROM chunks WHERE id >= ? ORDER BY id",
                (start_id,)
            )
        elif end_id is not None:
            cursor = conn.execute(
                "SELECT id FROM chunks WHERE id <= ? ORDER BY id",
                (end_id,)
            )
        else:
            cursor = conn.execute("SELECT id FROM chunks ORDER BY id")

        return [row[0] for row in cursor.fetchall()]

    def _format_range(
        self,
        start_id: Optional[int],
        end_id: Optional[int],
        chunk_ids: List[int]
    ) -> str:
        """Format range description for messages"""
        if chunk_ids:
            actual_start = chunk_ids[0]
            actual_end = chunk_ids[-1]
            return f"[{actual_start}-{actual_end}]"
        elif start_id is not None and end_id is not None:
            return f"[{start_id}-{end_id}]"
        elif start_id is not None:
            return f"[{start_id}-...]"
        elif end_id is not None:
            return f"[...-{end_id}]"
        else:
            return "[all]"

    def _embed_chunks(
        self,
        conn: sqlite3.Connection,
        model,
        chunk_ids: List[int],
        errors: list
    ) -> int:
        """Embed specified chunks and insert into vec_chunks

        Args:
            conn: Database connection
            model: SentenceTransformer model
            chunk_ids: List of chunk IDs to embed
            errors: List to append error messages to

        Returns:
            Number of chunks successfully embedded
        """
        import struct

        total_embedded = 0

        # Process in batches
        for i in range(0, len(chunk_ids), self.batch_size):
            batch_ids = chunk_ids[i:i + self.batch_size]

            # Fetch chunk content for this batch
            placeholders = ','.join('?' * len(batch_ids))
            cursor = conn.execute(
                f"SELECT id, content FROM chunks WHERE id IN ({placeholders})",
                batch_ids
            )
            batch = cursor.fetchall()

            if not batch:
                continue

            batch_chunk_ids = [row[0] for row in batch]
            texts = [row[1] for row in batch]

            try:
                # Generate embeddings
                embeddings = model.encode(
                    texts,
                    normalize_embeddings=True,
                    show_progress_bar=False
                )

                # Insert into vec_chunks
                for chunk_id, embedding in zip(batch_chunk_ids, embeddings):
                    embedding_blob = struct.pack(f'{len(embedding)}f', *embedding)
                    conn.execute(
                        "INSERT INTO vec_chunks (rowid, embedding) VALUES (?, ?)",
                        (chunk_id, embedding_blob)
                    )

                conn.commit()
                total_embedded += len(batch)

            except Exception as e:
                errors.append(f"Batch starting at ID {batch_ids[0]}: {e}")

        return total_embedded
