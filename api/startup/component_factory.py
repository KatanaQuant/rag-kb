"""Component factory for creating application objects"""

import os
from config import default_config
from ingestion.database_factory import DatabaseFactory
from query_cache import QueryCache

class ComponentFactory:
    """Creates application components

    Design principles:
    - Single responsibility: object creation
    - Small methods (< 5 lines each)
    - Dependency injection pattern
    """

    def __init__(self, state):
        self.state = state

    def create_progress_tracker(self):
        """Create progress tracker if enabled, using factory for backend detection."""
        if not default_config.processing.enabled:
            return None
        return DatabaseFactory.create_progress_tracker()

    def create_query_cache(self):
        """Create query cache if enabled"""
        if not default_config.cache.enabled:
            return None
        return QueryCache(default_config.cache.max_size)

    def create_indexer(self):
        """Create document indexer"""
        from pipeline import EmbeddingService
        embedding_service = self._create_embedding_service()
        from main import DocumentIndexer
        return DocumentIndexer(self.state.processor, embedding_service)

    def _create_embedding_service(self):
        """Create embedding service"""
        from pipeline import EmbeddingService
        workers = self._get_embedding_workers()
        max_pending = self._get_max_pending(workers)
        return EmbeddingService(
            model=self.state.model,
            vector_store=self.state.vector_store,
            max_workers=workers,
            max_pending=max_pending,
            processor=self.state.processor
        )

    def _get_embedding_workers(self) -> int:
        """Get number of embedding workers"""
        return int(os.getenv('EMBEDDING_WORKERS', '2'))

    def _get_max_pending(self, workers: int) -> int:
        """Get max pending embeddings"""
        default_val = str(workers * 2)
        return int(os.getenv('MAX_PENDING_EMBEDDINGS', default_val))

    def create_orchestrator(self):
        """Create indexing orchestrator"""
        from main import IndexOrchestrator
        indexer = self.create_indexer()
        kb_path = default_config.paths.knowledge_base
        return IndexOrchestrator(
            kb_path,
            indexer,
            self.state.processor,
            self.state.progress_tracker
        )

    def create_watcher(self):
        """Create file watcher"""
        if not default_config.watcher.enabled:
            return None
        from watcher import FileWatcherService
        indexer = self.create_indexer()
        return FileWatcherService(
            watch_path=default_config.paths.knowledge_base,
            indexer=indexer,
            debounce_seconds=default_config.watcher.debounce_seconds,
            batch_size=default_config.watcher.batch_size
        )
