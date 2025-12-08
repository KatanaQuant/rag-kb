"""
Tests for StartupManager behavior.

Metz-compliant tests that verify observable behavior through public interface.
Tests use initialize() and assert on state changes, not implementation details.
"""
import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from pathlib import Path


class TestStartupManagerCreation:
    """Test StartupManager can be instantiated"""

    def test_startup_manager_creation(self, mock_app_state):
        """StartupManager can be created with AppState"""
        from startup.manager import StartupManager
        manager = StartupManager(mock_app_state)
        assert manager.state is mock_app_state

    def test_startup_manager_creates_phase_objects(self, mock_app_state):
        """StartupManager creates phase objects on init"""
        from startup.manager import StartupManager
        manager = StartupManager(mock_app_state)

        # Phase objects should exist (observable state)
        assert manager._config_phase is not None
        assert manager._component_phase is not None
        assert manager._pipeline_phase is not None
        assert manager._sanitization_phase is not None
        assert manager._indexing_phase is not None


class TestStartupManagerInitialize:
    """Test StartupManager.initialize() - the public interface"""

    @pytest.fixture(autouse=True)
    def disable_concurrent_pipeline(self):
        """Disable concurrent pipeline for all tests in this class"""
        with patch.dict('os.environ', {'ENABLE_CONCURRENT_PIPELINE': 'false'}):
            yield

    @pytest.fixture
    def mock_dependencies(self):
        """Mock all external dependencies for integration test"""
        with patch('startup.manager.ConfigValidator') as mock_validator, \
             patch('startup.manager.ModelLoader') as mock_model_loader, \
             patch('startup.manager.DatabaseFactory') as mock_db_factory, \
             patch('startup.manager.DocumentProcessor') as mock_processor, \
             patch('startup.manager.QueryCache') as mock_cache, \
             patch('pipeline.factory.PipelineFactory') as mock_pipeline_factory, \
             patch('startup.manager.default_config') as mock_config, \
             patch('pipeline.IndexingQueue') as mock_queue, \
             patch('pipeline.IndexingWorker') as mock_worker:

            # Configure mock config
            mock_config.processing.enabled = True
            mock_config.cache.enabled = True
            mock_config.cache.max_size = 100
            mock_config.model.name = 'test-model'
            mock_config.watcher.enabled = False
            mock_config.paths.knowledge_base = Path('/test/kb')
            mock_config.database.path = '/test/db'

            # Configure mock model loader
            mock_model = Mock()
            mock_model_loader.return_value.load.return_value = mock_model

            # Configure mock database factory
            mock_store = Mock()
            mock_tracker = Mock()
            # Critical: get_incomplete_files must return [] to prevent len(Mock()) error
            mock_tracker.get_incomplete_files.return_value = []
            mock_db_factory.create_vector_store.return_value = mock_store
            mock_db_factory.create_progress_tracker.return_value = mock_tracker

            # Configure mock pipeline factory
            mock_factory_instance = Mock()
            mock_factory_instance.reranking_enabled = False
            mock_factory_instance.create_reranker.return_value = Mock()
            mock_pipeline_factory.default.return_value = mock_factory_instance

            # Configure mock queue/worker
            mock_queue_instance = Mock()
            mock_queue.return_value = mock_queue_instance

            yield {
                'validator': mock_validator,
                'model_loader': mock_model_loader,
                'db_factory': mock_db_factory,
                'processor': mock_processor,
                'cache': mock_cache,
                'pipeline_factory': mock_pipeline_factory,
                'config': mock_config,
                'model': mock_model,
                'store': mock_store,
                'tracker': mock_tracker,
            }

    @pytest.mark.asyncio
    async def test_initialize_loads_model(self, mock_app_state, mock_dependencies):
        """initialize() should load the embedding model"""
        from startup.manager import StartupManager

        manager = StartupManager(mock_app_state)
        await manager.initialize()

        # Observable state: model is set
        assert mock_app_state.core.model is not None

    @pytest.mark.asyncio
    async def test_initialize_creates_vector_store(self, mock_app_state, mock_dependencies):
        """initialize() should create vector store"""
        from startup.manager import StartupManager

        manager = StartupManager(mock_app_state)
        await manager.initialize()

        # Observable state: vector_store is set
        assert mock_app_state.core.vector_store is not None

    @pytest.mark.asyncio
    async def test_initialize_creates_progress_tracker_when_enabled(
        self, mock_app_state, mock_dependencies
    ):
        """initialize() should create progress tracker when processing enabled"""
        from startup.manager import StartupManager

        mock_dependencies['config'].processing.enabled = True

        manager = StartupManager(mock_app_state)
        await manager.initialize()

        # Observable state: progress_tracker is set
        assert mock_app_state.core.progress_tracker is not None

    @pytest.mark.asyncio
    async def test_initialize_skips_progress_tracker_when_disabled(
        self, mock_app_state, mock_dependencies
    ):
        """initialize() should skip progress tracker when processing disabled"""
        from startup.manager import StartupManager

        mock_dependencies['config'].processing.enabled = False

        manager = StartupManager(mock_app_state)
        # Reset to None to verify it stays None
        mock_app_state.core.progress_tracker = None
        await manager.initialize()

        # Observable state: progress_tracker remains None
        # (DatabaseFactory.create_progress_tracker not called)
        mock_dependencies['db_factory'].create_progress_tracker.assert_not_called()

    @pytest.mark.asyncio
    async def test_initialize_creates_cache_when_enabled(
        self, mock_app_state, mock_dependencies
    ):
        """initialize() should create query cache when enabled"""
        from startup.manager import StartupManager

        mock_dependencies['config'].cache.enabled = True
        mock_dependencies['config'].cache.max_size = 200

        manager = StartupManager(mock_app_state)
        await manager.initialize()

        # Observable state: cache is set
        assert mock_app_state.query.cache is not None

    @pytest.mark.asyncio
    async def test_initialize_skips_cache_when_disabled(
        self, mock_app_state, mock_dependencies
    ):
        """initialize() should skip query cache when disabled"""
        from startup.manager import StartupManager

        mock_dependencies['config'].cache.enabled = False

        manager = StartupManager(mock_app_state)
        mock_app_state.query.cache = None
        await manager.initialize()

        # Observable state: QueryCache constructor not called
        mock_dependencies['cache'].assert_not_called()

    @pytest.mark.asyncio
    async def test_initialize_creates_reranker(self, mock_app_state, mock_dependencies):
        """initialize() should create reranker via PipelineFactory"""
        from startup.manager import StartupManager

        manager = StartupManager(mock_app_state)
        await manager.initialize()

        # Observable state: reranker is set
        assert mock_app_state.query.reranker is not None

    @pytest.mark.asyncio
    async def test_initialize_creates_indexing_queue(self, mock_app_state, mock_dependencies):
        """initialize() should create indexing queue"""
        from startup.manager import StartupManager

        manager = StartupManager(mock_app_state)
        await manager.initialize()

        # Observable state: queue is set
        assert mock_app_state.indexing.queue is not None

    @pytest.mark.asyncio
    async def test_initialize_starts_worker(self, mock_app_state, mock_dependencies):
        """initialize() should start the indexing worker"""
        from startup.manager import StartupManager

        manager = StartupManager(mock_app_state)
        await manager.initialize()

        # Observable state: start_worker was called
        mock_app_state.start_worker.assert_called()

    @pytest.mark.asyncio
    async def test_initialize_validates_config_first(self, mock_app_state, mock_dependencies):
        """initialize() should validate config before other operations"""
        from startup.manager import StartupManager

        manager = StartupManager(mock_app_state)
        await manager.initialize()

        # ConfigValidator should be instantiated and validate called
        mock_dependencies['validator'].assert_called()
        mock_dependencies['validator'].return_value.validate.assert_called()


