"""
Unit tests for main module classes
"""
import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

from main import AppState, app
from operations.model_loader import ModelLoader
from operations.file_walker import FileWalker
from startup.manager import StartupManager
from routes.documents import DocumentLister
from operations.query_executor import QueryExecutor
from models import QueryRequest, QueryResponse
from ingestion import DocumentProcessor
from domain_models import ChunkData


class TestAPIVersion:
    """Tests for API version"""

    def test_api_version_matches_release(self):
        """Test that API version matches the current release version"""
        expected_version = "0.15.0-alpha"
        assert app.version == expected_version, \
            f"API version mismatch: expected {expected_version}, got {app.version}"


class TestAppState:
    """Tests for AppState"""

    def test_init(self):
        """Test initialization"""
        state = AppState()
        assert state.core.model is None
        assert state.core.vector_store is None
        assert state.core.processor is None
        assert state.indexing.queue is None
        assert state.query.cache is None


class TestModelLoader:
    """Tests for ModelLoader"""

    @patch('operations.model_loader.SentenceTransformer')
    def test_load(self, mock_transformer):
        """Test model loading with proper mock"""
        mock_model = Mock()
        mock_transformer.return_value = mock_model

        result = ModelLoader.load("all-MiniLM-L6-v2")

        mock_transformer.assert_called_once_with("all-MiniLM-L6-v2")
        assert result == mock_model


class TestFileWalker:
    """Tests for FileWalker"""

    def test_walk_nonexistent_path(self, tmp_path):
        """Test walking nonexistent path"""
        nonexistent = tmp_path / "nonexistent"
        walker = FileWalker(nonexistent, {'.txt'})

        files = list(walker.walk())
        assert files == []

    def test_walk_empty_directory(self, tmp_path):
        """Test walking empty directory"""
        walker = FileWalker(tmp_path, {'.txt'})

        files = list(walker.walk())
        assert files == []

    def test_walk_with_files(self, tmp_path):
        """Test walking directory with files"""
        # Create test files
        (tmp_path / "file1.txt").write_text("test")
        (tmp_path / "file2.txt").write_text("test")
        (tmp_path / "file3.md").write_text("test")

        walker = FileWalker(tmp_path, {'.txt'})
        files = list(walker.walk())

        assert len(files) == 2

# test_is_supported removed - Metz violation (tests private method)
# Behavior already covered by test_walk_filters_by_extension via public walk()

# Deprecated classes removed: DocumentIndexer and IndexOrchestrator were refactored
# out to pipeline architecture in v0.11+. Tests for these classes have been removed
# to eliminate technical debt.

class TestQueryExecutor:
    """Tests for QueryExecutor"""

    @pytest.fixture
    def mock_components(self):
        """Create mock components"""
        model = Mock()
        vector_store = Mock()
        return model, vector_store

    @pytest.mark.asyncio
    async def test_execute_rejects_empty_query(self, mock_components):
        """execute() should reject empty queries (Metz: test via public interface)"""
        model, store = mock_components
        executor = QueryExecutor(model, store)

        # Empty string
        request = QueryRequest(text="", top_k=5)
        with pytest.raises(ValueError, match="cannot be empty"):
            await executor.execute(request)

        # Whitespace only
        request = QueryRequest(text="   ", top_k=5)
        with pytest.raises(ValueError, match="cannot be empty"):
            await executor.execute(request)

    # test_validate_valid_query removed - no assertion, behavior covered by test_execute_query

    @pytest.mark.asyncio
    async def test_execute_query(self, mock_components):
        """Test query execution (async)"""
        from unittest.mock import AsyncMock

        model, store = mock_components
        executor = QueryExecutor(model, store)

        request = QueryRequest(text="test query", top_k=5)

        # Mock embedding
        mock_embedding = Mock()
        mock_embedding.tolist.return_value = [0.1, 0.2, 0.3]
        model.encode.return_value = mock_embedding

        # Mock async search results
        async def mock_search(*args, **kwargs):
            return [
                {
                    'content': 'result1',
                    'source': 'file1.txt',
                    'page': 1,
                    'score': 0.95
                }
            ]

        store.search = AsyncMock(side_effect=mock_search)

        response = await executor.execute(request)

        assert isinstance(response, QueryResponse)
        assert response.query == "test query"
        assert response.total_results == 1
        assert len(response.results) == 1


class TestDocumentLister:
    """Tests for DocumentLister"""

    @pytest.mark.asyncio
    async def test_list_all(self):
        """Test listing documents (async)"""
        from unittest.mock import AsyncMock

        mock_store = Mock()

        # Create async mock cursor
        async def mock_cursor():
            for row in [('file1.txt', '2025-01-01', 5), ('file2.txt', '2025-01-02', 3)]:
                yield row

        # Mock the async method called by DocumentLister
        mock_store.query_documents_with_chunks = AsyncMock(return_value=mock_cursor())

        lister = DocumentLister(mock_store)
        result = await lister.list_all()

        assert result['total_documents'] == 2
        assert len(result['documents']) == 2
        assert result['documents'][0]['file_path'] == 'file1.txt'
        assert result['documents'][0]['chunk_count'] == 5


# TestStartupManager removed: StartupManager has been heavily refactored in v0.11+
# and is now tested through integration tests. The old test referenced IndexOrchestrator
# which no longer exists.
