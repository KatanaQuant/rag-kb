"""
Unit tests for ingestion module
"""
import pytest
import tempfile
from pathlib import Path
import sqlite3

from ingestion import (
    FileHasher,
    PDFExtractor,
    DOCXExtractor,
    TextFileExtractor,
    MarkdownExtractor,
    TextExtractor,
    TextChunker,
    DocumentProcessor,
    DatabaseConnection,
    SchemaManager,
    VectorRepository,
    VectorStore
)
from ingestion.database import DOCLING_AVAILABLE
from config import ChunkConfig, DatabaseConfig
from domain_models import DocumentFile, ExtractionResult, ChunkData


class TestFileHasher:
    """Tests for FileHasher"""

    def test_hash_file(self, tmp_path):
        """Test file hashing"""
        file_path = tmp_path / "test.txt"
        file_path.write_text("test content")

        hash1 = FileHasher.hash_file(file_path)
        assert len(hash1) == 64  # SHA256 hex length

        # Same content should produce same hash
        hash2 = FileHasher.hash_file(file_path)
        assert hash1 == hash2

    def test_different_content_different_hash(self, tmp_path):
        """Test different files have different hashes"""
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"

        file1.write_text("content1")
        file2.write_text("content2")

        hash1 = FileHasher.hash_file(file1)
        hash2 = FileHasher.hash_file(file2)

        assert hash1 != hash2


class TestDocumentFile:
    """Tests for DocumentFile domain model"""

    def test_create_with_path_and_hash(self, tmp_path):
        """Test creating DocumentFile with path and hash"""
        file_path = tmp_path / "test.txt"
        file_path.write_text("content")

        doc_file = DocumentFile(path=file_path, hash="abc123")

        assert doc_file.path == file_path
        assert doc_file.hash == "abc123"

    def test_extension_property(self, tmp_path):
        """Test extension property returns lowercase extension"""
        doc_file = DocumentFile(path=tmp_path / "test.PDF", hash="abc")
        assert doc_file.extension == ".pdf"

        doc_file = DocumentFile(path=tmp_path / "doc.TXT", hash="def")
        assert doc_file.extension == ".txt"

    def test_name_property(self, tmp_path):
        """Test name property returns filename"""
        doc_file = DocumentFile(path=tmp_path / "my_document.pdf", hash="abc")
        assert doc_file.name == "my_document.pdf"

    def test_exists_returns_true_for_existing_file(self, tmp_path):
        """Test exists() returns True when file exists"""
        file_path = tmp_path / "test.txt"
        file_path.write_text("content")

        doc_file = DocumentFile(path=file_path, hash="abc")
        assert doc_file.exists() is True

    def test_exists_returns_false_for_missing_file(self, tmp_path):
        """Test exists() returns False when file doesn't exist"""
        doc_file = DocumentFile(path=tmp_path / "nonexistent.txt", hash="abc")
        assert doc_file.exists() is False

    def test_create_from_file_with_hasher(self, tmp_path):
        """Test creating DocumentFile using FileHasher"""
        file_path = tmp_path / "test.txt"
        file_path.write_text("test content")

        file_hash = FileHasher.hash_file(file_path)
        doc_file = DocumentFile(path=file_path, hash=file_hash)

        assert doc_file.path == file_path
        assert len(doc_file.hash) == 64  # SHA256 hex length
        assert doc_file.exists() is True


class TestExtractionResult:
    """Tests for ExtractionResult domain model"""

    def test_create_successful_result(self):
        """Test creating successful extraction result"""
        pages = [("Page 1 text", 1), ("Page 2 text", 2)]
        result = ExtractionResult(pages=pages, method="docling")

        assert result.success is True
        assert result.error is None
        assert result.pages == pages
        assert result.method == "docling"

    def test_create_failed_result(self):
        """Test creating failed extraction result"""
        result = ExtractionResult(
            pages=[],
            method="pypdf",
            success=False,
            error="Failed to extract"
        )

        assert result.success is False
        assert result.error == "Failed to extract"
        assert len(result.pages) == 0

    def test_page_count_property(self):
        """Test page_count property"""
        pages = [("text1", 1), ("text2", 2), ("text3", 3)]
        result = ExtractionResult(pages=pages, method="docling")

        assert result.page_count == 3

    def test_total_chars_property(self):
        """Test total_chars property"""
        pages = [("12345", 1), ("abc", 2), ("test", 3)]
        result = ExtractionResult(pages=pages, method="pypdf")

        assert result.total_chars == 12  # 5 + 3 + 4

    def test_empty_result(self):
        """Test extraction result with no pages"""
        result = ExtractionResult(pages=[], method="markdown")

        assert result.page_count == 0
        assert result.total_chars == 0

    def test_pages_without_page_numbers(self):
        """Test extraction for formats without page numbers (txt, md)"""
        pages = [("Full text content", None)]
        result = ExtractionResult(pages=pages, method="markdown")

        assert result.page_count == 1
        assert result.pages[0][1] is None