class TestStartupManagerPipeline:
    """Test concurrent pipeline behavior"""

    @pytest.fixture
    def mock_pipeline_deps(self):
        """Mock pipeline-specific dependencies"""
        with patch('startup.manager.ConfigValidator'), \
             patch('startup.manager.ModelLoader') as mock_loader, \
             patch('startup.manager.DatabaseFactory') as mock_db, \
             patch('startup.manager.DocumentProcessor'), \
             patch('startup.manager.QueryCache'), \
             patch('pipeline.factory.PipelineFactory') as mock_pf, \
             patch('startup.manager.default_config') as mock_cfg, \
             patch('pipeline.IndexingQueue'), \
             patch('pipeline.IndexingWorker'), \
             patch('pipeline.EmbeddingService'), \
             patch('pipeline.pipeline_coordinator.PipelineCoordinator') as mock_coord:

            mock_cfg.processing.enabled = True
            mock_cfg.cache.enabled = False
            mock_cfg.model.name = 'test'
            mock_cfg.watcher.enabled = False
            mock_cfg.paths.knowledge_base = Path('/kb')
            mock_cfg.database.path = '/db'

            mock_loader.return_value.load.return_value = Mock()
            mock_db.create_vector_store.return_value = Mock()
            # Critical: get_incomplete_files must return [] to prevent len(Mock()) error
            mock_tracker = Mock()
            mock_tracker.get_incomplete_files.return_value = []
            mock_db.create_progress_tracker.return_value = mock_tracker

            mock_factory = Mock()
            mock_factory.reranking_enabled = False
            mock_factory.create_reranker.return_value = Mock()
            mock_pf.default.return_value = mock_factory

            yield {'coordinator': mock_coord}

    @pytest.mark.asyncio
    async def test_initialize_starts_pipeline_when_enabled(
        self, mock_app_state, mock_pipeline_deps
    ):
        """initialize() should start concurrent pipeline when enabled"""
        from startup.manager import StartupManager

        with patch.dict('os.environ', {'ENABLE_CONCURRENT_PIPELINE': 'true'}):
            manager = StartupManager(mock_app_state)
            await manager.initialize()

        # Observable state: start_pipeline_coordinator was called
        mock_app_state.start_pipeline_coordinator.assert_called()

    @pytest.mark.asyncio
    async def test_initialize_skips_pipeline_when_disabled(
        self, mock_app_state, mock_pipeline_deps
    ):
        """initialize() should skip concurrent pipeline when disabled"""
        from startup.manager import StartupManager

        with patch.dict('os.environ', {'ENABLE_CONCURRENT_PIPELINE': 'false'}):
            manager = StartupManager(mock_app_state)
            await manager.initialize()

        # Observable state: pipeline_coordinator set to None
        assert mock_app_state.indexing.pipeline_coordinator is None


class TestStartupManagerIntegration:
    """Higher-level integration tests for startup behavior"""

    def test_startup_manager_has_public_initialize_method(self, mock_app_state):
        """StartupManager exposes initialize() as public interface"""
        from startup.manager import StartupManager
        manager = StartupManager(mock_app_state)

        # Public interface should exist
        assert hasattr(manager, 'initialize')
        assert callable(manager.initialize)

    def test_startup_manager_state_accessible_after_creation(self, mock_app_state):
        """StartupManager.state is accessible for inspection"""
        from startup.manager import StartupManager
        manager = StartupManager(mock_app_state)

        # State should be accessible (for testing observable outcomes)
        assert manager.state is mock_app_state
