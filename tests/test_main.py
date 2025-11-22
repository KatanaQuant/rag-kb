"""
Unit tests for main module classes
"""
import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

from main import (
    AppState,
    ModelLoader,
    FileWalker,
    DocumentIndexer,
    IndexOrchestrator,
    QueryExecutor,
    StartupManager,
    DocumentLister,
    app
)
from models import QueryRequest, QueryResponse
from ingestion import DocumentProcessor
from domain_models import ChunkData


class TestAPIVersion:
    """Tests for API version"""

    def test_api_version_matches_release(self):
        """Test that API version matches the current release version"""
        expected_version = "0.11.0"
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

    @patch('main.SentenceTransformer')
    def test_load(self, mock_transformer):
        """Test model loading"""
        mock_model = Mock()
        mock_transformer.return_value = mock_model

        result = ModelLoader.load("test-model")

        mock_transformer.assert_called_once_with("test-model")
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

    def test_is_supported(self, tmp_path):
        """Test file support checking"""
        walker = FileWalker(tmp_path, {'.txt', '.md'})

        txt_file = tmp_path / "test.txt"
        txt_file.write_text("test")

        md_file = tmp_path / "test.md"
        md_file.write_text("test")

        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_text("test")

        assert walker._is_supported(txt_file)
        assert walker._is_supported(md_file)
        assert not walker._is_supported(pdf_file)


class TestDocumentIndexer:
    """Tests for DocumentIndexer"""

    @pytest.fixture
    def mock_components(self):
        """Create mock components"""
        processor = Mock(spec=DocumentProcessor)
        embedding_service = Mock()

        return processor, embedding_service

    def test_init(self, mock_components):
        """Test initialization"""
        processor, embedding_service = mock_components
        indexer = DocumentIndexer(processor, embedding_service)

        assert indexer.processor == processor
        assert indexer.embedding_service == embedding_service

    def test_should_index_force(self, mock_components, tmp_path):
        """Test force indexing"""
        processor, embedding_service = mock_components
        indexer = DocumentIndexer(processor, embedding_service)

        file_path = tmp_path / "test.txt"
        file_path.write_text("test")

        # Force should always return True
        assert indexer._should_index(file_path, force=True)


class TestIndexOrchestrator:
    """Tests for IndexOrchestrator"""

    @pytest.fixture
    def mock_indexer(self):
        """Create mock indexer"""
        return Mock()

    @pytest.fixture
    def mock_processor(self):
        """Create mock processor"""
        proc = Mock()
        proc.SUPPORTED_EXTENSIONS = {'.txt'}
        return proc

    def test_index_all_missing_path(self, mock_indexer, mock_processor, tmp_path):
        """Test indexing nonexistent path"""
        nonexistent = tmp_path / "nonexistent"
        mock_queue = Mock()
        orch = IndexOrchestrator(nonexistent, mock_indexer, mock_processor)

        files, chunks = orch.index_all(mock_queue)
        assert files == 0
        assert chunks == 0

    def test_index_all_empty(self, mock_indexer, mock_processor, tmp_path):
        """Test indexing empty directory"""
        mock_queue = Mock()
        orch = IndexOrchestrator(tmp_path, mock_indexer, mock_processor)

        files, chunks = orch.index_all(mock_queue)
        assert files == 0
        assert chunks == 0

    def test_index_all_success(self, mock_indexer, mock_processor, tmp_path):
        """Test successful indexing"""
        (tmp_path / "file1.txt").write_text("test")
        (tmp_path / "file2.txt").write_text("test")

        mock_queue = Mock()
        mock_queue.add_many = Mock()

        orch = IndexOrchestrator(tmp_path, mock_indexer, mock_processor)
        files, chunks = orch.index_all(mock_queue)

        # Files are queued via add_many(), not directly indexed
        assert files == 2
        assert chunks == 0  # Async processing returns 0
        assert mock_queue.add_many.call_count == 1


class TestQueryExecutor:
    """Tests for QueryExecutor"""

    @pytest.fixture
    def mock_components(self):
        """Create mock components"""
        model = Mock()
        vector_store = Mock()
        return model, vector_store

    def test_validate_empty_query(self, mock_components):
        """Test validation of empty query"""
        model, store = mock_components
        executor = QueryExecutor(model, store)

        with pytest.raises(ValueError, match="cannot be empty"):
            executor._validate("")

        with pytest.raises(ValueError, match="cannot be empty"):
            executor._validate("   ")

    def test_validate_valid_query(self, mock_components):
        """Test validation of valid query"""
        model, store = mock_components
        executor = QueryExecutor(model, store)

        # Should not raise
        executor._validate("valid query")

    def test_execute_query(self, mock_components):
        """Test query execution"""
        model, store = mock_components
        executor = QueryExecutor(model, store)

        request = QueryRequest(text="test query", top_k=5)

        # Mock embedding
        mock_embedding = Mock()
        mock_embedding.tolist.return_value = [0.1, 0.2, 0.3]
        model.encode.return_value = mock_embedding

        # Mock search results
        store.search.return_value = [
            {
                'content': 'result1',
                'source': 'file1.txt',
                'page': 1,
                'score': 0.95
            }
        ]

        response = executor.execute(request)

        assert isinstance(response, QueryResponse)
        assert response.query == "test query"
        assert response.total_results == 1
        assert len(response.results) == 1


class TestDocumentLister:
    """Tests for DocumentLister"""

    def test_list_all(self):
        """Test listing documents"""
        mock_store = Mock()

        # Create a properly iterable mock cursor by making it a list
        mock_cursor = [
            ('file1.txt', '2025-01-01', 5),
            ('file2.txt', '2025-01-02', 3)
        ]

        # Mock the correct method called by DocumentLister
        mock_store.query_documents_with_chunks.return_value = mock_cursor

        lister = DocumentLister(mock_store)
        result = lister.list_all()

        assert result['total_documents'] == 2
        assert len(result['documents']) == 2
        assert result['documents'][0]['file_path'] == 'file1.txt'
        assert result['documents'][0]['chunk_count'] == 5


class TestStartupManager:
    """Tests for StartupManager"""

    @patch('main.ModelLoader')
    @patch('main.VectorStore')
    @patch('main.DocumentProcessor')
    @patch('main.IndexOrchestrator')
    def test_initialize(self, mock_orch, mock_proc, mock_store, mock_loader):
        """Test initialization"""
        state = AppState()
        manager = StartupManager(state)

        # Mock returns
        mock_loader.return_value.load.return_value = Mock()
        mock_store.return_value = Mock()
        mock_proc.return_value = Mock()

        mock_orch_inst = Mock()
        mock_orch_inst.index_all.return_value = (5, 100)
        mock_orch.return_value = mock_orch_inst

        manager.initialize()

        assert state.core.model is not None
        assert state.core.vector_store is not None
        assert state.core.processor is not None
