"""Sanitization phase.

Pre-indexing repairs: resume incomplete files, repair orphans, self-healing.
"""
import os

from operations.orphan_detector import OrphanDetector
from startup.self_healing import SelfHealingService


class SanitizationPhase:
    """Sanitizes data before new indexing.

    Handles:
    - Resuming incomplete file processing
    - Detecting and repairing orphaned files
    - Self-healing database operations
    """

    def __init__(self, state):
        """Initialize with application state.

        Args:
            state: AppState instance with progress tracker and vector store
        """
        self.state = state

    def execute(self):
        """Run all sanitization stages.

        Flow:
        1. Resume incomplete files
        2. Detect and repair orphans (files in DB without embeddings)
        3. Self-healing: clean empty documents, backfill chunk counts
        """
        if not self.state.core.progress_tracker:
            return

        print("\n=== Starting Sanitization Stage ===")
        self.resume_incomplete_files()
        self.repair_orphaned_files()
        self.run_self_healing()
        self._check_hnsw_health()
        print("=== Sanitization Complete ===\n")

    def run_self_healing(self):
        """Run self-healing operations (delete empty docs, backfill counts)."""
        healer = SelfHealingService()
        healer.run()

    def resume_incomplete_files(self):
        """Resume processing of incomplete files."""
        from config import default_config
        from operations.index_orchestrator import IndexOrchestrator
        from operations.document_indexer import DocumentIndexer
        from pipeline import EmbeddingService

        print("Checking for incomplete files...")

        # Create indexer for orchestrator
        embedding_workers = int(os.getenv('EMBEDDING_WORKERS', '2'))
        max_pending = int(os.getenv('MAX_PENDING_EMBEDDINGS', str(embedding_workers * 2)))
        embedding_service = EmbeddingService(
            model=self.state.core.model,
            vector_store=self.state.core.vector_store,
            max_workers=embedding_workers,
            max_pending=max_pending,
            processor=self.state.core.processor
        )
        indexer = DocumentIndexer(
            self.state.core.processor,
            embedding_service
        )

        kb_path = default_config.paths.knowledge_base
        orchestrator = IndexOrchestrator(
            kb_path,
            indexer,
            self.state.core.processor,
            self.state.core.progress_tracker,
            queue=self.state.indexing.queue
        )
        orchestrator.resume_incomplete_processing()

    def repair_orphaned_files(self):
        """Detect and repair orphaned files if auto-repair enabled."""
        if not self.is_auto_repair_enabled():
            return

        orphans = self.detect_orphans()
        if orphans:
            self.queue_orphans_for_repair(orphans)
        else:
            print("No orphaned files found")

    def is_auto_repair_enabled(self) -> bool:
        """Check if auto-repair is enabled."""
        auto_repair = os.getenv('AUTO_REPAIR_ORPHANS', 'true').lower() == 'true'
        if not auto_repair:
            print("Auto-repair disabled, skipping orphan check")
        return auto_repair

    def detect_orphans(self):
        """Detect orphaned files."""
        detector = OrphanDetector(self.state.core.progress_tracker, self.state.core.vector_store)
        return detector.detect_orphans()

    def queue_orphans_for_repair(self, orphans):
        """Queue orphaned files for repair."""
        print(f"Found {len(orphans)} orphaned files")
        print("Adding orphans to queue with HIGH priority...\n")
        detector = OrphanDetector(self.state.core.progress_tracker, self.state.core.vector_store)
        detector.repair_orphans(self.state.indexing.queue)
        print("Orphans queued for reindexing")

    def _check_hnsw_health(self):
        """Check HNSW index for orphan embeddings (PostgreSQL version).

        PostgreSQL + pgvector uses referential integrity and CASCADE deletes,
        so orphan embeddings are prevented at the database level.
        This check simply verifies vec_chunks count matches chunks count.
        """
        if not self._is_hnsw_check_enabled():
            return

        try:
            from operations.postgres_maintenance import PostgresIntegrityChecker

            checker = PostgresIntegrityChecker()
            checker.connect()
            result = checker.check_vector_count_mismatch()
            checker.close()

            chunk_count = result.get('chunk_count', 0)
            vector_count = result.get('vector_count', 0)

            if result.get('ok', True):
                print(f"[HNSW Health] OK - {vector_count:,} embeddings, {chunk_count:,} chunks")
            else:
                diff = chunk_count - vector_count
                print(f"[HNSW Health] WARNING: {diff:,} chunks missing embeddings")
                print(f"[HNSW Health] vec_chunks: {vector_count:,}, chunks: {chunk_count:,}")
                print("[HNSW Health] Fix: POST /api/maintenance/rebuild-embeddings")

        except Exception as e:
            print(f"[HNSW Health] Check failed: {e}")

    def _is_hnsw_check_enabled(self) -> bool:
        """Check if HNSW health check is enabled."""
        return os.getenv('CHECK_HNSW_HEALTH', 'true').lower() == 'true'
