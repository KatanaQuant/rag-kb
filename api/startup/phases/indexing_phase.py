"""Indexing phase.

Background indexing task: sanitization, document indexing, file watching.
"""
import os
import threading

from config import default_config
from value_objects import IndexingStats
from watcher import FileWatcherService


class IndexingPhase:
    """Manages background indexing operations.

    Handles:
    - Starting background thread for indexing
    - File watching service
    - Document indexing orchestration
    - Post-indexing orphan detection
    """

    def __init__(self, state, sanitization_phase=None):
        """Initialize with application state.

        Args:
            state: AppState instance
            sanitization_phase: Optional SanitizationPhase instance for pre-indexing repairs
        """
        self.state = state
        self.sanitization_phase = sanitization_phase

    def start_background(self):
        """Start indexing in background thread."""
        thread = threading.Thread(target=self.background_task, daemon=True)
        thread.start()

    def background_task(self):
        """Background task with sanitization stage before indexing.

        Flow:
        1. Start watcher (system responsive immediately)
        2. Sanitization: repair orphans from previous runs
        3. Index new files
        4. Post-indexing orphan check: catch orphans created during indexing
        """
        # Start watcher first so system is responsive immediately
        self.start_watcher()

        # Sanitization stage: repair before new indexing
        if self.sanitization_phase:
            self.sanitization_phase.execute()

        # Then do indexing in background
        self.state.runtime.indexing_in_progress = True
        try:
            self.index_docs()
        finally:
            self.state.runtime.indexing_in_progress = False

        # Post-indexing orphan check (catches orphans created during indexing)
        self.check_post_indexing_orphans()

    def index_docs(self):
        """Index documents."""
        print("Indexing documents...")
        try:
            self.run_indexing()
        except Exception as e:
            print("Indexing error occurred")

    def run_indexing(self):
        """Run indexing process."""
        orchestrator = self.create_orchestrator()
        files, chunks = orchestrator.index_all(queue=self.state.indexing.queue)
        self.state.runtime.stats = IndexingStats(files=files, chunks=chunks)
        if files > 0:
            print(f"Indexed {files} docs, {chunks} chunks")

    def create_orchestrator(self):
        """Create orchestrator with queue for concurrent pipeline."""
        from operations.index_orchestrator import IndexOrchestrator
        from operations.document_indexer import DocumentIndexer
        from pipeline import EmbeddingService

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
        return IndexOrchestrator(
            kb_path,
            indexer,
            self.state.core.processor,
            self.state.core.progress_tracker,
            queue=self.state.indexing.queue
        )

    def create_indexer(self):
        """Create document indexer."""
        from pipeline import EmbeddingService
        from operations.document_indexer import DocumentIndexer

        embedding_workers = int(os.getenv('EMBEDDING_WORKERS', '2'))
        max_pending = int(os.getenv('MAX_PENDING_EMBEDDINGS', str(embedding_workers * 2)))
        embedding_service = EmbeddingService(
            model=self.state.core.model,
            vector_store=self.state.core.vector_store,
            max_workers=embedding_workers,
            max_pending=max_pending,
            processor=self.state.core.processor
        )
        return DocumentIndexer(
            self.state.core.processor,
            embedding_service
        )

    def check_post_indexing_orphans(self):
        """Check for orphans created during initial indexing.

        This catches orphans that were created during index_docs() which
        the pre-indexing sanitization stage couldn't detect.

        Issue #2 in KNOWN_ISSUES.md - orphans during initial indexing.
        """
        if not self._is_auto_repair_enabled():
            return

        if not self.state.core.progress_tracker:
            return

        print("\n=== Post-Indexing Orphan Check ===")
        orphans = self._detect_orphans()
        if orphans:
            print(f"Found {len(orphans)} orphans created during indexing")
            self._queue_orphans_for_repair(orphans)
        else:
            print("No post-indexing orphans found")
        print("=== Post-Indexing Check Complete ===\n")

    def start_watcher(self):
        """Start file watcher if enabled."""
        if not default_config.watcher.enabled:
            print("File watcher disabled")
            return

        self.state.runtime.watcher = FileWatcherService(
            watch_path=default_config.paths.knowledge_base,
            queue=self.state.indexing.queue,
            debounce_seconds=default_config.watcher.debounce_seconds,
            batch_size=default_config.watcher.batch_size
        )
        self.state.start_watcher()

    def _is_auto_repair_enabled(self) -> bool:
        """Check if auto-repair is enabled."""
        return os.getenv('AUTO_REPAIR_ORPHANS', 'true').lower() == 'true'

    def _detect_orphans(self):
        """Detect orphaned files."""
        from operations.orphan_detector import OrphanDetector
        detector = OrphanDetector(self.state.core.progress_tracker, self.state.core.vector_store)
        return detector.detect_orphans()

    def _queue_orphans_for_repair(self, orphans):
        """Queue orphaned files for repair."""
        from operations.orphan_detector import OrphanDetector
        print(f"Found {len(orphans)} orphaned files")
        print("Adding orphans to queue with HIGH priority...\n")
        detector = OrphanDetector(self.state.core.progress_tracker, self.state.core.vector_store)
        detector.repair_orphans(self.state.indexing.queue)
        print("Orphans queued for reindexing")
