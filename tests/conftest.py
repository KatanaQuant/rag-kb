"""
Pytest configuration and shared fixtures

Common fixtures used across multiple test files are defined here.
Per Kent Beck TDD: Good fixtures reduce test setup duplication.
"""
import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, AsyncMock

# Add api directory to path for imports
# Detect if running in Docker (./api:/app mount) vs host (./api exists)
api_path = Path(__file__).parent.parent / "api"
if not api_path.exists():
    # Running in Docker where api contents are at /app directly
    api_path = Path(__file__).parent.parent
sys.path.insert(0, str(api_path))


# =============================================================================
# Common Mock Fixtures
# =============================================================================

@pytest.fixture
def mock_app_state():
    """Create mock AppState with all nested attributes.

    Use this fixture when testing components that interact with AppState.
    All nested objects are pre-configured as Mocks.
    """
    state = Mock()

    # Core components
    state.core = Mock()
    state.core.model = Mock()
    state.core.vector_store = Mock()
    state.core.async_vector_store = Mock()
    state.core.progress_tracker = Mock()
    state.core.processor = Mock()

    # Query components
    state.query = Mock()
    state.query.cache = Mock()
    state.query.reranker = Mock()

    # Indexing components
    state.indexing = Mock()
    state.indexing.queue = Mock()
    state.indexing.worker = Mock()
    state.indexing.pipeline_coordinator = Mock()

    # Runtime components
    state.runtime = Mock()
    state.runtime.watcher = Mock()
    state.runtime.stats = None
    state.runtime.indexing_in_progress = False

    # Common methods
    state.start_worker = Mock()
    state.start_pipeline_coordinator = Mock()
    state.start_watcher = Mock()
    state.initialize_async_vector_store = AsyncMock()
    state.get_model = Mock(return_value=state.core.model)
    state.get_vector_store = Mock(return_value=state.core.vector_store)
    state.get_async_vector_store = Mock(return_value=state.core.async_vector_store)
    state.get_query_cache = Mock(return_value=state.query.cache)

    return state


@pytest.fixture
def mock_config():
    """Create mock default_config with common settings.

    Use this fixture when testing components that read from config.
    """
    config = Mock()

    # Model config
    config.model = Mock()
    config.model.name = "test-model"

    # Database config
    config.database = Mock()
    config.database.path = "/tmp/test_db.sqlite"

    # Paths config
    config.paths = Mock()
    config.paths.knowledge_base = Path("/tmp/test_kb")
    config.paths.data = Path("/tmp/test_data")

    # Processing config
    config.processing = Mock()
    config.processing.enabled = True

    # Cache config
    config.cache = Mock()
    config.cache.enabled = True
    config.cache.max_size = 100

    # Watcher config
    config.watcher = Mock()
    config.watcher.enabled = True
    config.watcher.debounce_seconds = 1.0
    config.watcher.batch_size = 10

    # File validation config
    config.file_validation = Mock()
    config.file_validation.enabled = True
    config.file_validation.action = "warn"

    return config


# =============================================================================
# Database Fixtures
# =============================================================================

@pytest.fixture
def temp_db_path(tmp_path):
    """Create a temporary database path.

    Use this for tests that need an isolated database.
    """
    return tmp_path / "test.sqlite"


@pytest.fixture
def temp_kb_path(tmp_path):
    """Create a temporary knowledge base directory.

    Use this for tests that need a writable KB directory.
    """
    kb_path = tmp_path / "knowledge_base"
    kb_path.mkdir(parents=True, exist_ok=True)
    return kb_path


# =============================================================================
# Test Data Fixtures
# =============================================================================

@pytest.fixture
def sample_chunks():
    """Sample chunk data for testing chunking/embedding operations."""
    return [
        "This is the first test chunk with some content.",
        "This is the second test chunk with different content.",
        "This is the third test chunk with more varied content."
    ]


@pytest.fixture
def sample_document_metadata():
    """Sample document metadata for testing."""
    return {
        "file_path": "/test/path/document.pdf",
        "file_name": "document.pdf",
        "file_type": "pdf",
        "indexed_at": "2025-01-01T00:00:00",
        "chunk_count": 5
    }
