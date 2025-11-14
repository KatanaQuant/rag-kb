import sqlite3
from pathlib import Path
from typing import List, Dict, Tuple
import hashlib
import re

from pypdf import PdfReader
from docx import Document
import markdown
import numpy as np

from config import default_config


class FileHasher:
    """Generates file hashes for change detection"""

    @staticmethod
    def hash_file(file_path: Path) -> str:
        """Generate SHA256 hash of file"""
        hasher = hashlib.sha256()
        FileHasher._update_hasher(hasher, file_path)
        return hasher.hexdigest()

    @staticmethod
    def _update_hasher(hasher, file_path: Path):
        """Update hasher with file chunks"""
        with open(file_path, 'rb') as f:
            for chunk in FileHasher._read_chunks(f):
                hasher.update(chunk)

    @staticmethod
    def _read_chunks(file_handle):
        """Yield file chunks for hashing"""
        return iter(lambda: file_handle.read(8192), b'')


class PDFExtractor:
    """Extracts text from PDF files"""

    @staticmethod
    def extract(path: Path) -> List[Tuple[str, int]]:
        """Extract text with page numbers"""
        reader = PdfReader(path)
        return PDFExtractor._extract_pages(reader)

    @staticmethod
    def _extract_pages(reader) -> List[Tuple[str, int]]:
        """Extract all pages"""
        results = []
        for num, page in enumerate(reader.pages, 1):
            PDFExtractor._add_page(results, page, num)
        return results

    @staticmethod
    def _add_page(results: List, page, num: int):
        """Add page if has text"""
        text = page.extract_text()
        if text.strip():
            results.append((text, num))


class DOCXExtractor:
    """Extracts text from DOCX files"""

    @staticmethod
    def extract(path: Path) -> List[Tuple[str, None]]:
        """Extract text from DOCX"""
        doc = Document(path)
        text = DOCXExtractor._join_paragraphs(doc)
        return [(text, None)]

    @staticmethod
    def _join_paragraphs(doc) -> str:
        """Join all paragraphs"""
        return '\n'.join([p.text for p in doc.paragraphs])


class TextFileExtractor:
    """Extracts text from plain text files"""

    @staticmethod
    def extract(path: Path) -> List[Tuple[str, None]]:
        """Extract text from file"""
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            return [(f.read(), None)]


class MarkdownExtractor:
    """Extracts text from Markdown files"""

    @staticmethod
    def extract(path: Path) -> List[Tuple[str, None]]:
        """Extract and clean markdown"""
        text = MarkdownExtractor._read_file(path)
        clean = MarkdownExtractor._to_plain_text(text)
        return [(clean, None)]

    @staticmethod
    def _read_file(path: Path) -> str:
        """Read markdown file"""
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()

    @staticmethod
    def _to_plain_text(text: str) -> str:
        """Convert markdown to plain text"""
        html = markdown.markdown(text)
        return MarkdownExtractor._strip_html(html)

    @staticmethod
    def _strip_html(html: str) -> str:
        """Remove HTML tags"""
        return re.sub(r'<[^>]+>', '', html)


class TextExtractor:
    """Extracts text from various file formats"""

    def __init__(self):
        self.extractors = self._build_extractors()

    def extract(self, file_path: Path) -> List[Tuple[str, int]]:
        """Extract text based on file extension"""
        ext = file_path.suffix.lower()
        self._validate_extension(ext)
        return self.extractors[ext](file_path)

    def _build_extractors(self) -> Dict:
        """Map extensions to extractors"""
        return {
            '.pdf': PDFExtractor.extract,
            '.docx': DOCXExtractor.extract,
            '.txt': TextFileExtractor.extract,
            '.md': MarkdownExtractor.extract,
            '.markdown': MarkdownExtractor.extract
        }

    def _validate_extension(self, ext: str):
        """Validate extension is supported"""
        if ext not in self.extractors:
            raise ValueError(f"Unsupported: {ext}")


class TextChunker:
    """Splits text into overlapping chunks"""

    def __init__(self, config=default_config.chunks):
        self.config = config

    def chunk(self, text: str, page: int = None) -> List[Dict]:
        """Split text into chunks"""
        chunks = []
        start = 0
        while start < len(text):
            self._process_position(chunks, text, start, page)
            start = self._next_position(start)
        return chunks

    def _process_position(self, chunks, text, start, page):
        """Process chunk at position"""
        chunk = self._extract_chunk(text, start)
        if self._is_valid(chunk):
            chunks.append(self._make_dict(chunk, page))

    def _extract_chunk(self, text: str, start: int) -> str:
        """Extract chunk at position"""
        end = start + self.config.size
        return text[start:end].strip()

    def _is_valid(self, chunk: str) -> bool:
        """Check if chunk meets minimum size"""
        return len(chunk.strip()) >= self.config.min_size

    def _make_dict(self, content: str, page: int) -> Dict:
        """Create chunk dictionary"""
        return {'content': content, 'page': page}

    def _next_position(self, current: int) -> int:
        """Calculate next chunk start"""
        return current + self.config.size - self.config.overlap