class TestTextFileExtractor:
    """Tests for TextFileExtractor"""

    def test_extract_text(self, tmp_path):
        """Test text file extraction"""
        file_path = tmp_path / "test.txt"
        content = "Hello World\nTest Content"
        file_path.write_text(content)

        result = TextFileExtractor.extract(file_path)

        assert result.page_count == 1
        assert result.pages[0][0] == content
        assert result.pages[0][1] is None  # No page number for text
        assert result.method == 'text'


class TestMarkdownExtractor:
    """Tests for MarkdownExtractor"""

    @pytest.mark.skipif(not DOCLING_AVAILABLE, reason="Docling not available")
    def test_extract_markdown(self, tmp_path):
        """Test markdown extraction using Docling"""
        file_path = tmp_path / "test.md"
        content = "# Header\n\n**Bold text**\n\nNormal text"
        file_path.write_text(content)

        result = MarkdownExtractor.extract(file_path)

        assert result.page_count > 0
        assert result.method == 'docling_markdown'
        assert result.success

class TestTextExtractor:
    """Tests for TextExtractor"""

    def test_build_extractors(self):
        """Test extractor mapping"""
        extractor = TextExtractor()
        assert '.pdf' in extractor.extractors
        assert '.txt' in extractor.extractors
        assert '.md' in extractor.extractors
        assert '.docx' in extractor.extractors

    def test_validate_extension(self):
        """Test extension validation"""
        extractor = TextExtractor()

        with pytest.raises(ValueError, match="Unsupported"):
            extractor._validate_extension('.xyz')

    def test_extract_text_file(self, tmp_path):
        """Test extracting text file"""
        extractor = TextExtractor()
        file_path = tmp_path / "test.txt"
        file_path.write_text("test")

        result = extractor.extract(file_path)
        assert result.page_count == 1
        assert result.method == 'text'


class TestTextChunker:
    """Tests for TextChunker"""

    def test_chunk_small_text(self):
        """Test chunking small text"""
        config = ChunkConfig(size=100, overlap=20, min_size=10)
        chunker = TextChunker(config)

        text = "A" * 50  # Small text
        chunks = chunker.chunk(text)

        assert len(chunks) == 1
        assert chunks[0].content == text

    def test_chunk_large_text(self):
        """Test chunking large text"""
        config = ChunkConfig(size=100, overlap=20, min_size=10, semantic=False)
        chunker = TextChunker(config)

        text = "A" * 250  # Large text
        chunks = chunker.chunk(text)

        assert len(chunks) > 1

    def test_chunk_with_overlap(self):
        """Test overlap works correctly"""
        config = ChunkConfig(size=100, overlap=20, min_size=10, semantic=False)
        chunker = TextChunker(config)

        text = "A" * 200
        chunks = chunker.chunk(text)

        # Should have overlap
        assert len(chunks) >= 2

    def test_min_size_filter(self):
        """Test minimum size filtering"""
        config = ChunkConfig(size=100, overlap=0, min_size=50)
        chunker = TextChunker(config)

        text = "A" * 30  # Below min size
        chunks = chunker.chunk(text)

        assert len(chunks) == 0

    def test_page_metadata(self):
        """Test page metadata is preserved"""
        chunker = TextChunker()
        text = "A" * 100
        chunks = chunker.chunk(text, page=5)

        assert all(c.page == 5 for c in chunks)


