import os
import time
from pathlib import Path
from contextlib import asynccontextmanager
from typing import List
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
import threading
from collections import defaultdict

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from sentence_transformers import SentenceTransformer

from models import (
    QueryRequest, QueryResponse, SearchResult,
    HealthResponse, IndexRequest, IndexResponse,
    DocumentInfoResponse
)
from ingestion import DocumentProcessor, VectorStore, ProcessingProgressTracker, FileHasher
from ingestion.file_filter import FileFilterPolicy
from domain_models import DocumentFile
from config import default_config
from watcher import FileWatcherService
from query_cache import QueryCache
from value_objects import IndexingStats, ProcessingResult, DocumentIdentity
from app_state import AppState

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
    """Walks knowledge base directory

    Refactored following Sandi Metz principles:
    - Dependency Injection: filter_policy injected vs. hardcoded
    - Single Responsibility: Only handles directory walking
    - Small class: Reduced from ~70 lines to ~20 lines
    """

    def __init__(self, base_path: Path, extensions: set, filter_policy: FileFilterPolicy = None):
        self.base_path = base_path
        self.extensions = extensions
        self.filter_policy = filter_policy or FileFilterPolicy()

    def walk(self):
        """Yield supported files"""
        if not self.base_path.exists():
            return
        yield from self._walk_files()

    def _walk_files(self):
        """Walk all files"""
        for file_path in self.base_path.rglob("*"):
            if self._is_supported(file_path) and not self.filter_policy.should_exclude(file_path):
                yield file_path

    def _is_supported(self, path: Path) -> bool:
        """Check if file is supported"""
        if not path.is_file():
            return False
        return path.suffix.lower() in self.extensions

class DocumentIndexer:
    """Handles document indexing operations with async embedding"""

    def __init__(self, processor, embedding_service):
        self.processor = processor
        self.embedding_service = embedding_service

    def index_file(self, file_path: Path, force: bool = False, stage_callback=None) -> ProcessingResult:
        """Index single file. Returns ProcessingResult"""
        self.stage_callback = stage_callback
        if not self._should_index(file_path, force):
            return ProcessingResult.skipped()
        chunks = self._do_index(file_path)
        return ProcessingResult.success(chunks_count=chunks)

    def _should_index(self, path: Path, force: bool) -> bool:
        """Check if should index"""
        if force:
            return True
        return self._needs_indexing(path)

    def _needs_indexing(self, path: Path) -> bool:
        """Check if file needs indexing"""
        file_hash = FileHasher.hash_file(path)
        indexed = self.embedding_service.is_indexed(str(path), file_hash)
        return not indexed

    def _do_index(self, path: Path) -> int:
        """Perform indexing

        Following Sandi Metz 'Tell, Don't Ask': Let DocumentFile create itself
        """
        print(f"[DEBUG] _do_index: stage_callback is {'SET' if self.stage_callback else 'NONE'}")
        if self.stage_callback:
            self.stage_callback("extracting")
        doc_file = DocumentFile.from_path(path)
        chunks = self._get_chunks(doc_file)
        return self._store_if_valid(doc_file, chunks)

    def _get_chunks(self, doc_file: DocumentFile) -> List:
        """Extract chunks from file"""
        if self.stage_callback:
            self.stage_callback("chunking")
        chunks = self.processor.process_file(doc_file)
        # Silent when no chunks - avoid log spam
        return chunks

    def _store_if_valid(self, doc_file: DocumentFile, chunks: List) -> int:
        """Store chunks if valid"""
        if not chunks:
            # Add 0-chunk files to documents table to mark as "processed"
            # This prevents reprocessing on every startup
            self.embedding_service.add_empty_document(
                file_path=str(doc_file.path),
                file_hash=doc_file.hash
            )
            # Clean up progress tracker
            self.processor.delete_from_tracker(str(doc_file.path))
            return 0
        if self.stage_callback:
            self.stage_callback("embedding")
        self._store_chunks(doc_file, chunks)
        if self.stage_callback:
            self.stage_callback("storing")
        return len(chunks)

    def _store_chunks(self, doc_file: DocumentFile, chunks: List):
        """Store chunks with async embeddings"""
        identity = DocumentIdentity.from_file(doc_file.path, doc_file.hash)
        self.embedding_service.queue_embedding(identity, chunks)

    def wait_for_pending(self):
        """Wait for all pending embeddings to complete"""
        self.embedding_service.wait_for_all()

    def get_obsidian_graph(self):
        """Get Obsidian knowledge graph.

        Delegation method to avoid Law of Demeter violation.
        """
        return self.processor.get_obsidian_graph()

