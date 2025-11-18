import os
import time
from pathlib import Path
from contextlib import asynccontextmanager
from typing import List

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from sentence_transformers import SentenceTransformer

from models import (
    QueryRequest, QueryResponse, SearchResult,
    HealthResponse, IndexRequest, IndexResponse,
    DocumentInfoResponse
)
from ingestion import DocumentProcessor, VectorStore, ProcessingProgressTracker, FileHasher
from domain_models import DocumentFile
from config import default_config
from watcher import FileWatcherService
from query_cache import QueryCache


class AppState:
    """Application state container"""

    def __init__(self):
        self.model = None
        self.vector_store = None
        self.processor = None
        self.watcher = None
        self.cache = None
        self.progress_tracker = None
        self.indexing_in_progress = False
        self.indexing_stats = {"files": 0, "chunks": 0}


# Global state
state = AppState()


class ModelLoader:
    """Loads embedding models"""

    @staticmethod
    def load(model_name: str) -> SentenceTransformer:
        """Load embedding model"""
        print(f"Loading model: {model_name}")
        return SentenceTransformer(model_name)


class FileWalker:
    """Walks knowledge base directory"""

    def __init__(self, base_path: Path, extensions: set):
        self.base_path = base_path
        self.extensions = extensions

    def walk(self):
        """Yield supported files"""
        if not self.base_path.exists():
            return
        yield from self._walk_files()

    def _walk_files(self):
        """Walk all files"""
        for file_path in self.base_path.rglob("*"):
            if self._is_supported(file_path) and not self._is_excluded(file_path):
                yield file_path

    def _is_supported(self, path: Path) -> bool:
        """Check if file is supported"""
        if not path.is_file():
            return False
        return path.suffix.lower() in self.extensions

    def _is_excluded(self, path: Path) -> bool:
        """Check if file path should be excluded from processing"""
        # Exclude files in 'problematic' and 'original' subdirectories
        if 'problematic' in path.parts or 'original' in path.parts:
            return True
        # Exclude temporary files created during processing
        if '.tmp.pdf' in path.name or '.gs_tmp.pdf' in path.name:
            return True
        return False


class DocumentIndexer:
    """Handles document indexing operations"""

    def __init__(self, processor, model, vector_store):
        self.processor = processor
        self.model = model
        self.store = vector_store

    def index_file(self, file_path: Path, force: bool = False) -> int:
        """Index single file"""
        if not self._should_index(file_path, force):
            return self._skip_file(file_path)
        return self._do_index(file_path)

    def _should_index(self, path: Path, force: bool) -> bool:
        """Check if should index"""
        if force:
            return True
        return self._needs_indexing(path)

    def _needs_indexing(self, path: Path) -> bool:
        """Check if file needs indexing"""
        file_hash = FileHasher.hash_file(path)
        indexed = self.store.is_document_indexed(str(path), file_hash)
        return not indexed

    @staticmethod
    def _skip_file(path: Path) -> int:
        """Skip file logging"""
        print(f"Skipping: {path.name}")
        return 0

    def _do_index(self, path: Path) -> int:
        """Perform indexing"""
        print(f"Processing: {path.name}")
        file_hash = FileHasher.hash_file(path)
        doc_file = DocumentFile(path=path, hash=file_hash)
        chunks = self._get_chunks(doc_file)
        return self._store_if_valid(doc_file, chunks)

    def _get_chunks(self, doc_file: DocumentFile) -> List:
        """Extract chunks from file"""
        chunks = self.processor.process_file(doc_file)
        if not chunks:
            print(f"No chunks: {doc_file.name}")
        return chunks

    def _store_if_valid(self, doc_file: DocumentFile, chunks: List) -> int:
        """Store chunks if valid"""
        if not chunks:
            return 0
        self._store_chunks(doc_file, chunks)
        return len(chunks)

    def _store_chunks(self, doc_file: DocumentFile, chunks: List):
        """Store chunks with embeddings"""
        print(f"Embedding started: {doc_file.name} - {len(chunks)} chunks")
        embeddings = self._gen_embeddings(chunks)
        print(f"Embedding complete: {doc_file.name} - {len(chunks)} chunks embedded")
        self._add_to_store(doc_file.path, doc_file.hash, chunks, embeddings)
        print(f"Indexed {doc_file.name}: {len(chunks)} chunks stored")

    def _gen_embeddings(self, chunks: List) -> List:
        """Generate embeddings"""
        texts = [c['content'] for c in chunks]
        embeddings = self.model.encode(texts, show_progress_bar=False)
        return [emb.tolist() for emb in embeddings]

    def _add_to_store(self, path, hash_val, chunks, embeddings):
        """Add to vector store"""
        self.store.add_document(
            file_path=str(path),
            file_hash=hash_val,
            chunks=chunks,
            embeddings=embeddings
        )