class TestSemanticChunkingStrategy:
    """Tests for SemanticChunkingStrategy"""

    def test_chunk_on_paragraphs(self):
        """Test semantic chunking splits on paragraphs"""
        from ingestion import SemanticChunkingStrategy

        config = ChunkConfig(size=100, overlap=0, min_size=10)
        strategy = SemanticChunkingStrategy(config)

        text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        chunks = strategy.chunk(text, page=1)

        assert len(chunks) >= 1
        assert all(isinstance(c, ChunkData) for c in chunks)
        assert all(c.page == 1 for c in chunks)

    def test_respects_max_size(self):
        """Test semantic chunking respects max size"""
        from ingestion import SemanticChunkingStrategy

        config = ChunkConfig(size=50, overlap=0, min_size=10)
        strategy = SemanticChunkingStrategy(config)

        # Two large paragraphs that exceed size
        text = "A" * 60 + "\n\n" + "B" * 60
        chunks = strategy.chunk(text, page=1)

        # Should create separate chunks
        assert len(chunks) >= 2

    def test_filters_by_min_size(self):
        """Test semantic chunking filters by min size"""
        from ingestion import SemanticChunkingStrategy

        config = ChunkConfig(size=100, overlap=0, min_size=50)
        strategy = SemanticChunkingStrategy(config)

        text = "Small.\n\nTiny."
        chunks = strategy.chunk(text, page=1)

        # All chunks should meet min_size or be filtered
        assert all(len(c.content) >= 50 for c in chunks)


class TestFixedChunkingStrategy:
    """Tests for FixedChunkingStrategy"""

    def test_fixed_size_chunks(self):
        """Test fixed-size chunking"""
        from ingestion import FixedChunkingStrategy

        config = ChunkConfig(size=100, overlap=0, min_size=10)
        strategy = FixedChunkingStrategy(config)

        text = "A" * 250
        chunks = strategy.chunk(text, page=1)

        assert len(chunks) > 1
        # Most chunks should be ~100 chars (except last)
        assert all(len(c.content) <= 100 for c in chunks)

    def test_chunk_overlap(self):
        """Test chunking with overlap"""
        from ingestion import FixedChunkingStrategy

        config = ChunkConfig(size=100, overlap=20, min_size=10)
        strategy = FixedChunkingStrategy(config)

        text = "A" * 200
        chunks = strategy.chunk(text, page=1)

        # Should have overlap between chunks
        assert len(chunks) >= 2

    def test_preserves_page_metadata(self):
        """Test page metadata is preserved"""
        from ingestion import FixedChunkingStrategy

        config = ChunkConfig(size=100, overlap=0, min_size=10)
        strategy = FixedChunkingStrategy(config)

        text = "A" * 250
        chunks = strategy.chunk(text, page=5)

        assert all(c.page == 5 for c in chunks)

    def test_min_size_filter(self):
        """Test minimum size filtering"""
        from ingestion import FixedChunkingStrategy

        config = ChunkConfig(size=100, overlap=0, min_size=50)
        strategy = FixedChunkingStrategy(config)

        text = "A" * 30  # Below min size
        chunks = strategy.chunk(text, page=1)

        assert len(chunks) == 0


class TestMetadataEnricher:
    """Tests for MetadataEnricher"""

    def test_enrich_single_chunk(self, tmp_path):
        """Test enriching a single chunk with metadata"""
        from ingestion import MetadataEnricher, FileHasher

        file_path = tmp_path / "test.txt"
        file_path.write_text("test content")

        enricher = MetadataEnricher(FileHasher())
        chunks = [{'content': 'test chunk'}]

        enriched = enricher.enrich(chunks, file_path)

        assert len(enriched) == 1
        assert enriched[0]['content'] == 'test chunk'
        assert enriched[0]['source'] == 'test.txt'
        assert enriched[0]['file_path'] == str(file_path)
        assert 'file_hash' in enriched[0]
        assert len(enriched[0]['file_hash']) == 64  # SHA256

    def test_enrich_multiple_chunks(self, tmp_path):
        """Test enriching multiple chunks"""
        from ingestion import MetadataEnricher, FileHasher

        file_path = tmp_path / "doc.md"
        file_path.write_text("content")

        enricher = MetadataEnricher(FileHasher())
        chunks = [
            {'content': 'chunk 1'},
            {'content': 'chunk 2'},
            {'content': 'chunk 3'}
        ]

        enriched = enricher.enrich(chunks, file_path)

        assert len(enriched) == 3
        # All chunks should have same file metadata
        for chunk in enriched:
            assert chunk['source'] == 'doc.md'
            assert chunk['file_path'] == str(file_path)
            assert len(chunk['file_hash']) == 64

    def test_preserves_existing_fields(self, tmp_path):
        """Test that existing chunk fields are preserved"""
        from ingestion import MetadataEnricher, FileHasher

        file_path = tmp_path / "test.txt"
        file_path.write_text("test")

        enricher = MetadataEnricher(FileHasher())
        chunks = [{'content': 'test', 'page': 5, 'custom_field': 'value'}]

        enriched = enricher.enrich(chunks, file_path)

        assert enriched[0]['content'] == 'test'
        assert enriched[0]['page'] == 5
        assert enriched[0]['custom_field'] == 'value'
        assert 'source' in enriched[0]
        assert 'file_path' in enriched[0]
        assert 'file_hash' in enriched[0]


