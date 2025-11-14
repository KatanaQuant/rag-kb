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
from config import ChunkConfig, DatabaseConfig


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


class TestTextFileExtractor:
    """Tests for TextFileExtractor"""

    def test_extract_text(self, tmp_path):
        """Test text file extraction"""
        file_path = tmp_path / "test.txt"
        content = "Hello World\nTest Content"
        file_path.write_text(content)

        result = TextFileExtractor.extract(file_path)

        assert len(result) == 1
        assert result[0][0] == content
        assert result[0][1] is None  # No page number for text


class TestMarkdownExtractor:
    """Tests for MarkdownExtractor"""

    def test_extract_markdown(self, tmp_path):
        """Test markdown extraction"""
        file_path = tmp_path / "test.md"
        content = "# Header\n\n**Bold text**\n\nNormal text"
        file_path.write_text(content)

        result = MarkdownExtractor.extract(file_path)

        assert len(result) == 1
        text = result[0][0]
        assert "Header" in text
        assert "Bold text" in text

    def test_strip_html(self):
        """Test HTML stripping"""
        html = "<p>Test</p><strong>Bold</strong>"
        clean = MarkdownExtractor._strip_html(html)
        assert "<" not in clean
        assert ">" not in clean
        assert "Test" in clean
        assert "Bold" in clean


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
        assert len(result) == 1


class TestTextChunker:
    """Tests for TextChunker"""

    def test_chunk_small_text(self):
        """Test chunking small text"""
        config = ChunkConfig(size=100, overlap=20, min_size=10)
        chunker = TextChunker(config)

        text = "A" * 50  # Small text
        chunks = chunker.chunk(text)

        assert len(chunks) == 1
        assert chunks[0]['content'] == text

    def test_chunk_large_text(self):
        """Test chunking large text"""
        config = ChunkConfig(size=100, overlap=20, min_size=10)
        chunker = TextChunker(config)

        text = "A" * 250  # Large text
        chunks = chunker.chunk(text)

        assert len(chunks) > 1

    def test_chunk_with_overlap(self):
        """Test overlap works correctly"""
        config = ChunkConfig(size=100, overlap=20, min_size=10)
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

        assert all(c['page'] == 5 for c in chunks)


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

        chunks = processor.process_file(file_path)

        assert len(chunks) > 0
        assert all('content' in c for c in chunks)
        assert all('source' in c for c in chunks)
        assert all('file_path' in c for c in chunks)

    def test_process_nonexistent_file(self, tmp_path):
        """Test handling nonexistent file"""
        processor = DocumentProcessor()
        file_path = tmp_path / "nonexistent.txt"

        chunks = processor.process_file(file_path)
        assert chunks == []


class TestDatabaseConnection:
    """Tests for DatabaseConnection"""

    def test_connect(self, tmp_path):
        """Test database connection"""
        db_path = tmp_path / "test.db"
        config = DatabaseConfig(path=str(db_path))
        db_conn = DatabaseConnection(config)

        conn = db_conn.connect()
        assert conn is not None
        assert isinstance(conn, sqlite3.Connection)

        db_conn.close()

    def test_close(self, tmp_path):
        """Test closing connection"""
        db_path = tmp_path / "test.db"
        config = DatabaseConfig(path=str(db_path))
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
        config = DatabaseConfig(path=str(db_path))

        store = VectorStore(config)
        assert store.conn is not None
        assert store.repo is not None

        store.close()

    def test_get_stats(self, tmp_path):
        """Test getting stats"""
        db_path = tmp_path / "test.db"
        config = DatabaseConfig(path=str(db_path))

        store = VectorStore(config)
        stats = store.get_stats()

        assert 'indexed_documents' in stats
        assert 'total_chunks' in stats

        store.close()
