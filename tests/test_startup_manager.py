"""
Tests for StartupManager behavior.

These tests verify the initialization phases of StartupManager
to establish a safety net before refactoring (per Kent Beck TDD).
"""
import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from pathlib import Path


class TestStartupManagerInitialization:
    """Test StartupManager initialization phases"""

    @pytest.fixture
    def mock_app_state(self):
        """Create mock AppState with nested attributes"""
        state = Mock()
        state.core = Mock()
        state.core.model = None
        state.core.vector_store = None
        state.core.async_vector_store = None
        state.core.progress_tracker = None
        state.core.processor = None
        state.query = Mock()
        state.query.cache = None
        state.query.reranker = None
        state.indexing = Mock()
        state.indexing.queue = None
        state.indexing.worker = None
        state.indexing.pipeline_coordinator = None
        state.runtime = Mock()
        state.runtime.watcher = None
        state.runtime.stats = None
        state.runtime.indexing_in_progress = False
        state.start_worker = Mock()
        state.start_pipeline_coordinator = Mock()
        state.start_watcher = Mock()
        state.initialize_async_vector_store = AsyncMock()
        return state

    @pytest.fixture
    def startup_manager(self, mock_app_state):
        """Create StartupManager with mocked state"""
        from startup.manager import StartupManager
        return StartupManager(mock_app_state)

    def test_startup_manager_creation(self, mock_app_state):
        """Test that StartupManager can be created with AppState"""
        from startup.manager import StartupManager
        manager = StartupManager(mock_app_state)
        assert manager.state is mock_app_state

    def test_validate_config_calls_validator(self, startup_manager):
        """Test that _validate_config uses ConfigValidator"""
        with patch('startup.manager.ConfigValidator') as mock_validator_class:
            mock_validator = Mock()
            mock_validator_class.return_value = mock_validator

            startup_manager._validate_config()

            mock_validator_class.assert_called_once()
            mock_validator.validate.assert_called_once()

    def test_load_model_uses_model_loader(self, startup_manager, mock_app_state):
        """Test that _load_model uses ModelLoader and sets state.core.model"""
        with patch('startup.manager.ModelLoader') as mock_loader_class:
            mock_loader = Mock()
            mock_model = Mock()
            mock_loader.load.return_value = mock_model
            mock_loader_class.return_value = mock_loader

            with patch('startup.manager.default_config') as mock_config:
                mock_config.model.name = 'test-model'
                startup_manager._load_model()

            mock_loader.load.assert_called_once_with('test-model')
            assert mock_app_state.core.model == mock_model

    @pytest.mark.asyncio
    async def test_init_store_creates_both_stores(self, startup_manager, mock_app_state):
        """Test that _init_store creates sync and async vector stores"""
        with patch('startup.manager.VectorStore') as mock_sync_store:
            with patch('startup.manager.AsyncVectorStore') as mock_async_store:
                mock_sync = Mock()
                mock_async = Mock()
                mock_sync_store.return_value = mock_sync
                mock_async_store.return_value = mock_async

                await startup_manager._init_store()

                mock_sync_store.assert_called_once()
                mock_async_store.assert_called_once()
                assert mock_app_state.core.vector_store == mock_sync
                assert mock_app_state.core.async_vector_store == mock_async
                mock_app_state.initialize_async_vector_store.assert_called_once()

    def test_init_progress_tracker_when_enabled(self, startup_manager, mock_app_state):
        """Test that progress tracker is created when processing is enabled"""
        with patch('startup.manager.default_config') as mock_config:
            mock_config.processing.enabled = True
            mock_config.database.path = '/test/db/path'

            with patch('startup.manager.ProcessingProgressTracker') as mock_tracker_class:
                mock_tracker = Mock()
                mock_tracker_class.return_value = mock_tracker

                startup_manager._init_progress_tracker()

                mock_tracker_class.assert_called_once_with('/test/db/path')
                assert mock_app_state.core.progress_tracker == mock_tracker

    def test_init_progress_tracker_when_disabled(self, startup_manager, mock_app_state):
        """Test that progress tracker is not created when processing is disabled"""
        with patch('startup.manager.default_config') as mock_config:
            mock_config.processing.enabled = False

            with patch('startup.manager.ProcessingProgressTracker') as mock_tracker_class:
                startup_manager._init_progress_tracker()

                mock_tracker_class.assert_not_called()

    def test_init_processor_creates_document_processor(self, startup_manager, mock_app_state):
        """Test that _init_processor creates DocumentProcessor with tracker"""
        mock_tracker = Mock()
        mock_app_state.core.progress_tracker = mock_tracker

        with patch('startup.manager.DocumentProcessor') as mock_processor_class:
            mock_processor = Mock()
            mock_processor_class.return_value = mock_processor

            startup_manager._init_processor()

            mock_processor_class.assert_called_once_with(mock_tracker)
            assert mock_app_state.core.processor == mock_processor

    def test_init_cache_when_enabled(self, startup_manager, mock_app_state):
        """Test that query cache is created when enabled"""
        with patch('startup.manager.default_config') as mock_config:
            mock_config.cache.enabled = True
            mock_config.cache.max_size = 100

            with patch('startup.manager.QueryCache') as mock_cache_class:
                mock_cache = Mock()
                mock_cache_class.return_value = mock_cache

                startup_manager._init_cache()

                mock_cache_class.assert_called_once_with(100)
                assert mock_app_state.query.cache == mock_cache

    def test_init_cache_when_disabled(self, startup_manager, mock_app_state):
        """Test that query cache is not created when disabled"""
        with patch('startup.manager.default_config') as mock_config:
            mock_config.cache.enabled = False

            with patch('startup.manager.QueryCache') as mock_cache_class:
                startup_manager._init_cache()

                mock_cache_class.assert_not_called()
                # Cache should remain None when disabled
                assert mock_app_state.query.cache is None

    def test_init_reranker_uses_pipeline_factory(self, startup_manager, mock_app_state):
        """Test that _init_reranker uses PipelineFactory"""
        with patch('pipeline.factory.PipelineFactory') as mock_factory_class:
            mock_factory = Mock()
            mock_reranker = Mock()
            mock_factory.create_reranker.return_value = mock_reranker
            mock_factory.reranking_enabled = True
            mock_factory.config.reranking.model = 'test-reranker'
            mock_factory.reranking_top_n = 10
            mock_factory_class.default.return_value = mock_factory

            startup_manager._init_reranker()

            mock_factory_class.default.assert_called_once()
            mock_factory.create_reranker.assert_called_once()
            assert mock_app_state.query.reranker == mock_reranker


