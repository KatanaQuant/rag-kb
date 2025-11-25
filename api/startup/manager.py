import os
import time
from pathlib import Path
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
import threading

from sentence_transformers import SentenceTransformer
from config import default_config
from ingestion import DocumentProcessor, VectorStore, AsyncVectorStore, ProcessingProgressTracker
from watcher import FileWatcherService
from query_cache import QueryCache
from value_objects import IndexingStats
from app_state import AppState
from api_services.model_loader import ModelLoader
from api_services.file_walker import FileWalker
from api_services.document_indexer import DocumentIndexer
from api_services.index_orchestrator import IndexOrchestrator
from api_services.orphan_detector import OrphanDetector
from startup.config_validator import ConfigValidator


class StartupManager:
    """Manages application startup"""

    def __init__(self, app_state: AppState):
        self.state = app_state

    async def initialize(self):
        """Initialize all components (async for AsyncVectorStore)"""
        print("Initializing RAG system...")
        self._validate_config()
        self._load_model()
        await self._init_store()  # Now async
        self._init_progress_tracker()
        self._init_processor()
        self._init_cache()
        self._init_queue_and_worker()
        print("RAG system ready! Starting sanitization and indexing...")
        self._start_background_indexing()

    def _validate_config(self):
        """Validate configuration before startup"""
        validator = ConfigValidator(default_config)
        validator.validate()
        print("Configuration validated")

    def _load_model(self):
        """Load embedding model"""
        loader = ModelLoader()
        model_name = default_config.model.name
        self.state.core.model = loader.load(model_name)

    async def _init_store(self):
        """Initialize both sync and async vector stores

        Hybrid Architecture:
        - Sync VectorStore: Used by pipeline workers for background writes
        - Async AsyncVectorStore: Used by API routes for non-blocking reads

        Both stores use the same SQLite database with WAL mode for safe concurrent access.
        """
        print("Initializing vector stores...")

        # Initialize sync store for pipeline workers
        self.state.core.vector_store = VectorStore()
        print("Sync vector store initialized (for pipeline workers)")

        # Initialize async store for API routes
        self.state.core.async_vector_store = AsyncVectorStore()
        await self.state.core.async_vector_store.initialize()
        print("Async vector store initialized (for API routes)")

    def _init_progress_tracker(self):
        """Initialize progress tracker"""
        if default_config.processing.enabled:
            db_path = default_config.database.path
            self.state.core.progress_tracker = ProcessingProgressTracker(db_path)
            print("Resumable processing enabled")

    def _init_processor(self):
        """Initialize processor"""
        self.state.core.processor = DocumentProcessor(self.state.core.progress_tracker)

    def _init_cache(self):
        """Initialize query cache"""
        if default_config.cache.enabled:
            self.state.query.cache = QueryCache(default_config.cache.max_size)
            print(f"Query cache enabled (size: {default_config.cache.max_size})")
        else:
            print("Query cache disabled")

    def _init_queue_and_worker(self):
        """Initialize indexing queue and worker"""
        from services import IndexingQueue, IndexingWorker
        self.state.indexing.queue = IndexingQueue()
        indexer = self._create_indexer()

        # Initialize concurrent pipeline first
        self._init_concurrent_pipeline()

        # Create worker with pipeline coordinator
        self.state.indexing.worker = IndexingWorker(
            self.state.indexing.queue,
            indexer,
            pipeline_coordinator=self.state.indexing.pipeline_coordinator
        )
        self.state.indexing.worker.start()
        print("Indexing queue and worker started")

    def _init_concurrent_pipeline(self):
        """Initialize concurrent pipeline for parallel processing"""
        if not self._is_pipeline_enabled():
            return

        embedding_service = self._create_embedding_service()
        indexer = self._create_indexer()
        self._start_pipeline(embedding_service, indexer)

    def _is_pipeline_enabled(self) -> bool:
        """Check if concurrent pipeline is enabled"""
        import os
        enable_pipeline = os.getenv('ENABLE_CONCURRENT_PIPELINE', 'true').lower() == 'true'
        if not enable_pipeline:
            print("Concurrent pipeline disabled")
            self.state.indexing.pipeline_coordinator = None
        return enable_pipeline

    def _create_embedding_service(self):
        """Create embedding service with environment config"""
        import os
        from services.embedding_service import EmbeddingService

        max_workers = int(os.getenv('EMBEDDING_WORKERS', '3'))
        max_pending = int(os.getenv('MAX_PENDING_EMBEDDINGS', '6'))

        return EmbeddingService(
            self.state.core.model,
            self.state.core.vector_store,
            max_workers=max_workers,
            max_pending=max_pending
        )

    def _start_pipeline(self, embedding_service, indexer):
        """Start pipeline coordinator"""
        from services.pipeline_coordinator import PipelineCoordinator

        self.state.indexing.pipeline_coordinator = PipelineCoordinator(
            processor=self.state.core.processor,
            indexer=indexer,
            embedding_service=embedding_service
        )
        self.state.indexing.pipeline_coordinator.start()
        print("Concurrent pipeline started")

    def _sanitize_before_indexing(self):
        """Sanitization stage: detect and repair issues before new indexing

        Flow:
        1. Resume incomplete files
        2. Detect and repair orphans (files in DB without embeddings)
        3. Only after repairs complete, allow new file processing
        """
        if not self.state.core.progress_tracker:
            return

        print("\n=== Starting Sanitization Stage ===")
        self._resume_incomplete_files()
        self._repair_orphaned_files()
        print("=== Sanitization Complete ===\n")

    def _resume_incomplete_files(self):
        """Resume processing of incomplete files"""
        print("Checking for incomplete files...")
        orchestrator = self._create_orchestrator()
        orchestrator.resume_incomplete_processing()

    def _repair_orphaned_files(self):
        """Detect and repair orphaned files if auto-repair enabled"""
        if not self._is_auto_repair_enabled():
            return

        orphans = self._detect_orphans()
        if orphans:
            self._queue_orphans_for_repair(orphans)
        else:
            print("No orphaned files found")

    def _is_auto_repair_enabled(self) -> bool:
        """Check if auto-repair is enabled"""
        import os
        auto_repair = os.getenv('AUTO_REPAIR_ORPHANS', 'true').lower() == 'true'
        if not auto_repair:
            print("Auto-repair disabled, skipping orphan check")
        return auto_repair

    def _detect_orphans(self):
        """Detect orphaned files"""
        detector = OrphanDetector(self.state.core.progress_tracker, self.state.core.vector_store)
        return detector.detect_orphans()

    def _queue_orphans_for_repair(self, orphans):
        """Queue orphaned files for repair"""
        print(f"Found {len(orphans)} orphaned files")
        print("Adding orphans to queue with HIGH priority...\n")
        detector = OrphanDetector(self.state.core.progress_tracker, self.state.core.vector_store)
        detector.repair_orphans(self.state.indexing.queue)
        print("Orphans queued for reindexing")

    def _index_docs(self):
        """Index documents"""
        print("Indexing documents...")
        try:
            self._run_indexing()
        except Exception as e:
            print("Indexing error occurred")

    def _run_indexing(self):
        """Run indexing process"""
        orchestrator = self._create_orchestrator()
        files, chunks = orchestrator.index_all(queue=self.state.indexing.queue)
        self.state.runtime.stats = IndexingStats(files=files, chunks=chunks)
        if files > 0:
            print(f"Indexed {files} docs, {chunks} chunks")

    def _create_orchestrator(self):
        """Create orchestrator with queue for concurrent pipeline"""
        indexer = self._create_indexer()
        kb_path = default_config.paths.knowledge_base
        return IndexOrchestrator(
            kb_path,
            indexer,
            self.state.core.processor,
            self.state.core.progress_tracker,
            queue=self.state.indexing.queue
        )

    def _create_indexer(self):
        """Create indexer"""
        from services import EmbeddingService
        import os
        embedding_workers = int(os.getenv('EMBEDDING_WORKERS', '3'))
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

    def _start_background_indexing(self):
        """Start indexing in background thread"""
        import threading
        thread = threading.Thread(target=self._background_indexing_task, daemon=True)
        thread.start()

    def _background_indexing_task(self):
        """Background task with sanitization stage before indexing"""
        # Start watcher first so system is responsive immediately
        self._start_watcher()

        # Sanitization stage: repair before new indexing
        self._sanitize_before_indexing()

        # Then do indexing in background
        self.state.runtime.indexing_in_progress = True
        try:
            self._index_docs()
        finally:
            self.state.runtime.indexing_in_progress = False

    def _start_watcher(self):
        """Start file watcher if enabled"""
        if not default_config.watcher.enabled:
            print("File watcher disabled")
            return

        self.state.runtime.watcher = FileWatcherService(
            watch_path=default_config.paths.knowledge_base,
            queue=self.state.indexing.queue,
            debounce_seconds=default_config.watcher.debounce_seconds,
            batch_size=default_config.watcher.batch_size
        )
        self.state.runtime.watcher.start()

