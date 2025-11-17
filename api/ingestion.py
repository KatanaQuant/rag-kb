import sqlite3
from pathlib import Path
from typing import List, Dict, Tuple, Optional
import hashlib
import re
from dataclasses import dataclass
from datetime import datetime

from pypdf import PdfReader
from docx import Document
import markdown
import numpy as np

from config import default_config
from hybrid_search import HybridSearcher

try:
    from docling.document_converter import DocumentConverter
    DOCLING_AVAILABLE = True
except ImportError as e:
    DOCLING_AVAILABLE = False
    print(f"Warning: Docling not available, falling back to pypdf ({e})")

# Try to import chunking separately (may not be available in all versions)
try:
    from docling_core.transforms.chunker import HybridChunker
    from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
    from transformers import AutoTokenizer
    DOCLING_CHUNKING_AVAILABLE = True
except ImportError as e:
    DOCLING_CHUNKING_AVAILABLE = False
    if DOCLING_AVAILABLE:
        print(f"Warning: Docling HybridChunker not available ({e}), using fixed-size chunking")


@dataclass
class ProcessingProgress:
    """Processing progress for a document"""
    file_path: str
    file_hash: str
    total_chunks: int = 0
    chunks_processed: int = 0
    status: str = 'in_progress'
    last_chunk_end: int = 0
    error_message: Optional[str] = None
    started_at: Optional[str] = None
    last_updated: Optional[str] = None
    completed_at: Optional[str] = None