class IndexOrchestrator:
    """Orchestrates full indexing process"""

    def __init__(self, base_path: Path, indexer, processor, progress_tracker=None):
        self.base_path = base_path
        self.indexer = indexer
        self.walker = self._create_walker(base_path, processor)
        self.tracker = progress_tracker

    @staticmethod
    def _create_walker(base_path, processor):
        """Create file walker"""
        return FileWalker(base_path, processor.SUPPORTED_EXTENSIONS)

    def resume_incomplete_processing(self):
        """Resume processing incomplete files"""
        if not self.tracker:
            return
        incomplete = self.tracker.get_incomplete_files()
        if not incomplete:
            return
        print(f"Resuming {len(incomplete)} incomplete files...")
        self._process_incomplete(incomplete)

    def _process_incomplete(self, incomplete):
        """Process incomplete files"""
        for progress in incomplete:
            self._resume_one(progress)

    def _resume_one(self, progress):
        """Resume one file"""
        try:
            file_path = Path(progress.file_path)
            if not file_path.exists():
                self.tracker.mark_failed(progress.file_path, "File no longer exists")
                return
            self.indexer.index_file(file_path, force=True)
        except Exception as e:
            print(f"Failed to resume {progress.file_path}: {e}")
            self.tracker.mark_failed(progress.file_path, str(e))

    def index_all(self, force: bool = False) -> tuple[int, int]:
        """Index all documents"""
        if not self.base_path.exists():
            return self._handle_missing()
        return self._index_files(force)

    def _handle_missing(self) -> tuple[int, int]:
        """Handle missing path"""
        print(f"Path missing: {self.base_path}")
        return 0, 0

    def _index_files(self, force: bool) -> tuple[int, int]:
        """Index all files with batch processing"""
        indexed_files = 0
        total_chunks = 0
        file_count = 0
        batch_size = default_config.batch.size
        batch_delay = default_config.batch.delay

        for file_path in self.walker.walk():
            files, chunks = self._index_one(file_path, force, indexed_files, total_chunks)
            indexed_files, total_chunks = files, chunks
            file_count += 1

            # Add delay after each batch to prevent resource spikes
            if file_count % batch_size == 0:
                time.sleep(batch_delay)

        return indexed_files, total_chunks

    def _index_one(self, path, force, files, chunks):
        """Index one file"""
        new_chunks = self._try_index(path, force)
        if new_chunks > 0:
            return files + 1, chunks + new_chunks
        return files, chunks

    def _try_index(self, path: Path, force: bool) -> int:
        """Try indexing with error handling"""
        try:
            return self.indexer.index_file(path, force)
        except Exception as e:
            print(f"Error: {path.name}: indexing failed")
            return 0