class IndexOrchestrator:
    """Orchestrates full indexing process via queue

    All file processing routes through IndexingQueue for concurrent pipeline processing.
    """

    def __init__(self, base_path: Path, indexer, processor, progress_tracker=None, queue=None):
        self.base_path = base_path
        self.indexer = indexer
        self.walker = self._create_walker(base_path, processor)
        self.tracker = progress_tracker
        self.queue = queue

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
        """Add incomplete file to queue with HIGH priority for reprocessing"""
        try:
            file_path = Path(progress.file_path)
            if not file_path.exists():
                self.tracker.mark_failed(progress.file_path, "File no longer exists")
                return

            if not self.queue:
                print(f"WARNING: No queue available, cannot resume {file_path.name}")
                return

            from services import Priority
            self.queue.add(file_path, priority=Priority.HIGH, force=True)
            print(f"Queued incomplete file for reprocessing: {file_path.name}")
        except Exception as e:
            print(f"Failed to queue {progress.file_path}: {e}")
            self.tracker.mark_failed(progress.file_path, str(e))

    def index_all(self, queue, force: bool = False) -> tuple[int, int]:
        """Index all documents via queue

        All files are added to the queue for concurrent pipeline processing.

        Args:
            queue: IndexingQueue for file processing (required)
            force: If True, reindex even if already indexed

        Returns:
            Tuple of (files_queued, 0) - chunks count is 0 as processing is async
        """
        if not self.base_path.exists():
            return self._handle_missing()
        return self._index_files(queue)

    def _handle_missing(self) -> tuple[int, int]:
        """Handle missing path"""
        print(f"Path missing: {self.base_path}")
        return 0, 0

    def _group_files_for_display(self, files: List[Path]) -> str:
        """Group files by directory for cleaner display"""
        root_pdfs, dir_groups = self._categorize_files(files)
        return self._build_display(root_pdfs, dir_groups)

    def _categorize_files(self, files: List[Path]) -> tuple:
        """Categorize files into root PDFs and directory groups"""
        root_pdfs = []
        dir_groups = defaultdict(list)
        for file_path in files:
            self._categorize_one(file_path, root_pdfs, dir_groups)
        return root_pdfs, dir_groups

    def _categorize_one(self, file_path: Path, root_pdfs: List, dir_groups: dict):
        """Categorize a single file"""
        parts = file_path.parts
        kb_index = parts.index('knowledge_base') if 'knowledge_base' in parts else -1
        if kb_index >= 0 and kb_index + 2 < len(parts):
            subdir = parts[kb_index + 1]
            dir_groups[subdir].append(file_path)
        elif file_path.suffix == '.pdf':
            root_pdfs.append(file_path)

    def _build_display(self, root_pdfs: List, dir_groups: dict) -> str:
        """Build display string from categorized files"""
        lines = []
        if root_pdfs:
            lines.extend(self._format_root_pdfs(root_pdfs))
        if dir_groups:
            if root_pdfs:
                lines.append("")
            lines.extend(self._format_directories(dir_groups))
        return "\n".join(lines)

    def _format_root_pdfs(self, root_pdfs: List) -> List[str]:
        """Format root PDF list"""
        lines = ["PDFs:"]
        for pdf in sorted(root_pdfs):
            lines.append(f"  - {pdf.name}")
        return lines

    def _format_directories(self, dir_groups: dict) -> List[str]:
        """Format directory groups"""
        lines = ["Directories:"]
        for dir_name, files in sorted(dir_groups.items(), key=lambda x: -len(x[1])):
            lines.append(f"  - {dir_name}/ ({len(files)} files)")
        return lines

    def _index_files(self, queue) -> tuple[int, int]:
        """Add all files to queue for concurrent pipeline processing

        Args:
            queue: IndexingQueue for file processing

        Returns:
            Tuple of (files_queued, 0) - chunks count is 0 as processing is async
        """
        all_files = list(self.walker.walk())
        if not all_files:
            return 0, 0
        self._print_files_found(all_files)
        return self._enqueue_files(all_files, queue)

    def _enqueue_files(self, all_files: List, queue) -> tuple[int, int]:
        """Add files to queue for worker processing"""
        from services import Priority
        queue.add_many(all_files, priority=Priority.NORMAL)
        print(f"Added {len(all_files)} files to indexing queue")
        return len(all_files), 0

    def _print_files_found(self, all_files: List):
        """Print files found message"""
        print(f"Found {len(all_files)} files to process")
        print(self._group_files_for_display(all_files))

    def _persist_obsidian_graph(self):
        """Persist Obsidian knowledge graph to database"""
        try:
            graph_export = self._get_graph_export()
            if self._has_graph_content(graph_export):
                self._save_graph(graph_export)
        except Exception as e:
            print(f"Warning: Failed to persist graph: {e}")

    def _get_graph_export(self):
        """Get graph export from processor"""
        obsidian_graph = self.indexer.get_obsidian_graph()
        return obsidian_graph.export_graph()

    def _has_graph_content(self, graph_export):
        """Check if graph has content worth persisting"""
        return graph_export['stats']['total_nodes'] > 0

    def _save_graph(self, graph_export):
        """Save graph to database"""
        from ingestion.graph_repository import GraphRepository
        from ingestion.database import DatabaseConnection

        db = DatabaseConnection()
        conn = db.connect()
        graph_repo = GraphRepository(conn)
        graph_repo.persist_graph(graph_export)
        graph_repo.commit()
        db.close()
        self._print_graph_stats(graph_export)

    def _print_graph_stats(self, graph_export):
        """Print graph persistence statistics"""
        print(f"Graph persisted: {graph_export['stats']['total_nodes']} nodes, "
              f"{graph_export['stats']['total_edges']} edges")

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