class ProcessingProgressTracker:
    """Manages processing progress persistence"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = None
        self._connect()

    def _connect(self):
        """Connect to database"""
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)

    def start_processing(self, file_path: str, file_hash: str) -> ProcessingProgress:
        """Initialize or resume processing"""
        progress = self.get_progress(file_path)
        if progress and progress.file_hash == file_hash:
            return progress
        if progress:
            self._delete_progress(file_path)
        return self._create_progress(file_path, file_hash)

    def _delete_progress(self, file_path: str):
        """Delete old progress"""
        self.conn.execute("DELETE FROM processing_progress WHERE file_path = ?", (file_path,))
        self.conn.commit()

    def _create_progress(self, file_path: str, file_hash: str) -> ProcessingProgress:
        """Create new progress record"""
        now = datetime.utcnow().isoformat()
        self.conn.execute("""
            INSERT INTO processing_progress
            (file_path, file_hash, started_at, last_updated)
            VALUES (?, ?, ?, ?)
        """, (file_path, file_hash, now, now))
        self.conn.commit()
        return ProcessingProgress(file_path, file_hash, started_at=now, last_updated=now)

    def update_progress(self, file_path: str, chunks_processed: int, last_chunk_end: int):
        """Update progress after batch"""
        now = datetime.utcnow().isoformat()
        self.conn.execute("""
            UPDATE processing_progress
            SET chunks_processed = ?, last_chunk_end = ?, last_updated = ?
            WHERE file_path = ?
        """, (chunks_processed, last_chunk_end, now, file_path))
        self.conn.commit()

    def mark_completed(self, file_path: str):
        """Mark as completed"""
        now = datetime.utcnow().isoformat()
        self.conn.execute("""
            UPDATE processing_progress
            SET status = 'completed', completed_at = ?, last_updated = ?
            WHERE file_path = ?
        """, (now, now, file_path))
        self.conn.commit()

    def mark_failed(self, file_path: str, error_message: str):
        """Mark as failed"""
        now = datetime.utcnow().isoformat()
        self.conn.execute("""
            UPDATE processing_progress
            SET status = 'failed', error_message = ?, last_updated = ?
            WHERE file_path = ?
        """, (error_message, now, file_path))
        self.conn.commit()

    def get_incomplete_files(self) -> List[ProcessingProgress]:
        """Get all incomplete files"""
        cursor = self.conn.execute("""
            SELECT file_path, file_hash, total_chunks, chunks_processed,
                   status, last_chunk_end, error_message, started_at,
                   last_updated, completed_at
            FROM processing_progress
            WHERE status = 'in_progress'
        """)
        return [self._row_to_progress(row) for row in cursor.fetchall()]

    def get_progress(self, file_path: str) -> Optional[ProcessingProgress]:
        """Get progress for file"""
        cursor = self.conn.execute("""
            SELECT file_path, file_hash, total_chunks, chunks_processed,
                   status, last_chunk_end, error_message, started_at,
                   last_updated, completed_at
            FROM processing_progress
            WHERE file_path = ?
        """, (file_path,))
        row = cursor.fetchone()
        return self._row_to_progress(row) if row else None

    @staticmethod
    def _row_to_progress(row) -> ProcessingProgress:
        """Convert row to object"""
        return ProcessingProgress(
            file_path=row[0],
            file_hash=row[1],
            total_chunks=row[2],
            chunks_processed=row[3],
            status=row[4],
            last_chunk_end=row[5],
            error_message=row[6],
            started_at=row[7],
            last_updated=row[8],
            completed_at=row[9]
        )

    def close(self):
        """Close connection"""
        if self.conn:
            self.conn.close()


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


class DoclingExtractor:
    """Extracts text from documents using Docling (advanced parsing)"""

    _converter = None
    _chunker = None

    @classmethod
    def get_converter(cls):
        """Lazy load converter (singleton pattern)"""
        if cls._converter is None and DOCLING_AVAILABLE:
            # Use default settings - docling will auto-download models as needed
            # OCR and table structure extraction enabled by default
            cls._converter = DocumentConverter()
        return cls._converter

    @classmethod
    def get_chunker(cls, max_tokens: int = 512):
        """Lazy load hybrid chunker (singleton pattern)"""
        if cls._chunker is None and DOCLING_CHUNKING_AVAILABLE:
            # HybridChunker with HuggingFaceTokenizer wrapper
            raw_tokenizer = AutoTokenizer.from_pretrained(default_config.model.name)
            hf_tokenizer = HuggingFaceTokenizer(tokenizer=raw_tokenizer, max_tokens=max_tokens)
            cls._chunker = HybridChunker(tokenizer=hf_tokenizer, merge_peers=True)
        return cls._chunker

    @staticmethod
    def extract(path: Path) -> List[Tuple[str, int]]:
        """Extract text from PDF/DOCX using Docling with HybridChunker"""
        converter = DoclingExtractor.get_converter()
        # convert() returns ConversionResult directly (docling 2.61.2 API)
        result = converter.convert(str(path))
        document = result.document
        # Always use hybrid chunking (structure + token-aware)
        return DoclingExtractor._extract_hybrid_chunks(document)

    @staticmethod
    def _extract_hybrid_chunks(document) -> List[Tuple[str, int]]:
        """Extract hybrid chunks using HybridChunker (structure + token-aware)"""
        # Debug: check document
        print(f"DEBUG: document type = {type(document)}")
        if hasattr(document, 'texts'):
            print(f"DEBUG: document has {len(document.texts)} texts")
            total_text_len = 0
            for i, text_item in enumerate(document.texts):  # Show all texts
                # TextItem has a 'text' attribute with the actual content
                if hasattr(text_item, 'text'):
                    text_content = text_item.text
                    total_text_len += len(text_content)
                    print(f"DEBUG: text[{i}] ({len(text_content)} chars): '{text_content[:100]}...'" if len(text_content) > 100 else f"DEBUG: text[{i}] ({len(text_content)} chars): '{text_content}'")
                else:
                    print(f"DEBUG: text[{i}] type = {type(text_item)}")
            print(f"DEBUG: Total text length = {total_text_len} chars")

        chunker = DoclingExtractor.get_chunker(default_config.chunks.max_tokens)
        print(f"DEBUG: chunker = {chunker}")

        chunks_list = []
        chunk_iter = chunker.chunk(document)
        print(f"DEBUG: chunk iterator = {chunk_iter}")

        for i, chunk in enumerate(chunk_iter):
            print(f"DEBUG: processing chunk {i}")
            # Get chunk text (use text property or export to markdown)
            chunk_text = chunk.text if hasattr(chunk, 'text') else str(chunk)
            # Get page number from metadata if available
            page = chunk.meta.page if hasattr(chunk, 'meta') and hasattr(chunk.meta, 'page') else 0
            chunks_list.append((chunk_text, page))

        print(f"Hybrid chunking: {len(chunks_list)} chunks extracted")
        return chunks_list


class PDFExtractor:
    """Extracts text from PDF files (fallback when Docling fails)"""

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
    """Extracts text from Markdown files preserving structure"""

    @staticmethod
    def extract(path: Path) -> List[Tuple[str, None]]:
        """Extract markdown text preserving structure for semantic chunking"""
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            text = f.read()
        # Keep markdown as-is for semantic chunking to preserve structure
        return [(text, None)]


class TextExtractor:
    """Extracts text from various file formats"""

    def __init__(self, config=default_config):
        self.config = config
        self.extractors = self._build_extractors()

    def extract(self, file_path: Path) -> List[Tuple[str, int]]:
        """Extract text based on file extension"""
        ext = file_path.suffix.lower()
        self._validate_extension(ext)
        return self.extractors[ext](file_path)

    def _build_extractors(self) -> Dict:
        """Map extensions to extractors - Docling only, no fallbacks"""
        print("Using Docling + HybridChunker for PDF/DOCX, semantic chunking for MD/TXT")
        return {
            '.pdf': DoclingExtractor.extract,
            '.docx': DoclingExtractor.extract,
            '.md': MarkdownExtractor.extract,
            '.markdown': MarkdownExtractor.extract,
            '.txt': TextFileExtractor.extract
        }

    def _validate_extension(self, ext: str):
        """Validate extension is supported"""
        if ext not in self.extractors:
            raise ValueError(f"Unsupported: {ext}")


class TextChunker:
    """Splits text into chunks (semantic or fixed-size)"""

    def __init__(self, config=default_config.chunks):
        self.config = config

    def chunk(self, text: str, page: int = None) -> List[Dict]:
        """Split text into chunks"""
        if self.config.semantic:
            return self._semantic_chunk(text, page)
        return self._fixed_chunk(text, page)

    def _semantic_chunk(self, text: str, page: int) -> List[Dict]:
        """Semantic chunking: split on paragraphs/sentences, preserve structure"""
        chunks = []
        # Split on double newlines (paragraphs)
        paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]

        current_chunk = []
        current_size = 0

        for para in paragraphs:
            para_size = len(para)

            # If adding this paragraph would exceed size, save current chunk
            if current_chunk and (current_size + para_size) > self.config.size:
                chunk_text = '\n\n'.join(current_chunk)
                if self._is_valid(chunk_text):
                    chunks.append(self._make_dict(chunk_text, page))
                current_chunk = [para]
                current_size = para_size
            else:
                current_chunk.append(para)
                current_size += para_size

        # Add final chunk
        if current_chunk:
            chunk_text = '\n\n'.join(current_chunk)
            if self._is_valid(chunk_text):
                chunks.append(self._make_dict(chunk_text, page))

        return chunks if chunks else self._fixed_chunk(text, page)

    def _fixed_chunk(self, text: str, page: int) -> List[Dict]:
        """Fixed-size chunking with overlap"""
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


class ChunkedTextProcessor:
    """Processes text in resumable chunks"""

    def __init__(self, chunker: TextChunker,
                 progress_tracker: ProcessingProgressTracker,
                 batch_size: int = 50):
        self.chunker = chunker
        self.tracker = progress_tracker
        self.batch_size = batch_size

    def process_text(self, file_path: str, full_text: str,
                    file_hash: str, page_num: int = None) -> List[Dict]:
        """Process text with resume"""
        progress = self.tracker.start_processing(file_path, file_hash)

        # Skip if already completed
        if progress.status == 'completed':
            text = full_text
            return self._create_chunks(text, page_num)

        text = self._get_remaining(full_text, progress)
        chunks = self._create_chunks(text, page_num)
        return self._batch_process(file_path, chunks, progress)

    @staticmethod
    def _get_remaining(text: str, progress: ProcessingProgress) -> str:
        """Get unprocessed text"""
        if progress.last_chunk_end > 0:
            return text[progress.last_chunk_end:]
        return text

    def _create_chunks(self, text: str, page: int) -> List[Dict]:
        """Create chunks from text"""
        return self.chunker.chunk(text, page)

    def _batch_process(self, path: str, chunks: List[Dict],
                      progress: ProcessingProgress) -> List[Dict]:
        """Process in batches"""
        all_chunks = []
        chunks_count = progress.chunks_processed
        char_position = progress.last_chunk_end

        for i in range(0, len(chunks), self.batch_size):
            batch = chunks[i:i+self.batch_size]
            all_chunks.extend(batch)
            chunks_count += len(batch)
            char_position += sum(len(c['content']) for c in batch)
            self.tracker.update_progress(path, chunks_count, char_position)

        self.tracker.mark_completed(path)
        return all_chunks

    def _update_tracker(self, path: str, batch: List[Dict],
                       progress: ProcessingProgress):
        """Update progress tracking"""
        processed = progress.chunks_processed + len(batch)
        chunk_end = progress.last_chunk_end + sum(len(c['content']) for c in batch)
        self.tracker.update_progress(path, processed, chunk_end)


class DocumentProcessor:
    """Coordinates document processing"""

    SUPPORTED_EXTENSIONS = {
        '.pdf', '.txt', '.md', '.markdown', '.docx'
    }

    def __init__(self, progress_tracker: Optional[ProcessingProgressTracker] = None):
        self.hasher = FileHasher()
        self.extractor = TextExtractor()
        self.chunker = TextChunker()
        self.tracker = progress_tracker
        self.chunked_processor = None
        if self.tracker:
            self.chunked_processor = ChunkedTextProcessor(
                self.chunker, self.tracker, batch_size=50
            )

    def get_file_hash(self, path: Path) -> str:
        """Get file hash"""
        return self.hasher.hash_file(path)

    def process_file(self, path: Path) -> List[Dict]:
        """Process file into chunks"""
        if self.tracker:
            return self._process_with_resume(path)
        return self._process_legacy(path)

    def _process_with_resume(self, path: Path) -> List[Dict]:
        """Process with resumable tracking"""
        try:
            file_hash = self.get_file_hash(path)
            progress = self.tracker.get_progress(str(path))
            if self._is_completed(progress, file_hash):
                print(f"Skipping completed: {path.name}")
                return []
            return self._do_resumable_process(path, file_hash)
        except Exception as e:
            self.tracker.mark_failed(str(path), str(e))
            print(f"Error processing: {path.name}: {e}")
            import traceback
            traceback.print_exc()
            return []

    def _is_completed(self, progress, file_hash: str) -> bool:
        """Check if file already completed"""
        return progress and progress.status == 'completed' and progress.file_hash == file_hash

    def _do_resumable_process(self, path: Path, file_hash: str) -> List[Dict]:
        """Process with resume capability"""
        # Stage 1: Extract text
        extracted_items = self.extractor.extract(path)
        total_chars = sum(len(text) for text, _ in extracted_items)
        print(f"Extraction complete: {path.name} - {total_chars:,} chars extracted")

        all_chunks = []

        # Stage 2: Chunk text
        for text, page_num in extracted_items:
            chunks = self.chunked_processor.process_text(
                str(path), text, file_hash, page_num
            )
            enriched = self._enrich_chunks(chunks, path)
            all_chunks.extend(enriched)

        print(f"Chunking complete: {path.name} - {len(all_chunks)} chunks created")
        return all_chunks

    def _process_legacy(self, path: Path) -> List[Dict]:
        """Legacy processing without resume"""
        try:
            return self._do_process(path)
        except Exception as e:
            print(f"Error processing: {path.name}")
            return []

    def _do_process(self, path: Path) -> List[Dict]:
        """Perform processing"""
        extracted_items = self.extractor.extract(path)
        return self._process_pages(extracted_items, path)

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
        self._create_fts_table()
        self._create_processing_progress_table()
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

    def _create_fts_table(self):
        """Create FTS5 full-text search table"""
        try:
            self.conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS fts_chunks
                USING fts5(
                    chunk_id UNINDEXED,
                    content,
                    content='',
                    contentless_delete=1
                )
            """)
        except Exception as e:
            print(f"Note: fts_chunks exists: {e}")

    def _create_processing_progress_table(self):
        """Create processing progress tracking table"""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS processing_progress (
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
        self._insert_fts(chunk_id, chunk['content'])

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

    def _insert_fts(self, chunk_id: int, content: str):
        """Insert into FTS5 index"""
        try:
            self.conn.execute(
                "INSERT INTO fts_chunks (chunk_id, content) VALUES (?, ?)",
                (chunk_id, content)
            )
        except Exception:
            pass

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
        self.hybrid = HybridSearcher(self.conn)

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
              threshold: float = None, query_text: Optional[str] = None,
              use_hybrid: bool = True) -> List[Dict]:
        """Search for similar chunks"""
        vector_results = self.repo.search(query_embedding, top_k, threshold)

        if use_hybrid and query_text:
            return self.hybrid.search(query_text, vector_results, top_k)
        return vector_results

    def get_stats(self) -> Dict:
        """Get statistics"""
        return self.repo.get_stats()

    def close(self):
        """Close connection"""
        self.db_conn.close()