class TestStartupManagerSanitization:
    """Test StartupManager sanitization phases"""

    @pytest.fixture
    def mock_app_state(self):
        """Create mock AppState"""
        state = Mock()
        state.core = Mock()
        state.core.progress_tracker = Mock()
        state.core.vector_store = Mock()
        state.indexing = Mock()
        state.indexing.queue = Mock()
        return state

    @pytest.fixture
    def startup_manager(self, mock_app_state):
        """Create StartupManager with mocked state"""
        from startup.manager import StartupManager
        return StartupManager(mock_app_state)

    def test_detect_orphans_uses_orphan_detector(self, startup_manager, mock_app_state):
        """Test that _detect_orphans uses OrphanDetector"""
        with patch('startup.manager.OrphanDetector') as mock_detector_class:
            mock_detector = Mock()
            mock_orphans = ['/path/to/orphan1', '/path/to/orphan2']
            mock_detector.detect_orphans.return_value = mock_orphans
            mock_detector_class.return_value = mock_detector

            result = startup_manager._detect_orphans()

            mock_detector_class.assert_called_once_with(
                mock_app_state.core.progress_tracker,
                mock_app_state.core.vector_store
            )
            mock_detector.detect_orphans.assert_called_once()
            assert result == mock_orphans

    def test_run_self_healing_uses_service(self, startup_manager):
        """Test that _run_self_healing uses SelfHealingService"""
        with patch('startup.manager.SelfHealingService') as mock_healer_class:
            mock_healer = Mock()
            mock_healer_class.return_value = mock_healer

            startup_manager._run_self_healing()

            mock_healer_class.assert_called_once()
            mock_healer.run.assert_called_once()

    def test_sanitize_before_indexing_skips_when_no_tracker(self, startup_manager, mock_app_state):
        """Test that sanitization is skipped when progress_tracker is None"""
        mock_app_state.core.progress_tracker = None

        with patch.object(startup_manager, '_resume_incomplete_files') as mock_resume:
            with patch.object(startup_manager, '_repair_orphaned_files') as mock_repair:
                startup_manager._sanitize_before_indexing()

                mock_resume.assert_not_called()
                mock_repair.assert_not_called()

    def test_sanitize_before_indexing_runs_all_stages(self, startup_manager, mock_app_state):
        """Test that sanitization runs all stages when tracker exists"""
        mock_app_state.core.progress_tracker = Mock()

        with patch.object(startup_manager, '_resume_incomplete_files') as mock_resume:
            with patch.object(startup_manager, '_repair_orphaned_files') as mock_repair:
                with patch.object(startup_manager, '_run_self_healing') as mock_heal:
                    startup_manager._sanitize_before_indexing()

                    mock_resume.assert_called_once()
                    mock_repair.assert_called_once()
                    mock_heal.assert_called_once()


