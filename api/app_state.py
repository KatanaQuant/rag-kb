

from value_objects import IndexingStats

class CoreServices:
    """Core service dependencies

    Holds fundamental services needed throughout the application.
    Focused on storage, processing, and ML models.

    Hybrid Architecture:
    - vector_store: Sync VectorStore for pipeline workers (background writes)
    - async_vector_store: Async AsyncVectorStore for API routes (non-blocking reads)
    Both use same SQLite database with WAL mode for concurrency.
    """

    def __init__(self):
        self.model = None
        self.vector_store = None  # Sync store for pipeline workers
        self.async_vector_store = None  # Async store for API routes
        self.processor = None
        self.progress_tracker = None

class QueryServices:
    """Query-related services

    Separated from CoreServices to maintain SRP.
    """

    def __init__(self):
        self.cache = None

class IndexingComponents:
    """Indexing queue and worker infrastructure

    Holds components for background indexing and concurrent pipeline.
    """

    def __init__(self):
        self.queue = None
        self.worker = None
        self.pipeline_coordinator = None

class RuntimeState:
    """Runtime state and statistics

    Holds mutable runtime state separate from service dependencies.
    """

    def __init__(self):
        self.watcher = None
        self.indexing_in_progress = False
        self.stats = IndexingStats()

class AppState:
    """Application state container

    Refactored to compose focused state objects instead of holding
    10+ instance variables directly.

    Benefits:
    - Easier to test individual components
    - Clear separation of concerns
    - Follows Sandi Metz < 4 instance variables rule
    - Delegation methods hide internal structure (Law of Demeter)
    """

    def __init__(self):
        self.core = CoreServices()
        self.query = QueryServices()
        self.indexing = IndexingComponents()
        self.runtime = RuntimeState()

    # Delegation methods - Fix Law of Demeter violations
    # Instead of: state.runtime.watcher.stop()
    # Use: state.stop_watcher()

    # === Service Access Delegation (for route handlers) ===

    def get_model(self):
        """Get ML model for embeddings"""
        return self.core.model

    def get_async_vector_store(self):
        """Get async vector store for non-blocking API operations"""
        return self.core.async_vector_store

    def get_vector_store(self):
        """Get sync vector store for pipeline workers"""
        return self.core.vector_store

    def get_query_cache(self):
        """Get query cache"""
        return self.query.cache

    def get_processor(self):
        """Get document processor"""
        return self.core.processor

    def get_progress_tracker(self):
        """Get processing progress tracker"""
        return self.core.progress_tracker

    def get_indexing_queue(self):
        """Get indexing queue"""
        return self.indexing.queue

    def get_pipeline_coordinator(self):
        """Get pipeline coordinator"""
        return self.indexing.pipeline_coordinator

    # === State Access Delegation ===

    def is_indexing_in_progress(self):
        """Check if indexing is currently in progress"""
        return self.runtime.indexing_in_progress

    def set_indexing_in_progress(self, value: bool):
        """Set indexing in progress flag"""
        self.runtime.indexing_in_progress = value

    def get_indexing_stats(self):
        """Get current indexing statistics"""
        return self.runtime.stats

    # === Lifecycle Management Delegation ===

    def stop_watcher(self):
        """Stop file watcher service"""
        if self.runtime.watcher:
            self.runtime.watcher.stop()

    def stop_indexing(self):
        """Stop indexing worker"""
        if self.indexing.worker:
            self.indexing.worker.stop()

    async def close_vector_store(self):
        """Close both sync and async vector store connections"""
        if self.core.vector_store:
            self.core.vector_store.close()  # Sync close
        if self.core.async_vector_store:
            await self.core.async_vector_store.close()  # Async close

    def close_progress_tracker(self):
        """Close progress tracker connection"""
        if self.core.progress_tracker:
            self.core.progress_tracker.close()

    async def close_all_resources(self):
        """Close all resource connections (async for AsyncVectorStore)"""
        await self.close_vector_store()
        self.close_progress_tracker()

    async def get_vector_store_stats(self):
        """Get vector store statistics (async, non-blocking for API routes)"""
        if self.core.async_vector_store:
            return await self.core.async_vector_store.get_stats()
        return {'indexed_documents': 0, 'total_chunks': 0}

    def queue_size(self):
        """Get current queue size"""
        if self.indexing.queue:
            return self.indexing.queue.size()
        return 0

    def is_queue_paused(self):
        """Check if queue is paused"""
        if self.indexing.queue:
            return self.indexing.queue.is_paused()
        return False

    def is_worker_running(self):
        """Check if indexing worker is running"""
        if self.indexing.worker:
            return self.indexing.worker.is_running()
        return False

    # === Startup Lifecycle Delegation ===

    async def initialize_async_vector_store(self):
        """Initialize async vector store connection"""
        if self.core.async_vector_store:
            await self.core.async_vector_store.initialize()

    def start_worker(self):
        """Start indexing worker"""
        if self.indexing.worker:
            self.indexing.worker.start()

    def start_pipeline_coordinator(self):
        """Start pipeline coordinator"""
        if self.indexing.pipeline_coordinator:
            self.indexing.pipeline_coordinator.start()

    def start_watcher(self):
        """Start file watcher service"""
        if self.runtime.watcher:
            self.runtime.watcher.start()
