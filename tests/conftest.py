"""
Pytest configuration and shared fixtures

Common fixtures used across multiple test files are defined here.
Per Kent Beck TDD: Good fixtures reduce test setup duplication.
"""
import os
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
# Environment Detection Helpers
# =============================================================================

def is_docker_environment():
    """Check if running inside Docker container."""
    return Path('/.dockerenv').exists() or Path('/run/.containerenv').exists()


skip_if_not_docker = pytest.mark.skipif(
    not is_docker_environment(),
    reason="Test requires Docker environment"
)


def has_sqlite_vec():
    """Check if sqlite-vec extension is available."""
    try:
        import sqlite_vec
        return True
    except ImportError:
        return False


skip_if_no_sqlite_vec = pytest.mark.skipif(
    not has_sqlite_vec(),
    reason="sqlite-vec extension not available"
)


def _huggingface_cache_accessible():
    """Check if HuggingFace cache directory is accessible."""
    cache_dir = os.path.expanduser("~/.cache/huggingface/hub")
    try:
        # Check if we can create/write to the cache directory
        os.makedirs(cache_dir, exist_ok=True)
        test_file = os.path.join(cache_dir, ".write_test")
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
        return True
    except (PermissionError, OSError):
        return False


requires_huggingface = pytest.mark.skipif(
    not _huggingface_cache_accessible(),
    reason="HuggingFace cache not accessible"
)


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
    # Configure progress_tracker to return empty list for background tasks
    state.core.progress_tracker.get_incomplete_files = Mock(return_value=[])
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


@pytest.fixture
def mock_database_factory():
    """Mock DatabaseFactory for tests that don't need real database.

    Use this fixture when testing components that use DatabaseFactory.
    All factory methods return pre-configured mocks.
    """
    from unittest.mock import patch, MagicMock

    mock_store = MagicMock()
    mock_store.is_document_indexed.return_value = False
    mock_store.search.return_value = []
    mock_store.get_stats.return_value = {'indexed_documents': 0, 'total_chunks': 0}
    mock_store.delete_document.return_value = {'found': True, 'document_deleted': True}
    mock_store.close.return_value = None

    mock_conn = MagicMock()
    mock_conn.connect.return_value = MagicMock()
    mock_conn.close.return_value = None

    mock_tracker = MagicMock()
    mock_tracker.get_status.return_value = None
    mock_tracker.get_incomplete.return_value = []
    mock_tracker.start_processing.return_value = None

    with patch('ingestion.database_factory.DatabaseFactory') as MockFactory:
        MockFactory.detect_backend.return_value = 'sqlite'
        MockFactory.create_vector_store.return_value = mock_store
        MockFactory.create_connection.return_value = mock_conn
        MockFactory.create_progress_tracker.return_value = mock_tracker

        yield {
            'factory': MockFactory,
            'vector_store': mock_store,
            'connection': mock_conn,
            'progress_tracker': mock_tracker,
        }


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


# =============================================================================
# Maintenance Test Fixtures
# =============================================================================

@pytest.fixture
def maintenance_client():
    """Create test client for maintenance endpoint tests."""
    from main import app
    from fastapi.testclient import TestClient
    client = TestClient(app)
    yield client


@pytest.fixture
def temp_db_full(tmp_path):
    """Create temporary SQLite database with full schema (documents + chunks + processing_progress).

    Use this for maintenance tests that need the complete database schema.
    """
    import sqlite3
    import tempfile

    fd, path = tempfile.mkstemp(suffix='.db')
    conn = sqlite3.connect(path)

    conn.execute('''
        CREATE TABLE documents (
            id INTEGER PRIMARY KEY,
            file_path TEXT,
            indexed_at TIMESTAMP
        )
    ''')
    conn.execute('''
        CREATE TABLE chunks (
            id INTEGER PRIMARY KEY,
            document_id INTEGER,
            content TEXT,
            FOREIGN KEY (document_id) REFERENCES documents(id)
        )
    ''')
    conn.execute('''
        CREATE TABLE processing_progress (
            file_path TEXT PRIMARY KEY,
            status TEXT
        )
    ''')
    conn.commit()
    conn.close()

    yield path

    os.close(fd)
    os.unlink(path)


@pytest.fixture
def temp_db_with_fts(tmp_path):
    """Create temporary SQLite database with FTS schema.

    Use this for maintenance tests that need FTS5 virtual tables.
    """
    import sqlite3
    import tempfile

    fd, path = tempfile.mkstemp(suffix='.db')
    conn = sqlite3.connect(path)

    conn.execute('''
        CREATE TABLE documents (
            id INTEGER PRIMARY KEY,
            file_path TEXT UNIQUE,
            indexed_at TIMESTAMP
        )
    ''')
    conn.execute('''
        CREATE TABLE chunks (
            id INTEGER PRIMARY KEY,
            document_id INTEGER,
            content TEXT,
            FOREIGN KEY (document_id) REFERENCES documents(id)
        )
    ''')
    conn.execute('''
        CREATE VIRTUAL TABLE fts_chunks USING fts5(content, chunk_id UNINDEXED)
    ''')
    conn.commit()
    conn.close()

    yield path

    os.close(fd)
    os.unlink(path)


@pytest.fixture
def temp_db_progress():
    """Create temporary SQLite database with full processing_progress schema.

    Use this for resumable processing and rejection tracking tests.
    """
    import sqlite3
    import tempfile

    fd, path = tempfile.mkstemp(suffix='.db')
    conn = sqlite3.connect(path)

    conn.execute('''
        CREATE TABLE processing_progress (
            file_path TEXT PRIMARY KEY,
            file_hash TEXT,
            total_chunks INTEGER DEFAULT 0,
            chunks_processed INTEGER DEFAULT 0,
            status TEXT DEFAULT 'in_progress',
            last_chunk_end INTEGER DEFAULT 0,
            error_message TEXT,
            started_at TEXT,
            last_updated TEXT,
            completed_at TEXT
        )
    ''')
    conn.commit()
    conn.close()

    yield path

    os.close(fd)
    os.unlink(path)


@pytest.fixture
def temp_db_minimal():
    """Create temporary SQLite database with documents + chunks only.

    Use this for tests that only need document/chunk tables.
    """
    import sqlite3
    import tempfile

    fd, path = tempfile.mkstemp(suffix='.db')
    conn = sqlite3.connect(path)

    conn.execute('''
        CREATE TABLE documents (
            id INTEGER PRIMARY KEY,
            file_path TEXT UNIQUE,
            indexed_at TIMESTAMP
        )
    ''')
    conn.execute('''
        CREATE TABLE chunks (
            id INTEGER PRIMARY KEY,
            document_id INTEGER,
            content TEXT,
            FOREIGN KEY (document_id) REFERENCES documents(id)
        )
    ''')
    conn.commit()
    conn.close()

    yield path

    os.close(fd)
    os.unlink(path)