class TestDocumentProcessor:
    """Tests for DocumentProcessor"""

    def test_supported_extensions(self):
        """Test supported extensions"""
        processor = DocumentProcessor()
        assert '.pdf' in processor.SUPPORTED_EXTENSIONS
        assert '.txt' in processor.SUPPORTED_EXTENSIONS
        assert '.md' in processor.SUPPORTED_EXTENSIONS

    def test_get_file_hash(self, tmp_path):
        """Test file hash retrieval"""
        processor = DocumentProcessor()
        file_path = tmp_path / "test.txt"
        file_path.write_text("content")

        hash_val = processor.get_file_hash(file_path)
        assert len(hash_val) == 64

    def test_process_text_file(self, tmp_path):
        """Test processing text file"""
        processor = DocumentProcessor()
        file_path = tmp_path / "test.txt"
        content = "A" * 2000  # Enough for multiple chunks
        file_path.write_text(content)

        file_hash = FileHasher.hash_file(file_path)
        doc_file = DocumentFile(path=file_path, hash=file_hash)
        chunks = processor.process_file(doc_file)

        assert len(chunks) > 0
        assert all('content' in c for c in chunks)
        assert all('source' in c for c in chunks)
        assert all('file_path' in c for c in chunks)

    def test_process_nonexistent_file(self, tmp_path):
        """Test handling nonexistent file"""
        processor = DocumentProcessor()
        file_path = tmp_path / "nonexistent.txt"

        doc_file = DocumentFile(path=file_path, hash="fake_hash")
        chunks = processor.process_file(doc_file)
        assert chunks == []


class TestDatabaseConnection:
    """Tests for DatabaseConnection"""

    def test_connect(self, tmp_path):
        """Test database connection"""
        db_path = tmp_path / "test.db"
        config = DatabaseConfig(path=str(db_path), require_vec_extension=False)
        db_conn = DatabaseConnection(config)

        conn = db_conn.connect()
        assert conn is not None
        assert isinstance(conn, sqlite3.Connection)

        db_conn.close()

    def test_close(self, tmp_path):
        """Test closing connection"""
        db_path = tmp_path / "test.db"
        config = DatabaseConfig(path=str(db_path), require_vec_extension=False)
        db_conn = DatabaseConnection(config)

        db_conn.connect()
        db_conn.close()
        # Should not error


class TestSchemaManager:
    """Tests for SchemaManager"""

    def test_create_schema(self, tmp_path):
        """Test schema creation"""
        db_path = tmp_path / "test.db"
        config = DatabaseConfig(path=str(db_path))
        conn = sqlite3.connect(str(db_path))

        manager = SchemaManager(conn, config)
        manager.create_schema()

        # Check tables exist
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = {row[0] for row in cursor.fetchall()}

        assert 'documents' in tables
        assert 'chunks' in tables

        conn.close()


class TestVectorRepository:
    """Tests for VectorRepository"""

    @pytest.fixture
    def setup_db(self, tmp_path):
        """Setup test database"""
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))

        # Create tables
        conn.execute("""
            CREATE TABLE documents (
                id INTEGER PRIMARY KEY,
                file_path TEXT UNIQUE,
                file_hash TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE chunks (
                id INTEGER PRIMARY KEY,
                document_id INTEGER,
                content TEXT,
                page INTEGER,
                chunk_index INTEGER
            )
        """)
        conn.commit()

        return conn

    def test_is_indexed(self, setup_db):
        """Test checking if document is indexed"""
        repo = VectorRepository(setup_db)

        # Not indexed
        assert not repo.is_indexed("/path/file.txt", "hash123")

        # Add document
        setup_db.execute(
            "INSERT INTO documents (file_path, file_hash) VALUES (?, ?)",
            ("/path/file.txt", "hash123")
        )
        setup_db.commit()

        # Now indexed
        assert repo.is_indexed("/path/file.txt", "hash123")

        # Different hash
        assert not repo.is_indexed("/path/file.txt", "hash456")

    def test_get_stats(self, setup_db):
        """Test getting statistics"""
        repo = VectorRepository(setup_db)

        stats = repo.get_stats()
        assert stats['indexed_documents'] == 0
        assert stats['total_chunks'] == 0

        # Add data
        setup_db.execute(
            "INSERT INTO documents (file_path, file_hash) VALUES (?, ?)",
            ("/path/file.txt", "hash123")
        )
        setup_db.execute(
            "INSERT INTO chunks (document_id, content, page, chunk_index) VALUES (?, ?, ?, ?)",
            (1, "content", None, 0)
        )
        setup_db.commit()

        stats = repo.get_stats()
        assert stats['indexed_documents'] == 1
        assert stats['total_chunks'] == 1


