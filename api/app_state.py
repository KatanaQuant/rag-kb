

from value_objects import IndexingStats

class CoreServices:
    """Core service dependencies

    Holds fundamental services needed throughout the application.
    Focused on storage, processing, and ML models.
    """

    def __init__(self):
        self.model = None
        self.vector_store = None
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

    def stop_watcher(self):
        """Stop file watcher service"""
        if self.runtime.watcher:
            self.runtime.watcher.stop()

    def stop_indexing(self):
        """Stop indexing worker"""
        if self.indexing.worker:
            self.indexing.worker.stop()

    def close_vector_store(self):
        """Close vector store connection"""
        if self.core.vector_store:
            self.core.vector_store.close()

    def close_progress_tracker(self):
        """Close progress tracker connection"""
        if self.core.progress_tracker:
            self.core.progress_tracker.close()

    def close_all_resources(self):
        """Close all resource connections"""
        self.close_vector_store()
        self.close_progress_tracker()

    def get_vector_store_stats(self):
        """Get vector store statistics"""
        if self.core.vector_store:
            return self.core.vector_store.get_stats()
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