class OrphanDetector:
    """Detects and repairs orphaned files (processed but not embedded)"""

    def __init__(self, progress_tracker, vector_store):
        self.tracker = progress_tracker
        self.store = vector_store

    def detect_orphans(self):
        """Detect orphaned files"""
        if not self.tracker:
            return []

        import sqlite3
        conn = sqlite3.connect(self.tracker.get_db_path())
        cursor = conn.execute('''
            SELECT pp.file_path, pp.chunks_processed, pp.last_updated
            FROM processing_progress pp
            LEFT JOIN documents d ON pp.file_path = d.file_path
            WHERE pp.status = 'completed' AND d.id IS NULL
            ORDER BY pp.last_updated DESC
        ''')
        orphans = [{'path': row[0], 'chunks': row[1], 'updated': row[2]} for row in cursor.fetchall()]
        conn.close()
        return orphans

    def repair_orphans(self, queue):
        """Repair orphaned files by adding them to queue with HIGH priority"""
        from services.indexing_queue import Priority

        orphans = self.detect_orphans()
        if not orphans:
            return 0
        self._print_header(orphans)
        stats = self._add_to_queue(orphans, queue)
        self._print_summary(stats)
        return stats['queued']

    def _print_header(self, orphans):
        """Print repair header and sample"""
        print(f"\n{'='*80}")
        print(f"Found {len(orphans)} orphaned files (processed but not embedded)")
        print(f"{'='*80}")
        print("\nSample orphaned files:")
        for orphan in orphans[:5]:
            filename = orphan['path'].split('/')[-1]
            print(f"  - {filename} ({orphan['updated']})")
        if len(orphans) > 5:
            print(f"  ... and {len(orphans) - 5} more\n")
        print("Repairing orphaned files...")

    def _add_to_queue(self, orphans, queue):
        """Add all orphaned files to queue with HIGH priority"""
        stats = {'queued': 0, 'non_existent': 0}
        for idx, orphan in enumerate(orphans):
            self._show_progress(idx, len(orphans), stats)
            self._queue_one(orphan, queue, stats)
        return stats

    def _show_progress(self, idx, total, stats):
        """Show progress every 50 files"""
        if self._is_progress_milestone(idx):
            self._print_progress(idx, total, stats)

    def _is_progress_milestone(self, idx):
        """Check if should show progress"""
        return idx > 0 and idx % 50 == 0

    def _print_progress(self, idx, total, stats):
        """Print progress message"""
        print(f"Orphan repair progress: {idx}/{total} "
              f"({stats['queued']} queued, {stats['non_existent']} non-existent)")

    def _queue_one(self, orphan, queue, stats):
        """Queue one orphaned file for reindexing"""
        from pathlib import Path
        from services.indexing_queue import Priority

        try:
            path = Path(orphan['path'])
            if not path.exists():
                self._handle_non_existent(orphan, stats)
                return

            # Delete from tracker so it can be reprocessed
            self.tracker.delete_document(str(path))

            # Add to queue with HIGH priority (orphans process before normal files)
            queue.add(path, priority=Priority.HIGH, force=True)
            stats['queued'] += 1

        except Exception as e:
            print(f"ERROR queuing {orphan['path'].split('/')[-1]}: {e}")

    def _handle_non_existent(self, orphan, stats):
        """Handle non-existent orphan files"""
        self.tracker.delete_document(orphan['path'])
        stats['non_existent'] += 1

    def _print_summary(self, stats):
        """Print repair summary"""
        print(f"\nNon-existent files cleaned: {stats['non_existent']}")
        print(f"\n{'='*80}")
        print(f"Orphan repair complete: {stats['queued']} files queued for reindexing")
        print(f"{'='*80}\n")

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
        self._init_queue_and_worker()
        print("RAG system ready! Starting sanitization and indexing...")
        self._start_background_indexing()

    def _load_model(self):
        """Load embedding model"""
        loader = ModelLoader()
        model_name = default_config.model.name
        self.state.core.model = loader.load(model_name)

    def _init_store(self):
        """Initialize vector store"""
        print("Initializing vector store...")
        self.state.core.vector_store = VectorStore()

    def _init_progress_tracker(self):
        """Initialize progress tracker"""
        if default_config.processing.enabled:
            db_path = default_config.database.path
            self.state.core.progress_tracker = ProcessingProgressTracker(db_path)
            print("Resumable processing enabled")

    def _init_processor(self):
        """Initialize processor"""
        self.state.core.processor = DocumentProcessor(self.state.core.progress_tracker)

    def _init_cache(self):
        """Initialize query cache"""
        if default_config.cache.enabled:
            self.state.query.cache = QueryCache(default_config.cache.max_size)
            print(f"Query cache enabled (size: {default_config.cache.max_size})")
        else:
            print("Query cache disabled")

    def _init_queue_and_worker(self):
        """Initialize indexing queue and worker"""
        from services import IndexingQueue, IndexingWorker
        self.state.indexing.queue = IndexingQueue()
        indexer = self._create_indexer()

        # Initialize concurrent pipeline first
        self._init_concurrent_pipeline()

        # Create worker with pipeline coordinator
        self.state.indexing.worker = IndexingWorker(
            self.state.indexing.queue,
            indexer,
            pipeline_coordinator=self.state.indexing.pipeline_coordinator
        )
        self.state.indexing.worker.start()
        print("Indexing queue and worker started")

    def _init_concurrent_pipeline(self):
        """Initialize concurrent pipeline for parallel processing"""
        if not self._is_pipeline_enabled():
            return

        embedding_service = self._create_embedding_service()
        indexer = self._create_indexer()
        self._start_pipeline(embedding_service, indexer)

    def _is_pipeline_enabled(self) -> bool:
        """Check if concurrent pipeline is enabled"""
        import os
        enable_pipeline = os.getenv('ENABLE_CONCURRENT_PIPELINE', 'true').lower() == 'true'
        if not enable_pipeline:
            print("Concurrent pipeline disabled")
            self.state.indexing.pipeline_coordinator = None
        return enable_pipeline

    def _create_embedding_service(self):
        """Create embedding service with environment config"""
        import os
        from services.embedding_service import EmbeddingService

        max_workers = int(os.getenv('EMBEDDING_WORKERS', '3'))
        max_pending = int(os.getenv('MAX_PENDING_EMBEDDINGS', '6'))

        return EmbeddingService(
            self.state.core.model,
            self.state.core.vector_store,
            max_workers=max_workers,
            max_pending=max_pending
        )

    def _start_pipeline(self, embedding_service, indexer):
        """Start pipeline coordinator"""
        from services.pipeline_coordinator import PipelineCoordinator

        self.state.indexing.pipeline_coordinator = PipelineCoordinator(
            processor=self.state.core.processor,
            indexer=indexer,
            embedding_service=embedding_service
        )
        self.state.indexing.pipeline_coordinator.start()
        print("Concurrent pipeline started")

    def _sanitize_before_indexing(self):
        """Sanitization stage: detect and repair issues before new indexing

        Flow:
        1. Resume incomplete files
        2. Detect and repair orphans (files in DB without embeddings)
        3. Only after repairs complete, allow new file processing
        """
        if not self.state.core.progress_tracker:
            return

        print("\n=== Starting Sanitization Stage ===")
        self._resume_incomplete_files()
        self._repair_orphaned_files()
        print("=== Sanitization Complete ===\n")

    def _resume_incomplete_files(self):
        """Resume processing of incomplete files"""
        print("Checking for incomplete files...")
        orchestrator = self._create_orchestrator()
        orchestrator.resume_incomplete_processing()

    def _repair_orphaned_files(self):
        """Detect and repair orphaned files if auto-repair enabled"""
        if not self._is_auto_repair_enabled():
            return

        orphans = self._detect_orphans()
        if orphans:
            self._queue_orphans_for_repair(orphans)
        else:
            print("No orphaned files found")

    def _is_auto_repair_enabled(self) -> bool:
        """Check if auto-repair is enabled"""
        import os
        auto_repair = os.getenv('AUTO_REPAIR_ORPHANS', 'true').lower() == 'true'
        if not auto_repair:
            print("Auto-repair disabled, skipping orphan check")
        return auto_repair

    def _detect_orphans(self):
        """Detect orphaned files"""
        detector = OrphanDetector(self.state.core.progress_tracker, self.state.core.vector_store)
        return detector.detect_orphans()

    def _queue_orphans_for_repair(self, orphans):
        """Queue orphaned files for repair"""
        print(f"Found {len(orphans)} orphaned files")
        print("Adding orphans to queue with HIGH priority...\n")
        detector = OrphanDetector(self.state.core.progress_tracker, self.state.core.vector_store)
        detector.repair_orphans(self.state.indexing.queue)
        print("Orphans queued for reindexing")

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
        files, chunks = orchestrator.index_all(queue=self.state.indexing.queue)
        self.state.runtime.stats = IndexingStats(files=files, chunks=chunks)
        if files > 0:
            print(f"Indexed {files} docs, {chunks} chunks")

    def _create_orchestrator(self):
        """Create orchestrator with queue for concurrent pipeline"""
        indexer = self._create_indexer()
        kb_path = default_config.paths.knowledge_base
        return IndexOrchestrator(
            kb_path,
            indexer,
            self.state.core.processor,
            self.state.core.progress_tracker,
            queue=self.state.indexing.queue
        )

    def _create_indexer(self):
        """Create indexer"""
        from services import EmbeddingService
        import os
        embedding_workers = int(os.getenv('EMBEDDING_WORKERS', '3'))
        max_pending = int(os.getenv('MAX_PENDING_EMBEDDINGS', str(embedding_workers * 2)))
        embedding_service = EmbeddingService(
            model=self.state.core.model,
            vector_store=self.state.core.vector_store,
            max_workers=embedding_workers,
            max_pending=max_pending,
            processor=self.state.core.processor
        )
        return DocumentIndexer(
            self.state.core.processor,
            embedding_service
        )

    def _start_background_indexing(self):
        """Start indexing in background thread"""
        import threading
        thread = threading.Thread(target=self._background_indexing_task, daemon=True)
        thread.start()

    def _background_indexing_task(self):
        """Background task with sanitization stage before indexing"""
        # Start watcher first so system is responsive immediately
        self._start_watcher()

        # Sanitization stage: repair before new indexing
        self._sanitize_before_indexing()

        # Then do indexing in background
        self.state.runtime.indexing_in_progress = True
        try:
            self._index_docs()
        finally:
            self.state.runtime.indexing_in_progress = False

    def _start_watcher(self):
        """Start file watcher if enabled"""
        if not default_config.watcher.enabled:
            print("File watcher disabled")
            return

        self.state.runtime.watcher = FileWatcherService(
            watch_path=default_config.paths.knowledge_base,
            queue=self.state.indexing.queue,
            debounce_seconds=default_config.watcher.debounce_seconds,
            batch_size=default_config.watcher.batch_size
        )
        self.state.runtime.watcher.start()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan"""
    manager = StartupManager(state)
    manager.initialize()
    yield
    _cleanup()

def _cleanup():
    """Cleanup resources"""
    if state.runtime.watcher:
        state.runtime.watcher.stop()
    if state.indexing.worker:
        state.indexing.worker.stop()
    if state.core.vector_store:
        state.core.vector_store.close()
    if state.core.progress_tracker:
        state.core.progress_tracker.close()

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
    stats = state.core.vector_store.get_stats()
    return HealthResponse(
        status="healthy",
        indexed_documents=stats['indexed_documents'],
        total_chunks=stats['total_chunks'],
        model=default_config.model.name,
        indexing_in_progress=state.runtime.indexing_in_progress
    )

@app.post("/query", response_model=QueryResponse)
async def query(request: QueryRequest):
    """Query the knowledge base"""
    try:
        executor = QueryExecutor(state.core.model, state.core.vector_store, state.query.cache)
        return executor.execute(request)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Query failed")

@app.post("/index", response_model=IndexResponse)
async def index(request: IndexRequest, background_tasks: BackgroundTasks):
    """Trigger reindexing via queue + concurrent pipeline

    Adds all files to the indexing queue for processing by the
    concurrent pipeline. Returns immediately - check /indexing/status
    or /queue/jobs to monitor progress.
    """
    try:
        if not state.indexing.queue:
            raise HTTPException(status_code=400, detail="Indexing queue not initialized")

        # Add all files to queue
        from services.file_filter import FileFilter
        kb_path = default_config.paths.knowledge_base
        file_filter = FileFilter(kb_path)
        all_files = file_filter.get_files()

        from services import Priority
        priority = Priority.HIGH if request.force_reindex else Priority.NORMAL
        state.indexing.queue.add_many(all_files, priority=priority, force=request.force_reindex)

        return IndexResponse(
            status="success",
            indexed_files=0,
            total_chunks=0,
            message=f"Queued {len(all_files)} files for indexing (force={request.force_reindex}). Check /queue/jobs for progress."
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue files: {str(e)}")

@app.post("/repair-orphans")
async def repair_orphans():
    """Repair orphaned files (processed but not embedded)

    Orphaned files occur when processing completes but embedding fails.
    This endpoint detects and repairs them by reindexing.
    """
    try:
        if not state.core.progress_tracker:
            raise HTTPException(
                status_code=400,
                detail="Progress tracking not enabled"
            )

        detector = OrphanDetector(state.core.progress_tracker, state.core.vector_store)
        orphans = detector.detect_orphans()

        if not orphans:
            return {
                "status": "success",
                "orphans_found": 0,
                "orphans_repaired": 0,
                "message": "No orphaned files found"
            }

        # Repair orphans by adding to queue with HIGH priority
        queued = detector.repair_orphans(state.indexing.queue)

        return {
            "status": "success",
            "orphans_found": len(orphans),
            "orphans_queued": queued,
            "message": f"Queued {queued} orphaned files for reindexing with HIGH priority"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to repair orphans: {str(e)}"
        )

@app.get("/document/{filename}", response_model=DocumentInfoResponse)
async def get_document_info(filename: str):
    """Get document information including extraction method"""
    try:
        info = state.core.vector_store.get_document_info(filename)
        if not info:
            raise HTTPException(status_code=404, detail=f"Document not found: {filename}")
        return DocumentInfoResponse(**info)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to retrieve document info")

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
        return self.store.query_documents_with_chunks()

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
        lister = DocumentLister(state.core.vector_store)
        return lister.list_all()
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="Failed to list documents"
        )

@app.get("/documents/search")
async def search_documents(pattern: str = None):
    """Search for documents by file path pattern

    Args:
        pattern: Optional substring to search for in file paths (case-insensitive)
                 Examples: "AFTS", "notebook", ".pdf", "chapter1"

    Returns:
        List of matching documents with their metadata
    """
    try:
        searcher = DocumentSearcher()
        return searcher.search(pattern)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to search documents: {str(e)}"
        )

class DocumentSearcher:
    """Searches for documents in database"""

    def search(self, pattern: str = None) -> dict:
        """Search documents by pattern"""
        results = self._query_documents(pattern)
        documents = self._format_results(results)
        return self._build_response(pattern, documents)

    def _query_documents(self, pattern: str = None):
        """Query documents with optional pattern"""
        import sqlite3
        conn = sqlite3.connect(default_config.database.path)

        if pattern:
            results = self._search_with_pattern(conn, pattern)
        else:
            results = self._list_all_documents(conn)

        conn.close()
        return results

    def _search_with_pattern(self, conn, pattern: str):
        """Search with pattern filter"""
        cursor = conn.execute("""
            SELECT d.id, d.file_path, d.file_hash, d.indexed_at, COUNT(c.id) as chunk_count
            FROM documents d
            LEFT JOIN chunks c ON d.id = c.document_id
            WHERE d.file_path LIKE ?
            GROUP BY d.id
            ORDER BY d.indexed_at DESC
        """, (f"%{pattern}%",))
        return cursor.fetchall()

    def _list_all_documents(self, conn):
        """List all documents"""
        cursor = conn.execute("""
            SELECT d.id, d.file_path, d.file_hash, d.indexed_at, COUNT(c.id) as chunk_count
            FROM documents d
            LEFT JOIN chunks c ON d.id = c.document_id
            GROUP BY d.id
            ORDER BY d.indexed_at DESC
        """)
        return cursor.fetchall()

    def _format_results(self, results):
        """Format query results"""
        return [self._format_row(row) for row in results]

    def _format_row(self, row) -> dict:
        """Format single row"""
        return {
            "id": row[0],
            "file_path": row[1],
            "file_name": row[1].split('/')[-1],
            "file_hash": row[2],
            "indexed_at": row[3],
            "chunk_count": row[4]
        }

    def _build_response(self, pattern, documents):
        """Build search response"""
        return {
            "pattern": pattern,
            "total_matches": len(documents),
            "documents": documents
        }

@app.delete("/document/{file_path:path}")
async def delete_document(file_path: str):
    """Delete a document and all its chunks from the vector store

    This removes:
    - Document record from documents table
    - All chunks from chunks table
    - Processing progress from processing_progress table

    Args:
        file_path: Full path to the document (e.g., /app/knowledge_base/file.pdf)

    Returns:
        Deletion statistics including chunks deleted
    """
    try:
        # Delete from vector store (documents + chunks)
        result = state.core.vector_store.delete_document(file_path)

        if not result['found']:
            raise HTTPException(
                status_code=404,
                detail=f"Document not found: {file_path}"
            )

        # Delete from processing progress
        if state.core.progress_tracker:
            progress_deleted = state.core.progress_tracker.delete_document(file_path)
        else:
            progress_deleted = False

        return {
            "success": True,
            "file_path": file_path,
            "chunks_deleted": result['chunks_deleted'],
            "processing_progress_deleted": progress_deleted,
            "message": f"Successfully deleted document with {result['chunks_deleted']} chunks"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete document: {str(e)}"
        )

@app.post("/indexing/pause")
async def pause_indexing():
    """Pause background indexing

    Pauses the indexing worker. Files already being processed will complete,
    but no new files will be processed until resume is called.
    """
    try:
        if not state.indexing.queue:
            raise HTTPException(status_code=400, detail="Indexing queue not initialized")

        state.indexing.queue.pause()
        return {
            "status": "success",
            "message": "Indexing paused",
            "queue_size": state.indexing.queue.size()
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to pause indexing: {str(e)}")

@app.post("/indexing/resume")
async def resume_indexing():
    """Resume background indexing

    Resumes the indexing worker to process files from the queue.
    """
    try:
        if not state.indexing.queue:
            raise HTTPException(status_code=400, detail="Indexing queue not initialized")

        state.indexing.queue.resume()
        return {
            "status": "success",
            "message": "Indexing resumed",
            "queue_size": state.indexing.queue.size()
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to resume indexing: {str(e)}")

@app.post("/indexing/priority/{file_path:path}")
async def add_priority_file(file_path: str, force: bool = False):
    """Add a file to the front of the indexing queue with high priority

    Args:
        file_path: Relative path from knowledge_base (e.g., "original/test.epub")
        force: Force reindexing even if already indexed

    Use this to prioritize testing or critical files over the background queue.
    """
    try:
        if not state.indexing.queue:
            raise HTTPException(status_code=400, detail="Indexing queue not initialized")

        from services import Priority
        from pathlib import Path

        # Construct full path
        kb_path = default_config.paths.knowledge_base
        full_path = kb_path / file_path

        if not full_path.exists():
            raise HTTPException(status_code=404, detail=f"File not found: {file_path}")

        # Add with high priority
        state.indexing.queue.add(full_path, priority=Priority.HIGH, force=force)

        return {
            "status": "success",
            "message": f"Added {file_path} to queue with HIGH priority",
            "queue_size": state.indexing.queue.size(),
            "force": force
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to add priority file: {str(e)}")

@app.get("/indexing/status")
async def get_indexing_status():
    """Get current indexing queue status

    Returns information about the indexing queue and worker state.
    """
    try:
        if not state.indexing.queue or not state.indexing.worker:
            raise HTTPException(status_code=400, detail="Indexing queue not initialized")

        return {
            "queue_size": state.indexing.queue.size(),
            "paused": state.indexing.queue.is_paused(),
            "worker_running": state.indexing.worker.is_running(),
            "indexing_in_progress": state.runtime.indexing_in_progress
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get status: {str(e)}")

@app.get("/queue/jobs")
async def get_queue_jobs():
    """Get detailed queue and active jobs information

    Shows concurrent pipeline statistics:
    - Input queue size and state
    - Internal pipeline queue sizes (chunk, embed, store)
    - Active jobs in each pipeline stage
    - Worker running status for each stage
    """
    try:
        if not state.indexing.queue or not state.indexing.worker:
            raise HTTPException(status_code=400, detail="Indexing queue not initialized")

        if not state.indexing.pipeline_coordinator:
            raise HTTPException(status_code=400, detail="Concurrent pipeline not initialized")

        # Get pipeline statistics
        pipeline_stats = state.indexing.pipeline_coordinator.get_stats()

        return {
            "input_queue_size": state.indexing.queue.size(),
            "paused": state.indexing.queue.is_paused(),
            "worker_running": state.indexing.worker.is_running(),
            "queue_sizes": pipeline_stats["queue_sizes"],
            "active_jobs": pipeline_stats["active_jobs"],
            "workers_running": pipeline_stats["workers_running"]
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get queue jobs: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
