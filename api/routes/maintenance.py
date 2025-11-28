"""Maintenance API routes

Endpoints for database maintenance, repair, and cleanup operations.
All maintenance operations are exposed via REST API for automation.
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import List, Optional
from pathlib import Path
import sqlite3

from config import default_config
from pipeline.indexing_queue import Priority
from routes.deps import get_app_state

router = APIRouter(prefix="/api/maintenance", tags=["maintenance"])


# ============================================================================
# Request/Response Models
# ============================================================================

class FixTrackingRequest(BaseModel):
    """Request for fix-tracking operation"""
    dry_run: bool = False


class FixTrackingResponse(BaseModel):
    """Response from fix-tracking operation"""
    documents_checked: int
    documents_updated: int
    dry_run: bool
    message: str


class DeleteOrphansRequest(BaseModel):
    """Request for delete-orphans operation"""
    dry_run: bool = False


class OrphanDocument(BaseModel):
    """An orphan document record"""
    id: int
    file_path: str
    filename: str


class DeleteOrphansResponse(BaseModel):
    """Response from delete-orphans operation"""
    orphans_found: int
    orphans_deleted: int
    dry_run: bool
    orphans: List[OrphanDocument]
    message: str


class ReindexRequest(BaseModel):
    """Request for reindex-incomplete operation"""
    dry_run: bool = False
    issue_types: Optional[List[str]] = None  # Filter by issue type


class ReindexResult(BaseModel):
    """Result for a single reindex operation"""
    file_path: str
    filename: str
    success: bool
    error: Optional[str] = None


class ReindexResponse(BaseModel):
    """Response from reindex-incomplete operation"""
    documents_found: int
    documents_queued: int
    dry_run: bool
    documents: List[ReindexResult]
    message: str


# ============================================================================
# Fix Tracking Endpoint
# ============================================================================

@router.post("/backfill-chunk-counts", response_model=FixTrackingResponse)
async def backfill_chunk_counts(request: FixTrackingRequest = None):
    """Backfill missing chunk counts for historical documents

    Some documents indexed before chunk tracking was added may be missing
    expected_chunk_count and actual_chunk_count fields. This endpoint
    calculates and fills in the missing counts.

    Args:
        dry_run: If true, show what would be updated without making changes

    Example:
        POST /api/maintenance/backfill-chunk-counts
        {"dry_run": true}

    Returns:
        Number of documents checked and updated
    """
    if request is None:
        request = FixTrackingRequest()

    try:
        from migrations.backfill_chunk_counts import backfill_chunk_counts
        result = backfill_chunk_counts(dry_run=request.dry_run)

        return FixTrackingResponse(
            documents_checked=result.get('checked', 0),
            documents_updated=result.get('updated', 0) if not request.dry_run else result.get('would_update', 0),
            dry_run=request.dry_run,
            message=f"{'Would update' if request.dry_run else 'Updated'} {result.get('would_update', result.get('updated', 0))} documents"
        )

    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="Migration module not found. Ensure migrations/backfill_chunk_counts.py exists."
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fix tracking failed: {e}")


# ============================================================================
# Delete Orphans Endpoint
# ============================================================================

@router.post("/delete-empty-documents", response_model=DeleteOrphansResponse)
async def delete_empty_documents(request: DeleteOrphansRequest = None):
    """Delete document records that have no chunks (empty documents)

    Empty document records can occur when:
    - Processing was interrupted before chunks were stored
    - Chunks were manually deleted
    - Database inconsistency
    """
    if request is None:
        request = DeleteOrphansRequest()

    try:
        orphans, deleted_count = _process_empty_documents(request.dry_run)
        return _build_orphan_response(orphans, deleted_count, request.dry_run)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Delete orphans failed: {e}")


def _process_empty_documents(dry_run: bool) -> tuple:
    """Find and optionally delete empty documents"""
    conn = sqlite3.connect(default_config.database.path)
    orphans = _find_orphan_documents(conn)
    deleted_count = 0 if dry_run else _delete_orphans(conn, orphans)
    conn.close()
    return orphans, deleted_count


def _find_orphan_documents(conn) -> list:
    """Find documents with no chunks"""
    cursor = conn.execute('''
        SELECT d.id, d.file_path
        FROM documents d
        WHERE NOT EXISTS (SELECT 1 FROM chunks c WHERE c.document_id = d.id)
    ''')
    return cursor.fetchall()


def _delete_orphans(conn, orphans: list) -> int:
    """Delete orphan documents and their progress records"""
    for doc_id, file_path in orphans:
        conn.execute('DELETE FROM documents WHERE id = ?', (doc_id,))
        conn.execute('DELETE FROM processing_progress WHERE file_path = ?', (file_path,))
    conn.commit()
    return len(orphans)


def _build_orphan_response(orphans: list, deleted_count: int, dry_run: bool) -> DeleteOrphansResponse:
    """Build response with orphan list"""
    orphan_list = [
        OrphanDocument(id=doc_id, file_path=fp, filename=Path(fp).name)
        for doc_id, fp in orphans
    ]
    action = 'Would delete' if dry_run else 'Deleted'
    return DeleteOrphansResponse(
        orphans_found=len(orphans),
        orphans_deleted=deleted_count,
        dry_run=dry_run,
        orphans=orphan_list[:50],
        message=f"{action} {len(orphans)} orphan documents"
    )


# ============================================================================
# Reindex Incomplete Endpoint
# ============================================================================

@router.post("/reindex-failed-documents", response_model=ReindexResponse)
async def reindex_failed_documents(http_request: Request, request: ReindexRequest = None):
    """Queue all documents that failed or are incomplete for re-indexing

    Finds documents with integrity issues (zero chunks, missing embeddings,
    processing incomplete) and queues them for re-indexing with HIGH priority.
    Returns immediately - check /indexing/status for progress.

    Args:
        dry_run: If true, show what would be queued without queueing
        issue_types: Filter by specific issue types:
            - zero_chunks: Documents with no chunks
            - processing_incomplete: Processing didn't finish
            - missing_embeddings: Chunks without embeddings

    Example:
        POST /api/maintenance/reindex-failed-documents
        {"dry_run": true, "issue_types": ["zero_chunks"]}

    Returns:
        Number of documents found and queued
    """
    if request is None:
        request = ReindexRequest()

    try:
        from operations.failed_document_reindexer import FailedDocumentReindexer

        app_state = get_app_state(http_request)
        reindexer = FailedDocumentReindexer(
            progress_tracker=app_state.get_progress_tracker(),
            vector_store=app_state.get_async_vector_store(),
            indexing_queue=app_state.get_indexing_queue()
        )

        summary = reindexer.reindex(
            issue_types=request.issue_types,
            dry_run=request.dry_run
        )

        return ReindexResponse(
            documents_found=summary.documents_found,
            documents_queued=summary.documents_queued,
            dry_run=summary.dry_run,
            documents=[
                ReindexResult(
                    file_path=r.file_path,
                    filename=r.filename,
                    success=r.success,
                    error=r.error
                ) for r in summary.results
            ],
            message=summary.message
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reindex failed: {e}")