class TestStartupManagerIndexing:
    """Test StartupManager indexing phases"""

    @pytest.fixture
    def mock_app_state(self):
        """Create mock AppState"""
        state = Mock()
        state.core = Mock()
        state.core.model = Mock()
        state.core.vector_store = Mock()
        state.core.processor = Mock()
        state.core.progress_tracker = Mock()
        state.indexing = Mock()
        state.indexing.queue = Mock()
        state.runtime = Mock()
        state.runtime.stats = None
        state.runtime.indexing_in_progress = False
        return state

    @pytest.fixture
    def startup_manager(self, mock_app_state):
        """Create StartupManager with mocked state"""
        from startup.manager import StartupManager
        return StartupManager(mock_app_state)

    def test_create_orchestrator_returns_orchestrator(self, startup_manager, mock_app_state):
        """Test that _create_orchestrator returns IndexOrchestrator"""
        with patch('startup.manager.default_config') as mock_config:
            mock_config.paths.knowledge_base = Path('/test/kb')

            with patch('startup.manager.IndexOrchestrator') as mock_orch_class:
                with patch.object(startup_manager, '_create_indexer') as mock_create_indexer:
                    mock_indexer = Mock()
                    mock_create_indexer.return_value = mock_indexer
                    mock_orchestrator = Mock()
                    mock_orch_class.return_value = mock_orchestrator

                    result = startup_manager._create_orchestrator()

                    mock_orch_class.assert_called_once()
                    assert result == mock_orchestrator

    def test_is_pipeline_enabled_default_true(self, startup_manager, mock_app_state):
        """Test that pipeline is enabled by default"""
        with patch.dict('os.environ', {}, clear=True):
            with patch('startup.manager.os.getenv', return_value='true'):
                result = startup_manager._is_pipeline_enabled()
                assert result is True

    def test_is_pipeline_enabled_can_be_disabled(self, startup_manager, mock_app_state):
        """Test that pipeline can be disabled via environment"""
        with patch('startup.manager.os.getenv', return_value='false'):
            result = startup_manager._is_pipeline_enabled()
            assert result is False
            assert mock_app_state.indexing.pipeline_coordinator is None


class TestStartupManagerWatcher:
    """Test StartupManager file watcher initialization"""

    @pytest.fixture
    def mock_app_state(self):
        """Create mock AppState"""
        state = Mock()
        state.runtime = Mock()
        state.runtime.watcher = None
        state.indexing = Mock()
        state.indexing.queue = Mock()
        state.start_watcher = Mock()
        return state

    @pytest.fixture
    def startup_manager(self, mock_app_state):
        """Create StartupManager with mocked state"""
        from startup.manager import StartupManager
        return StartupManager(mock_app_state)

    def test_start_watcher_when_enabled(self, startup_manager, mock_app_state):
        """Test that watcher is started when enabled"""
        with patch('startup.manager.default_config') as mock_config:
            mock_config.watcher.enabled = True
            mock_config.paths.knowledge_base = Path('/test/kb')
            mock_config.watcher.debounce_seconds = 1.0
            mock_config.watcher.batch_size = 10

            with patch('startup.manager.FileWatcherService') as mock_watcher_class:
                mock_watcher = Mock()
                mock_watcher_class.return_value = mock_watcher

                startup_manager._start_watcher()

                mock_watcher_class.assert_called_once()
                assert mock_app_state.runtime.watcher == mock_watcher
                mock_app_state.start_watcher.assert_called_once()

    def test_start_watcher_when_disabled(self, startup_manager, mock_app_state):
        """Test that watcher is not started when disabled"""
        with patch('startup.manager.default_config') as mock_config:
            mock_config.watcher.enabled = False

            with patch('startup.manager.FileWatcherService') as mock_watcher_class:
                startup_manager._start_watcher()

                mock_watcher_class.assert_not_called()
                mock_app_state.start_watcher.assert_not_called()
