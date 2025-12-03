"""Pipeline initialization phase.

Initializes queue, worker, and concurrent pipeline for parallel processing.
"""
import os

from config import default_config


class PipelinePhase:
    """Initializes indexing queue and concurrent pipeline.

    Sets up the background processing infrastructure.
    """

    def __init__(self, state):
        """Initialize with application state.

        Args:
            state: AppState instance to populate with pipeline components
        """
        self.state = state

    def init_queue_and_worker(self):
        """Initialize indexing queue and worker."""
        from pipeline import IndexingQueue, IndexingWorker

        self.state.indexing.queue = IndexingQueue()
        indexer = self.create_indexer()

        # Initialize concurrent pipeline first
        self.init_concurrent_pipeline()

        # Create worker with pipeline coordinator
        self.state.indexing.worker = IndexingWorker(
            self.state.indexing.queue,
            indexer,
            pipeline_coordinator=self.state.indexing.pipeline_coordinator
        )
        self.state.start_worker()
        print("Indexing queue and worker started")

    def init_concurrent_pipeline(self):
        """Initialize concurrent pipeline for parallel processing."""
        if not self.is_pipeline_enabled():
            return

        embedding_service = self.create_embedding_service()
        indexer = self.create_indexer()
        self.start_pipeline(embedding_service, indexer)

    def is_pipeline_enabled(self) -> bool:
        """Check if concurrent pipeline is enabled."""
        enable_pipeline = os.getenv('ENABLE_CONCURRENT_PIPELINE', 'true').lower() == 'true'
        if not enable_pipeline:
            print("Concurrent pipeline disabled")
            self.state.indexing.pipeline_coordinator = None
        return enable_pipeline

    def create_embedding_service(self):
        """Create embedding service with environment config."""
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

    def start_pipeline(self, embedding_service, indexer):
        """Start pipeline coordinator."""
        from pipeline.pipeline_coordinator import PipelineCoordinator

        self.state.indexing.pipeline_coordinator = PipelineCoordinator(
            processor=self.state.core.processor,
            indexer=indexer,
            embedding_service=embedding_service,
            indexing_queue=self.state.indexing.queue  # For mark_complete() callback
        )
        self.state.start_pipeline_coordinator()
        print("Concurrent pipeline started")

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