class DocumentProcessor:
    """Coordinates document processing"""

    SUPPORTED_EXTENSIONS = {
        '.pdf', '.txt', '.md', '.markdown', '.docx'
    }

    def __init__(self):
        self.hasher = FileHasher()
        self.extractor = TextExtractor()
        self.chunker = TextChunker()

    def get_file_hash(self, path: Path) -> str:
        """Get file hash"""
        return self.hasher.hash_file(path)

    def process_file(self, path: Path) -> List[Dict]:
        """Process file into chunks"""
        try:
            return self._do_process(path)
        except Exception as e:
            print(f"Error: {path}: {e}")
            return []

    def _do_process(self, path: Path) -> List[Dict]:
        """Perform processing"""
        text_pages = self.extractor.extract(path)
        return self._process_pages(text_pages, path)

    def _process_pages(self, pages: List, path: Path) -> List[Dict]:
        """Process extracted pages"""
        all_chunks = []
        for text, page_num in pages:
            self._add_page_chunks(all_chunks, text, page_num, path)
        return all_chunks

    def _add_page_chunks(self, all_chunks, text, page, path):
        """Add chunks for one page"""
        chunks = self.chunker.chunk(text, page)
        enriched = self._enrich_chunks(chunks, path)
        all_chunks.extend(enriched)

    def _enrich_chunks(self, chunks: List[Dict], path: Path) -> List[Dict]:
        """Add metadata to chunks"""
        for chunk in chunks:
            self._add_metadata(chunk, path)
        return chunks

    def _add_metadata(self, chunk: Dict, path: Path):
        """Add metadata to single chunk"""
        chunk['source'] = str(path.name)
        chunk['file_path'] = str(path)
        chunk['file_hash'] = self.get_file_hash(path)


class DatabaseConnection:
    """Manages SQLite connection and extensions"""

    def __init__(self, config=default_config.database):
        self.config = config
        self.conn = None

    def connect(self) -> sqlite3.Connection:
        """Establish database connection"""
        self.conn = self._create_connection()
        self._load_extension()
        return self.conn

    def _create_connection(self) -> sqlite3.Connection:
        """Create SQLite connection"""
        return sqlite3.connect(
            self.config.path,
            check_same_thread=self.config.check_same_thread
        )

    def _load_extension(self):
        """Load vector extension"""
        self.conn.enable_load_extension(True)
        self._try_load()

    def _try_load(self):
        """Try loading extension"""
        try:
            self.conn.load_extension("vec0")
        except Exception:
            self._load_python_bindings()

    def _load_python_bindings(self):
        """Fallback to Python bindings"""
        try:
            import sqlite_vec
            sqlite_vec.load(self.conn)
        except Exception as e:
            raise RuntimeError(f"sqlite-vec failed: {e}")

    def close(self):
        """Close connection"""
        if self.conn:
            self.conn.close()


class SchemaManager:
    """Manages database schema"""

    def __init__(self, conn: sqlite3.Connection, config=default_config.database):
        self.conn = conn
        self.config = config

    def create_schema(self):
        """Create all required tables"""
        self._create_documents_table()
        self._create_chunks_table()
        self._create_vector_table()
        self.conn.commit()

    def _create_documents_table(self):
        """Create documents table"""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT UNIQUE NOT NULL,
                file_hash TEXT NOT NULL,
                indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

    def _create_chunks_table(self):
        """Create chunks table"""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                page INTEGER,
                chunk_index INTEGER,
                FOREIGN KEY (document_id)
                    REFERENCES documents(id)
                    ON DELETE CASCADE
            )
        """)

    def _create_vector_table(self):
        """Create vector embeddings table"""
        try:
            self._execute_create_vec_table()
        except Exception as e:
            print(f"Note: vec_chunks exists: {e}")

    def _execute_create_vec_table(self):
        """Execute vector table creation"""
        self.conn.execute(f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks
            USING vec0(
                chunk_id INTEGER PRIMARY KEY,
                embedding FLOAT[{self.config.embedding_dim}]
            )
        """)