class TestVectorStore:
    """Integration tests for VectorStore"""

    def test_init(self, tmp_path):
        """Test store initialization"""
        db_path = tmp_path / "test.db"
        config = DatabaseConfig(path=str(db_path), require_vec_extension=False)

        store = VectorStore(config)
        assert store.conn is not None
        assert store.repo is not None

        store.close()

    def test_get_stats(self, tmp_path):
        """Test getting stats"""
        db_path = tmp_path / "test.db"
        config = DatabaseConfig(path=str(db_path), require_vec_extension=False)

        store = VectorStore(config)
        stats = store.get_stats()

        assert 'indexed_documents' in stats
        assert 'total_chunks' in stats

        store.close()


class TestDoclingExtractorHelpers:
    """Tests for DoclingExtractor helper methods (Phase 8 refactoring)"""

    def test_should_retry_with_ghostscript_for_pdf(self, tmp_path):
        """Test Ghostscript retry decision for PDF files"""
        from ingestion import DoclingExtractor

        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_text("fake pdf")

        assert DoclingExtractor._should_retry_with_ghostscript(pdf_path, True) is True
        assert DoclingExtractor._should_retry_with_ghostscript(pdf_path, False) is False

    def test_should_not_retry_with_ghostscript_for_docx(self, tmp_path):
        """Test Ghostscript retry decision for non-PDF files"""
        from ingestion import DoclingExtractor

        docx_path = tmp_path / "test.docx"
        docx_path.write_text("fake docx")

        assert DoclingExtractor._should_retry_with_ghostscript(docx_path, True) is False
        assert DoclingExtractor._should_retry_with_ghostscript(docx_path, False) is False

    def test_get_condensed_error_reason_truncates_long_errors(self):
        """Test error message condensing"""
        from ingestion import DoclingExtractor

        long_error = RuntimeError("This is a very long error message " * 10)
        result = DoclingExtractor._get_condensed_error_reason(long_error)

        assert len(result) == 100
        assert result.startswith("This is a very long error message")

    def test_get_condensed_error_reason_handles_multiline(self):
        """Test error condensing takes only first line"""
        from ingestion import DoclingExtractor

        multiline_error = RuntimeError("First line\nSecond line\nThird line")
        result = DoclingExtractor._get_condensed_error_reason(multiline_error)

        assert result == "First line"
        assert "Second" not in result

    def test_extract_error_details_with_errors(self):
        """Test extracting error details from result"""
        from ingestion import DoclingExtractor
        from unittest.mock import Mock

        result = Mock()
        result.errors = ["Error 1", "Error 2", "Error 3", "Error 4"]

        details = DoclingExtractor._extract_error_details(result)

        assert "    - Error 1" in details
        assert "    - Error 2" in details
        assert "    - Error 3" in details
        assert "Error 4" not in details  # Limit to 3

    def test_extract_error_details_no_errors(self):
        """Test extracting error details when no errors present"""
        from ingestion import DoclingExtractor
        from unittest.mock import Mock

        result = Mock()
        result.errors = []

        details = DoclingExtractor._extract_error_details(result)

        assert details == "    - No specific error details available"

    def test_extract_error_details_no_error_attribute(self):
        """Test extracting error details when result has no errors attribute"""
        from ingestion import DoclingExtractor
        from unittest.mock import Mock

        result = Mock(spec=[])  # No attributes

        details = DoclingExtractor._extract_error_details(result)

        assert details == "    - No specific error details available"
