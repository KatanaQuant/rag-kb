"""Component initialization phase.

Initializes core components: model, stores, processor, cache, reranker.
"""
from config import default_config
from ingestion import DocumentProcessor, VectorStore, ProcessingProgressTracker
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
        """Initialize vector store with unified architecture.

        Unified Architecture (v2.2.3+):
        - Single sync VectorStore with thread-safe locking
        - AsyncVectorStoreAdapter created lazily on first access
        - Eliminates dual-store HNSW corruption issues
        - DELETE operations now work correctly from API
        """
        print("Initializing vector store (unified architecture)...")

        # Initialize single sync store (thread-safe via RLock)
        self.state.core.vector_store = VectorStore()
        print("Vector store initialized (thread-safe, adapter created lazily)")

        # Note: async adapter is created lazily via CoreServices.async_vector_store property

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

    def init_query_expander(self):
        """Initialize LLM-based query expander using Ollama."""
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
