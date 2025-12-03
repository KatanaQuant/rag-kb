"""Component initialization phase.

Initializes core components: model, stores, processor, cache, reranker.
"""
from config import default_config
from ingestion import DocumentProcessor, VectorStore, AsyncVectorStore, ProcessingProgressTracker
from query_cache import QueryCache
from operations.model_loader import ModelLoader


class ComponentPhase:
    """Initializes core application components.

    Handles model loading, vector store setup, and service initialization.
    """

    def __init__(self, state):
        """Initialize with application state.

        Args:
            state: AppState instance to populate with components
        """
        self.state = state

    def load_model(self):
        """Load embedding model."""
        loader = ModelLoader()
        model_name = default_config.model.name
        self.state.core.model = loader.load(model_name)

    async def init_store(self):
        """Initialize both sync and async vector stores.

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
        await self.state.initialize_async_vector_store()
        print("Async vector store initialized (for API routes)")

    def init_progress_tracker(self):
        """Initialize progress tracker."""
        if default_config.processing.enabled:
            db_path = default_config.database.path
            self.state.core.progress_tracker = ProcessingProgressTracker(db_path)
            print("Resumable processing enabled")

    def init_processor(self):
        """Initialize document processor."""
        self.state.core.processor = DocumentProcessor(self.state.core.progress_tracker)

    def init_cache(self):
        """Initialize query cache."""
        if default_config.cache.enabled:
            self.state.query.cache = QueryCache(default_config.cache.max_size)
            print(f"Query cache enabled (size: {default_config.cache.max_size})")
        else:
            print("Query cache disabled")

    def init_reranker(self):
        """Initialize search result reranker from pipeline config."""
        from pipeline.factory import PipelineFactory

        factory = PipelineFactory.default()
        self.state.query.reranker = factory.create_reranker()

        if factory.reranking_enabled:
            print(f"Reranker enabled: {factory.config.reranking.model} (top_n={factory.reranking_top_n})")
        else:
            print("Reranker disabled")
