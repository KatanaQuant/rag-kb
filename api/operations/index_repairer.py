"""Combined index repair service

Runs both HNSW and FTS index rebuilds in sequence.
Convenience operation for full index maintenance.

Use cases:
- Complete index recovery after database inconsistencies
- Scheduled maintenance to ensure all indexes are in sync
- Recovery after interrupted indexing operations
"""
import time
from dataclasses import dataclass
from typing import Optional

from operations.hnsw_rebuilder import HnswRebuilder, HnswRebuildResult
from operations.fts_rebuilder import FtsRebuilder, FtsRebuildResult


@dataclass
class IndexRepairResult:
    """Result of combined index repair operation"""
    dry_run: bool
    total_time: float
    hnsw_result: HnswRebuildResult
    fts_result: FtsRebuildResult
    message: str
    error: Optional[str] = None


class IndexRepairer:
    """Combined HNSW and FTS index repair service

    Runs both HnswRebuilder and FtsRebuilder in sequence to ensure
    all indexes are consistent with the chunks table.

    Example:
        repairer = IndexRepairer(db_path="/app/data/rag.db")
        result = repairer.repair(dry_run=True)  # Preview changes
        if result.hnsw_result.orphan_embeddings > 0:
            result = repairer.repair(dry_run=False)  # Execute repair
    """

    def __init__(self, db_path: str):
        """Initialize repairer with database path

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self.hnsw_rebuilder = HnswRebuilder(db_path)
        self.fts_rebuilder = FtsRebuilder(db_path)

    def repair(self, dry_run: bool = False) -> IndexRepairResult:
        """Repair both HNSW and FTS indexes

        Runs HNSW rebuild first, then FTS rebuild. Both operations
        use the same dry_run flag.

        Args:
            dry_run: If True, report what would be done without modifying

        Returns:
            IndexRepairResult with combined statistics from both operations
        """
        start_time = time.time()
        error = None

        # Run HNSW rebuild
        try:
            hnsw_result = self.hnsw_rebuilder.rebuild(dry_run=dry_run)
        except Exception as e:
            # Create error result for HNSW
            hnsw_result = HnswRebuildResult(
                total_embeddings=0,
                valid_embeddings=0,
                orphan_embeddings=0,
                final_embeddings=0,
                dry_run=dry_run,
                elapsed_time=0.0,
                error=str(e)
            )
            error = f"HNSW rebuild failed: {e}"

        # Run FTS rebuild
        try:
            fts_result = self.fts_rebuilder.rebuild(dry_run=dry_run)
        except Exception as e:
            # Create error result for FTS
            fts_result = FtsRebuildResult(
                dry_run=dry_run,
                chunks_found=0,
                chunks_indexed=0,
                fts_entries_before=0,
                fts_entries_after=0,
                time_taken=0.0,
                message=f"Error: {e}",
                errors=[str(e)]
            )
            if error:
                error += f"; FTS rebuild failed: {e}"
            else:
                error = f"FTS rebuild failed: {e}"

        total_time = time.time() - start_time

        # Build summary message
        message = self._build_message(dry_run, hnsw_result, fts_result, error)

        return IndexRepairResult(
            dry_run=dry_run,
            total_time=total_time,
            hnsw_result=hnsw_result,
            fts_result=fts_result,
            message=message,
            error=error
        )

    def _build_message(
        self,
        dry_run: bool,
        hnsw_result: HnswRebuildResult,
        fts_result: FtsRebuildResult,
        error: Optional[str]
    ) -> str:
        """Build summary message for repair result"""
        if error:
            return f"Index repair completed with errors: {error}"

        parts = []

        # HNSW summary
        if hnsw_result.error:
            parts.append(f"HNSW: {hnsw_result.error}")
        elif hnsw_result.orphan_embeddings == 0:
            parts.append("HNSW: clean (no orphans)")
        elif dry_run:
            parts.append(f"HNSW: would remove {hnsw_result.orphan_embeddings} orphans")
        else:
            parts.append(f"HNSW: removed {hnsw_result.orphan_embeddings} orphans")

        # FTS summary
        if dry_run:
            parts.append(f"FTS: would rebuild {fts_result.chunks_found} chunks")
        else:
            parts.append(f"FTS: rebuilt {fts_result.chunks_indexed} chunks")

        prefix = "Would repair" if dry_run else "Repaired"
        return f"{prefix} indexes. {'; '.join(parts)}"
