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
from api_services.model_loader import ModelLoader
from api_services.file_walker import FileWalker
from api_services.document_indexer import DocumentIndexer
from api_services.index_orchestrator import IndexOrchestrator
from api_services.query_executor import QueryExecutor
from api_services.orphan_detector import OrphanDetector
from api_services.document_lister import DocumentLister
from api_services.document_searcher import DocumentSearcher
from startup.manager import StartupManager

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

    File scanning happens in background to prevent API blocking.
    """
    try:
        if not state.indexing.queue:
            raise HTTPException(status_code=400, detail="Indexing queue not initialized")

        # Move file scanning to background to prevent blocking
        def scan_and_queue():
            """Background task: Scan files and add to queue"""
            from services import Priority

            kb_path = default_config.paths.knowledge_base
            walker = FileWalker(kb_path, state.core.processor.SUPPORTED_EXTENSIONS)
            all_files = list(walker.walk())

            priority = Priority.HIGH if request.force_reindex else Priority.NORMAL
            state.indexing.queue.add_many(all_files, priority=priority, force=request.force_reindex)

            print(f"✓ Background scan complete: Queued {len(all_files)} files (force={request.force_reindex})")

        background_tasks.add_task(scan_and_queue)

        return IndexResponse(
            status="success",
            indexed_files=0,
            total_chunks=0,
            message=f"File scan started in background (force={request.force_reindex}). Check /queue/jobs for progress."
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start indexing: {str(e)}")

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