class QueryExecutor:
    """Executes semantic search queries"""

    def __init__(self, model, vector_store, cache=None):
        self.model = model
        self.store = vector_store
        self.cache = cache

    def execute(self, request: QueryRequest) -> QueryResponse:
        """Execute search query"""
        self._validate(request.text)

        if self.cache:
            cached = self.cache.get(request.text, request.top_k, request.threshold)
            if cached:
                return self._format(cached, request.text)

        embedding = self._gen_embedding(request.text)
        results = self._search(embedding, request)

        if self.cache:
            self.cache.put(request.text, request.top_k, request.threshold, results)

        return self._format(results, request.text)

    @staticmethod
    def _validate(text: str):
        """Validate query text"""
        if not text.strip():
            raise ValueError("Query cannot be empty")

    def _gen_embedding(self, text: str):
        """Generate query embedding"""
        return self.model.encode(text, show_progress_bar=False)

    def _search(self, embedding, request):
        """Search vector store"""
        return self.store.search(
            query_embedding=embedding.tolist(),
            top_k=request.top_k,
            threshold=request.threshold,
            query_text=request.text,
            use_hybrid=True
        )

    @staticmethod
    def _format(results: List, query: str) -> QueryResponse:
        """Format response"""
        search_results = QueryExecutor._to_models(results)
        return QueryResponse(
            results=search_results,
            query=query,
            total_results=len(search_results)
        )

    @staticmethod
    def _to_models(results: List) -> List[SearchResult]:
        """Convert to models"""
        return [
            SearchResult(
                content=r['content'],
                source=r['source'],
                page=r['page'],
                score=r['score']
            )
            for r in results
        ]


class StartupManager:
    """Manages application startup"""

    def __init__(self, app_state: AppState):
        self.state = app_state

    def initialize(self):
        """Initialize all components"""
        print("Initializing RAG system...")
        self._load_model()
        self._init_store()
        self._init_progress_tracker()
        self._init_processor()
        self._init_cache()
        self._resume_incomplete()
        print("RAG system ready! Starting background indexing...")
        self._start_background_indexing()

    def _load_model(self):
        """Load embedding model"""
        loader = ModelLoader()
        model_name = default_config.model.name
        self.state.model = loader.load(model_name)

    def _init_store(self):
        """Initialize vector store"""
        print("Initializing vector store...")
        self.state.vector_store = VectorStore()

    def _init_progress_tracker(self):
        """Initialize progress tracker"""
        if default_config.processing.enabled:
            db_path = default_config.database.path
            self.state.progress_tracker = ProcessingProgressTracker(db_path)
            print("Resumable processing enabled")

    def _init_processor(self):
        """Initialize processor"""
        self.state.processor = DocumentProcessor(self.state.progress_tracker)

    def _init_cache(self):
        """Initialize query cache"""
        if default_config.cache.enabled:
            self.state.cache = QueryCache(default_config.cache.max_size)
            print(f"Query cache enabled (size: {default_config.cache.max_size})")
        else:
            print("Query cache disabled")

    def _resume_incomplete(self):
        """Resume incomplete processing"""
        if not self.state.progress_tracker:
            return
        orchestrator = self._create_orchestrator()
        orchestrator.resume_incomplete_processing()

    def _index_docs(self):
        """Index documents"""
        print("Indexing documents...")
        try:
            self._run_indexing()
        except Exception as e:
            print("Indexing error occurred")

    def _run_indexing(self):
        """Run indexing process"""
        orchestrator = self._create_orchestrator()
        files, chunks = orchestrator.index_all()
        self.state.indexing_stats = {"files": files, "chunks": chunks}
        print(f"Indexed {files} docs, {chunks} chunks")

    def _create_orchestrator(self):
        """Create orchestrator"""
        indexer = self._create_indexer()
        kb_path = default_config.paths.knowledge_base
        return IndexOrchestrator(kb_path, indexer, self.state.processor, self.state.progress_tracker)

    def _create_indexer(self):
        """Create indexer"""
        return DocumentIndexer(
            self.state.processor,
            self.state.model,
            self.state.vector_store
        )

    def _start_background_indexing(self):
        """Start indexing in background thread"""
        import threading
        thread = threading.Thread(target=self._background_indexing_task, daemon=True)
        thread.start()

    def _background_indexing_task(self):
        """Background task for indexing and watcher startup"""
        # Start watcher first so system is responsive immediately
        self._start_watcher()

        # Then do indexing in background
        self.state.indexing_in_progress = True
        try:
            self._index_docs()
        finally:
            self.state.indexing_in_progress = False

    def _start_watcher(self):
        """Start file watcher if enabled"""
        if not default_config.watcher.enabled:
            print("File watcher disabled")
            return

        indexer = self._create_indexer()
        self.state.watcher = FileWatcherService(
            watch_path=default_config.paths.knowledge_base,
            indexer=indexer,
            debounce_seconds=default_config.watcher.debounce_seconds,
            batch_size=default_config.watcher.batch_size
        )
        self.state.watcher.start()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan"""
    manager = StartupManager(state)
    manager.initialize()
    yield
    _cleanup()


def _cleanup():
    """Cleanup resources"""
    if state.watcher:
        state.watcher.stop()
    if state.vector_store:
        state.vector_store.close()
    if state.progress_tracker:
        state.progress_tracker.close()


app = FastAPI(
    title="RAG Knowledge Base API",
    description="Local RAG system for querying your knowledge base",
    version="0.1.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", include_in_schema=False)
async def root():
    """Root endpoint"""
    return {
        "message": "RAG Knowledge Base API",
        "docs": "/docs",
        "health": "/health"
    }


@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check"""
    stats = state.vector_store.get_stats()
    return HealthResponse(
        status="healthy",
        indexed_documents=stats['indexed_documents'],
        total_chunks=stats['total_chunks'],
        model=default_config.model.name,
        indexing_in_progress=state.indexing_in_progress
    )


