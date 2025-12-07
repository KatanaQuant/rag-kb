

from value_objects import IndexingStats

class CoreServices:
    """Core service dependencies

    Holds fundamental services needed throughout the application.
    Focused on storage, processing, and ML models.

    Unified Architecture (v2.2.3+):
    - vector_store: Single sync VectorStore for all operations
    - async_vector_store: AsyncVectorStoreAdapter wrapping vector_store for non-blocking API

    The adapter pattern eliminates dual-store issues where AsyncVectorStore was
    read-only to prevent HNSW corruption. Now DELETE works correctly from API.
    """

    def __init__(self):
        self.model = None
        self.vector_store = None  # Single sync store (thread-safe via RLock)
        self._async_adapter = None  # Lazy-created adapter for async API access
        self.processor = None
        self.progress_tracker = None

    @property
    def async_vector_store(self):
        """Get async adapter for vector store (lazy creation).

        Returns AsyncVectorStoreAdapter wrapping the sync VectorStore.
        This provides non-blocking async interface for API routes while
        using the same underlying store for thread-safe operations.
        """
        if self._async_adapter is None and self.vector_store is not None:
            from ingestion.async_adapter import AsyncVectorStoreAdapter
            self._async_adapter = AsyncVectorStoreAdapter(self.vector_store)
        return self._async_adapter

    @async_vector_store.setter
    def async_vector_store(self, value):
        """Set async vector store (for backward compatibility during transition).

        Note: In unified architecture, this setter is not typically used.
        The adapter is created lazily from vector_store.
        """
        self._async_adapter = value

class QueryServices:
    """Query-related services

    Separated from CoreServices to maintain SRP.
    """

    def __init__(self):
        self.cache = None
        self.reranker = None
        self.query_expander = None  # LLM-based query expansion via Ollama

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
    - Follows <4 instance variables principle
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

    def get_reranker(self):
        """Get search result reranker"""
        return self.query.reranker

    def get_query_expander(self):
        """Get LLM-based query expander"""
        return self.query.query_expander

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
        """Close vector store connection.

        Unified Architecture: Only close the sync store. The async adapter
        is just a wrapper and doesn't own the connection.
        """
        if self.core.vector_store:
            self.core.vector_store.close()  # Only sync store needs closing
        # Adapter close is a no-op - it doesn't own the connection

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
        """Initialize async vector store connection.

        Unified Architecture: This is now a no-op since the adapter is
        lazily created and doesn't need initialization.
        Kept for backward compatibility with existing startup code.
        """
        # No-op in unified architecture - adapter is created lazily
        pass

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

    # === Queue Operations (Fix Law of Demeter in routes) ===

    def add_to_queue(self, path, priority=None, force: bool = False):
        """Add file to indexing queue.

        Fixes Law of Demeter: routes call this instead of
        app_state.indexing.queue.add()
        """
        if self.indexing.queue:
            self.indexing.queue.add(path, priority=priority, force=force)

    def add_many_to_queue(self, paths, priority=None, force: bool = False):
        """Add multiple files to indexing queue."""
        if self.indexing.queue:
            self.indexing.queue.add_many(paths, priority=priority, force=force)

    def pause_queue(self):
        """Pause indexing queue."""
        if self.indexing.queue:
            self.indexing.queue.pause()

    def resume_queue(self):
        """Resume indexing queue."""
        if self.indexing.queue:
            self.indexing.queue.resume()

    def clear_queue(self):
        """Clear indexing queue."""
        if self.indexing.queue:
            self.indexing.queue.clear()

    def get_pipeline_stats(self) -> dict:
        """Get pipeline coordinator statistics.

        Fixes Law of Demeter: routes call this instead of
        app_state.indexing.pipeline_coordinator.get_stats()
        """
        if self.indexing.pipeline_coordinator:
            return self.indexing.pipeline_coordinator.get_stats()
        return {'queue_sizes': {}, 'active_jobs': {}, 'workers_running': {}}
