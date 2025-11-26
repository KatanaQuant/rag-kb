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

    Args:
        dry_run: If true, show empty documents without deleting

    Example:
        POST /api/maintenance/delete-empty-documents
        {"dry_run": true}

    Returns:
        List of empty documents and deletion status
    """
    if request is None:
        request = DeleteOrphansRequest()

    try:
        db_path = default_config.database.path
        conn = sqlite3.connect(db_path)

        # Find orphans (documents with no chunks)
        cursor = conn.execute('''
            SELECT d.id, d.file_path
            FROM documents d
            WHERE NOT EXISTS (SELECT 1 FROM chunks c WHERE c.document_id = d.id)
        ''')
        orphans = cursor.fetchall()

        orphan_list = [
            OrphanDocument(
                id=doc_id,
                file_path=fp,
                filename=Path(fp).name
            )
            for doc_id, fp in orphans
        ]

        deleted_count = 0
        if not request.dry_run and orphans:
            # Delete orphan documents and their progress records
            for doc_id, file_path in orphans:
                conn.execute('DELETE FROM documents WHERE id = ?', (doc_id,))
                conn.execute('DELETE FROM processing_progress WHERE file_path = ?', (file_path,))
                deleted_count += 1
            conn.commit()

        conn.close()

        return DeleteOrphansResponse(
            orphans_found=len(orphans),
            orphans_deleted=deleted_count,
            dry_run=request.dry_run,
            orphans=orphan_list[:50],  # Limit response size
            message=f"{'Would delete' if request.dry_run else 'Deleted'} {len(orphans)} orphan documents"
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Delete orphans failed: {e}")


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
        app_state = http_request.app.state.app_state

        # Get integrity report directly (no HTTP call needed)
        from operations.completeness_reporter import CompletenessReporter
        reporter = CompletenessReporter(
            progress_tracker=app_state.core.progress_tracker,
            vector_store=app_state.core.async_vector_store
        )
        report = reporter.generate_report()

        # Filter by issue types if specified
        allowed_issues = request.issue_types or ['zero_chunks', 'processing_incomplete', 'missing_embeddings']
        incomplete = [
            i for i in report.get('issues', [])
            if i['issue'] in allowed_issues
        ]

        if not incomplete:
            return ReindexResponse(
                documents_found=0,
                documents_queued=0,
                dry_run=request.dry_run,
                documents=[],
                message="No incomplete documents found"
            )

        # Build result list
        documents = [
            ReindexResult(
                file_path=item['file_path'],
                filename=Path(item['file_path']).name,
                success=True,
                error=None
            )
            for item in incomplete[:100]  # Limit response size
        ]

        queued_count = 0
        if not request.dry_run:
            # Queue all documents with HIGH priority
            queue = app_state.indexing.queue
            if queue:
                for item in incomplete:
                    path = Path(item['file_path'])
                    if path.exists():
                        queue.add(path, priority=Priority.HIGH, force=True)
                        queued_count += 1
            else:
                raise HTTPException(
                    status_code=400,
                    detail="Indexing queue not available"
                )

        return ReindexResponse(
            documents_found=len(incomplete),
            documents_queued=queued_count if not request.dry_run else 0,
            dry_run=request.dry_run,
            documents=documents,
            message=f"{'Would queue' if request.dry_run else 'Queued'} {len(incomplete)} documents for reindexing with HIGH priority"
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reindex failed: {e}")
