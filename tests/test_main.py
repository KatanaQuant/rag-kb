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
    DocumentLister
)
from models import QueryRequest, QueryResponse
from ingestion import DocumentProcessor
from domain_models import ChunkData


class TestAppState:
    """Tests for AppState"""

    def test_init(self):
        """Test initialization"""
        state = AppState()
        assert state.model is None
        assert state.vector_store is None
        assert state.processor is None


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
        model = Mock()
        vector_store = Mock()

        return processor, model, vector_store

    def test_init(self, mock_components):
        """Test initialization"""
        processor, model, store = mock_components
        indexer = DocumentIndexer(processor, model, store)

        assert indexer.processor == processor
        assert indexer.model == model
        assert indexer.store == store

    def test_should_index_force(self, mock_components, tmp_path):
        """Test force indexing"""
        processor, model, store = mock_components
        indexer = DocumentIndexer(processor, model, store)

        file_path = tmp_path / "test.txt"
        file_path.write_text("test")

        # Force should always return True
        assert indexer._should_index(file_path, force=True)

    def test_should_index_not_indexed(self, mock_components, tmp_path):
        """Test indexing new file"""
        processor, model, store = mock_components
        indexer = DocumentIndexer(processor, model, store)

        file_path = tmp_path / "test.txt"
        file_path.write_text("test")

        processor.get_file_hash.return_value = "hash123"
        store.is_document_indexed.return_value = False

        assert indexer._should_index(file_path, force=False)

    def test_should_index_already_indexed(self, mock_components, tmp_path):
        """Test skipping already indexed file"""
        processor, model, store = mock_components
        indexer = DocumentIndexer(processor, model, store)

        file_path = tmp_path / "test.txt"
        file_path.write_text("test")

        processor.get_file_hash.return_value = "hash123"
        store.is_document_indexed.return_value = True

        assert not indexer._should_index(file_path, force=False)

    def test_index_file_skip(self, mock_components, tmp_path):
        """Test skipping file"""
        processor, model, store = mock_components
        indexer = DocumentIndexer(processor, model, store)

        file_path = tmp_path / "test.txt"
        file_path.write_text("test")

        processor.get_file_hash.return_value = "hash123"
        store.is_document_indexed.return_value = True

        result = indexer.index_file(file_path, force=False)
        assert result == 0

    def test_index_file_success(self, mock_components, tmp_path):
        """Test successful indexing"""
        processor, model, store = mock_components
        indexer = DocumentIndexer(processor, model, store)

        file_path = tmp_path / "test.txt"
        file_path.write_text("test")

        processor.get_file_hash.return_value = "hash123"
        store.is_document_indexed.return_value = False
        processor.process_file.return_value = [
            {'content': 'chunk1'},
            {'content': 'chunk2'}
        ]

        # Mock embeddings with .tolist() method
        mock_emb1 = Mock()
        mock_emb1.tolist.return_value = [0.1]
        mock_emb2 = Mock()
        mock_emb2.tolist.return_value = [0.2]
        model.encode.return_value = [mock_emb1, mock_emb2]

        result = indexer.index_file(file_path, force=True)
        assert result == 2

    def test_gen_embeddings(self, mock_components):
        """Test embedding generation"""
        processor, model, store = mock_components
        indexer = DocumentIndexer(processor, model, store)

        chunks = [
            {'content': 'text1'},
            {'content': 'text2'}
        ]

        mock_emb = Mock()
        mock_emb.tolist.side_effect = [[0.1, 0.2], [0.3, 0.4]]
        model.encode.return_value = [mock_emb, mock_emb]

        embeddings = indexer._gen_embeddings(chunks)

        model.encode.assert_called_once()
        assert len(embeddings) == 2


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
        orch = IndexOrchestrator(nonexistent, mock_indexer, mock_processor)

        files, chunks = orch.index_all()
        assert files == 0
        assert chunks == 0

    def test_index_all_empty(self, mock_indexer, mock_processor, tmp_path):
        """Test indexing empty directory"""
        orch = IndexOrchestrator(tmp_path, mock_indexer, mock_processor)

        files, chunks = orch.index_all()
        assert files == 0
        assert chunks == 0

    def test_index_all_success(self, mock_indexer, mock_processor, tmp_path):
        """Test successful indexing"""
        (tmp_path / "file1.txt").write_text("test")
        (tmp_path / "file2.txt").write_text("test")

        mock_indexer.index_file.return_value = 5

        orch = IndexOrchestrator(tmp_path, mock_indexer, mock_processor)
        files, chunks = orch.index_all()

        assert files == 2
        assert chunks == 10  # 2 files * 5 chunks each


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
        mock_cursor = [
            ('file1.txt', '2025-01-01', 5),
            ('file2.txt', '2025-01-02', 3)
        ]

        mock_store.conn.execute.return_value = mock_cursor

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

        assert state.model is not None
        assert state.vector_store is not None
        assert state.processor is not None