class VectorRepository:
    """Handles vector CRUD operations"""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def is_indexed(self, path: str, hash_val: str) -> bool:
        """Check if document indexed"""
        result = self._fetch_hash(path)
        return result and result[0] == hash_val

    def _fetch_hash(self, path: str):
        """Fetch stored hash"""
        cursor = self.conn.execute(
            "SELECT file_hash FROM documents WHERE file_path = ?",
            (path,)
        )
        return cursor.fetchone()

    def add_document(self, path: str, hash_val: str,
                    chunks: List[Dict], embeddings: List) -> int:
        """Add document with chunks"""
        self._delete_old(path)
        doc_id = self._insert_doc(path, hash_val)
        self._insert_chunks(doc_id, chunks, embeddings)
        self.conn.commit()
        return doc_id

    def _delete_old(self, path: str):
        """Remove existing document"""
        self.conn.execute(
            "DELETE FROM documents WHERE file_path = ?",
            (path,)
        )

    def _insert_doc(self, path: str, hash_val: str) -> int:
        """Insert document record"""
        cursor = self.conn.execute(
            "INSERT INTO documents (file_path, file_hash) VALUES (?, ?)",
            (path, hash_val)
        )
        return cursor.lastrowid

    def _insert_chunks(self, doc_id: int, chunks: List[Dict],
                      embeddings: List):
        """Insert all chunks and vectors"""
        for idx, (chunk, emb) in enumerate(zip(chunks, embeddings)):
            self._insert_chunk_pair(doc_id, chunk, emb, idx)

    def _insert_chunk_pair(self, doc_id, chunk, emb, idx):
        """Insert chunk and its vector"""
        chunk_id = self._insert_chunk(doc_id, chunk, idx)
        self._insert_vector(chunk_id, emb)

    def _insert_chunk(self, doc_id: int, chunk: Dict, idx: int) -> int:
        """Insert single chunk"""
        cursor = self.conn.execute(
            """INSERT INTO chunks
               (document_id, content, page, chunk_index)
               VALUES (?, ?, ?, ?)""",
            (doc_id, chunk['content'], chunk.get('page'), idx)
        )
        return cursor.lastrowid

    def _insert_vector(self, chunk_id: int, embedding: List):
        """Insert vector embedding"""
        blob = self._to_blob(embedding)
        self.conn.execute(
            "INSERT INTO vec_chunks (chunk_id, embedding) VALUES (?, ?)",
            (chunk_id, blob)
        )

    @staticmethod
    def _to_blob(embedding: List) -> bytes:
        """Convert embedding to binary"""
        arr = np.array(embedding, dtype=np.float32)
        return arr.tobytes()

    def search(self, embedding: List, top_k: int,
              threshold: float = None) -> List[Dict]:
        """Search for similar vectors"""
        blob = self._to_blob(embedding)
        results = self._execute_search(blob, top_k)
        return self._format_results(results, threshold)

    def _execute_search(self, blob: bytes, top_k: int):
        """Execute vector search"""
        cursor = self.conn.execute("""
            SELECT c.content, d.file_path, c.page,
                   vec_distance_cosine(v.embedding, ?) as dist
            FROM vec_chunks v
            JOIN chunks c ON v.chunk_id = c.id
            JOIN documents d ON c.document_id = d.id
            ORDER BY dist ASC
            LIMIT ?
        """, (blob, top_k))
        return cursor.fetchall()

    def _format_results(self, rows, threshold: float) -> List[Dict]:
        """Format search results"""
        results = []
        for row in rows:
            self._add_if_valid(results, row, threshold)
        return results

    def _add_if_valid(self, results, row, threshold):
        """Add result if meets threshold"""
        score = 1 - row[3]
        if threshold is None or score >= threshold:
            results.append(self._make_result(row, score))

    @staticmethod
    def _make_result(row, score: float) -> Dict:
        """Create result dictionary"""
        return {
            'content': row[0],
            'source': Path(row[1]).name,
            'page': row[2],
            'score': float(score)
        }

    def get_stats(self) -> Dict:
        """Get database statistics"""
        return {
            'indexed_documents': self._count_docs(),
            'total_chunks': self._count_chunks()
        }

    def _count_docs(self) -> int:
        """Count total documents"""
        cursor = self.conn.execute("SELECT COUNT(*) FROM documents")
        return cursor.fetchone()[0]

    def _count_chunks(self) -> int:
        """Count total chunks"""
        cursor = self.conn.execute("SELECT COUNT(*) FROM chunks")
        return cursor.fetchone()[0]


class VectorStore:
    """Facade for vector storage operations"""

    def __init__(self, config=default_config.database):
        self.db_conn = DatabaseConnection(config)
        self.conn = self.db_conn.connect()
        self._init_schema()
        self.repo = VectorRepository(self.conn)

    def _init_schema(self):
        """Initialize database schema"""
        schema = SchemaManager(self.conn)
        schema.create_schema()

    def is_document_indexed(self, path: str, hash_val: str) -> bool:
        """Check if document is indexed"""
        return self.repo.is_indexed(path, hash_val)

    def add_document(self, file_path: str, file_hash: str,
                    chunks: List[Dict], embeddings: List):
        """Add document to store"""
        self.repo.add_document(file_path, file_hash, chunks, embeddings)

    def search(self, query_embedding: List, top_k: int = 5,
              threshold: float = None) -> List[Dict]:
        """Search for similar chunks"""
        return self.repo.search(query_embedding, top_k, threshold)

    def get_stats(self) -> Dict:
        """Get statistics"""
        return self.repo.get_stats()

    def close(self):
        """Close connection"""
        self.db_conn.close()