@app.post("/query", response_model=QueryResponse)
async def query(request: QueryRequest):
    """Query the knowledge base"""
    try:
        executor = QueryExecutor(state.model, state.vector_store, state.cache)
        return executor.execute(request)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Query failed")


@app.post("/index", response_model=IndexResponse)
async def index(request: IndexRequest, background_tasks: BackgroundTasks):
    """Trigger reindexing"""
    try:
        result = _do_reindex(request.force_reindex)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail="Indexing failed")


@app.get("/document/{filename}", response_model=DocumentInfoResponse)
async def get_document_info(filename: str):
    """Get document information including extraction method"""
    try:
        info = state.vector_store.get_document_info(filename)
        if not info:
            raise HTTPException(status_code=404, detail=f"Document not found: {filename}")
        return DocumentInfoResponse(**info)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to retrieve document info")


def _do_reindex(force: bool) -> IndexResponse:
    """Perform reindexing"""
    indexer = _build_indexer()
    orchestrator = _build_orchestrator(indexer)
    files, chunks = orchestrator.index_all(force)
    return _build_response(files, chunks)


def _build_indexer():
    """Build document indexer"""
    return DocumentIndexer(
        state.processor,
        state.model,
        state.vector_store
    )


def _build_orchestrator(indexer):
    """Build orchestrator"""
    kb_path = default_config.paths.knowledge_base
    return IndexOrchestrator(kb_path, indexer, state.processor, state.progress_tracker)


def _build_response(files: int, chunks: int) -> IndexResponse:
    """Build index response"""
    return IndexResponse(
        status="success",
        indexed_files=files,
        total_chunks=chunks,
        message=f"Indexed {files} files, {chunks} chunks"
    )


class DocumentLister:
    """Lists indexed documents"""

    def __init__(self, vector_store):
        self.store = vector_store

    def list_all(self) -> dict:
        """List all documents"""
        cursor = self._query()
        documents = self._format(cursor)
        return self._build_response(documents)

    def _query(self):
        """Query documents"""
        return self.store.conn.execute("""
            SELECT d.file_path, d.indexed_at, COUNT(c.id)
            FROM documents d
            LEFT JOIN chunks c ON d.id = c.document_id
            GROUP BY d.id
            ORDER BY d.indexed_at DESC
        """)

    @staticmethod
    def _format(cursor) -> List[dict]:
        """Format results"""
        documents = []
        for row in cursor:
            DocumentLister._add_doc(documents, row)
        return documents

    @staticmethod
    def _add_doc(documents: List, row):
        """Add document to list"""
        documents.append({
            'file_path': row[0],
            'indexed_at': row[1],
            'chunk_count': row[2]
        })

    @staticmethod
    def _build_response(documents: List) -> dict:
        """Build response dict"""
        return {
            'total_documents': len(documents),
            'documents': documents
        }


@app.get("/documents")
async def list_documents():
    """List all documents"""
    try:
        lister = DocumentLister(state.vector_store)
        return lister.list_all()
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="Failed to list documents"
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
