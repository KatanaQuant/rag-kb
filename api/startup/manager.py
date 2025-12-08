"""Startup manager - orchestrates application initialization.

Refactored from God Object (26 methods) to facade over focused phase classes.
Phase classes are available in startup.phases for direct use if needed.
"""
import os
import time
from pathlib import Path
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
import threading

from sentence_transformers import SentenceTransformer
from config import default_config
from ingestion import DocumentProcessor
from ingestion.database_factory import DatabaseFactory, get_backend
from watcher import FileWatcherService
from query_cache import QueryCache
from value_objects import IndexingStats
from app_state import AppState
from operations.model_loader import ModelLoader
from operations.file_walker import FileWalker
from operations.document_indexer import DocumentIndexer
from operations.index_orchestrator import IndexOrchestrator
from operations.orphan_detector import OrphanDetector
from startup.config_validator import ConfigValidator
from startup.postgres_self_healing import SelfHealingService

# Phase classes for focused responsibilities (Phase 2.1 refactoring)
from startup.phases import (
    ConfigurationPhase,
    ComponentPhase,
    PipelinePhase,
    SanitizationPhase,
    IndexingPhase,
)


class StartupManager:
    """Manages application startup.

    Facade over focused phase classes. Methods are organized into phases:
    - Configuration: validate config
    - Component: model, stores, processor, cache, reranker
    - Pipeline: queue, worker, concurrent pipeline
    - Sanitization: resume incomplete, repair orphans, self-healing
    - Indexing: background indexing, file watching
    """

    def __init__(self, app_state: AppState):
        self.state = app_state
        # Phase objects available for direct testing/use
        self._config_phase = ConfigurationPhase()
        self._component_phase = ComponentPhase(app_state)
        self._pipeline_phase = PipelinePhase(app_state)
        self._sanitization_phase = SanitizationPhase(app_state)
        self._indexing_phase = IndexingPhase(app_state, self._sanitization_phase)

    async def initialize(self):
        """Initialize all components (async for AsyncVectorStore)"""
        print("Initializing RAG system...")
        self._validate_config()
        self._load_model()
        await self._init_store()  # Now async
        self._init_progress_tracker()
        self._init_processor()
        self._init_cache()
        self._init_reranker()
        self._init_query_expander()
        self._init_queue_and_worker()
        print("RAG system ready! Starting sanitization and indexing...")
        self._start_background_indexing()

    # ============ Configuration Phase ============

    def _validate_config(self):
        """Validate configuration before startup"""
        validator = ConfigValidator(default_config)
        validator.validate()
        print("Configuration validated")

    # ============ Component Phase ============

    def _load_model(self):
        """Load embedding model"""
        loader = ModelLoader()
        model_name = default_config.model.name
        self.state.core.model = loader.load(model_name)

    async def _init_store(self):
        """Initialize vector store with unified architecture.

        Unified Architecture (v2.2.3+):
        - Single sync VectorStore with thread-safe locking
        - AsyncVectorStoreAdapter created lazily on first access
        - Eliminates dual-store HNSW corruption issues
        - DELETE operations now work correctly from API

        Backend Selection (v2.3.0+):
        - Uses DatabaseFactory to auto-detect backend from DATABASE_URL
        - Supports both PostgreSQL (pgvector) and SQLite (vectorlite)

        The adapter wraps the sync store using asyncio.to_thread() for
        non-blocking API operations while maintaining thread safety.
        """
        backend = get_backend()
        print(f"Initializing vector store (unified architecture, backend: {backend})...")

        # Initialize single sync store using factory (thread-safe via RLock)
        self.state.core.vector_store = DatabaseFactory.create_vector_store()
        print(f"Vector store initialized ({backend}, thread-safe, adapter created lazily)")

        # Note: async adapter is created lazily via CoreServices.async_vector_store property
        # No explicit initialization needed - just access state.core.async_vector_store

    def _init_progress_tracker(self):
        """Initialize progress tracker using factory for backend auto-detection."""
        if default_config.processing.enabled:
            self.state.core.progress_tracker = DatabaseFactory.create_progress_tracker()
            print(f"Resumable processing enabled (backend: {get_backend()})")

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

    def _init_reranker(self):
        """Initialize search result reranker from pipeline config"""
        from pipeline.factory import PipelineFactory

        factory = PipelineFactory.default()
        self.state.query.reranker = factory.create_reranker()

        if factory.reranking_enabled:
            print(f"Reranker enabled: {factory.config.reranking.model} (top_n={factory.reranking_top_n})")
        else:
            print("Reranker disabled")

    def _init_query_expander(self):
        """Initialize LLM-based query expander using Ollama"""
        import os
        from pipeline.query_expander import QueryExpander

        enabled = os.getenv("QUERY_EXPANSION_ENABLED", "false").lower() == "true"
        self.state.query.query_expander = QueryExpander(enabled=enabled)

        if enabled:
            model = os.getenv("QUERY_EXPANSION_MODEL", "qwen2.5:0.5b")
            ollama_url = os.getenv("OLLAMA_URL", "http://ollama:11434")
            print(f"Query expansion enabled: {model} via {ollama_url}")
        else:
            print("Query expansion disabled")

    # ============ Pipeline Phase ============

    def _init_queue_and_worker(self):
        """Initialize indexing queue and worker"""
        from pipeline import IndexingQueue, IndexingWorker
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
        self.state.start_worker()
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
        from pipeline.embedding_service import EmbeddingService

        max_workers = int(os.getenv('EMBEDDING_WORKERS', '2'))
        max_pending = int(os.getenv('MAX_PENDING_EMBEDDINGS', '6'))
        batch_size = int(os.getenv('EMBEDDING_BATCH_SIZE', '32'))

        return EmbeddingService(
            self.state.core.model,
            self.state.core.vector_store,
            max_workers=max_workers,
            max_pending=max_pending,
            batch_size=batch_size
        )

    def _start_pipeline(self, embedding_service, indexer):
        """Start pipeline coordinator"""
        from pipeline.pipeline_coordinator import PipelineCoordinator

        self.state.indexing.pipeline_coordinator = PipelineCoordinator(
            processor=self.state.core.processor,
            indexer=indexer,
            embedding_service=embedding_service,
            indexing_queue=self.state.indexing.queue  # For mark_complete() callback
        )
        self.state.start_pipeline_coordinator()
        print("Concurrent pipeline started")

    # ============ Sanitization Phase ============

    def _sanitize_before_indexing(self):
        """Sanitization stage: detect and repair issues before new indexing

        Flow:
        1. Resume incomplete files
        2. Detect and repair orphans (files in DB without embeddings)
        3. Self-healing: clean empty documents, backfill chunk counts
        4. Only after repairs complete, allow new file processing
        """
        if not self.state.core.progress_tracker:
            return

        print("\n=== Starting Sanitization Stage ===")
        self._resume_incomplete_files()
        self._repair_orphaned_files()
        self._run_self_healing()
        print("=== Sanitization Complete ===\n")

    def _run_self_healing(self):
        """Run self-healing operations (delete empty docs, backfill counts)"""
        healer = SelfHealingService()
        healer.run()

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

    # ============ Indexing Phase ============

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
        from pipeline import EmbeddingService
        import os
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

    # ============ Background Tasks ============

    def _start_background_indexing(self):
        """Start indexing in background thread"""
        import threading
        thread = threading.Thread(target=self._background_indexing_task, daemon=True)
        thread.start()

    def _background_indexing_task(self):
        """Background task with sanitization stage before indexing

        Flow:
        1. Start watcher (system responsive immediately)
        2. Sanitization: repair orphans from previous runs
        3. Index new files
        4. Post-indexing orphan check: catch orphans created during indexing
        """
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

        # Post-indexing orphan check (catches orphans created during indexing)
        self._check_post_indexing_orphans()

    def _check_post_indexing_orphans(self):
        """Check for orphans created during initial indexing

        This catches orphans that were created during _index_docs() which
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
        self.state.start_watcher()

