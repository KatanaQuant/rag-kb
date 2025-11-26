"""Maintenance API routes

Endpoints for database maintenance, repair, and cleanup operations.
Replaces manage.py CLI commands with REST API.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from pathlib import Path
import sqlite3

from config import default_config

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
    documents_reindexed: int
    documents_failed: int
    dry_run: bool
    results: List[ReindexResult]
    message: str


# ============================================================================
# Fix Tracking Endpoint
# ============================================================================

@router.post("/fix-tracking", response_model=FixTrackingResponse)
async def fix_tracking(request: FixTrackingRequest = None):
    """Backfill chunk counts for historical documents

    Some documents may have been indexed before chunk tracking was added.
    This endpoint updates the expected_chunk_count and actual_chunk_count
    fields for documents that are missing this data.

    Args:
        dry_run: If true, show what would be updated without making changes

    Example:
        POST /api/maintenance/fix-tracking
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

@router.post("/delete-orphans", response_model=DeleteOrphansResponse)
async def delete_orphans(request: DeleteOrphansRequest = None):
    """Delete orphan document records (metadata with no chunks)

    Orphan records can occur when:
    - Processing was interrupted before chunks were stored
    - Chunks were manually deleted
    - Database inconsistency

    Args:
        dry_run: If true, show orphans without deleting

    Example:
        POST /api/maintenance/delete-orphans
        {"dry_run": true}

    Returns:
        List of orphan documents and deletion status
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

@router.post("/reindex-incomplete", response_model=ReindexResponse)
async def reindex_incomplete(request: ReindexRequest = None):
    """Re-index all incomplete documents

    Finds documents that are incomplete (zero chunks, missing embeddings,
    processing incomplete) and triggers re-indexing for each.

    Args:
        dry_run: If true, show what would be reindexed without doing it
        issue_types: Filter by specific issue types:
            - zero_chunks: Documents with no chunks
            - processing_incomplete: Processing didn't finish
            - missing_embeddings: Chunks without embeddings

    Example:
        POST /api/maintenance/reindex-incomplete
        {"dry_run": true, "issue_types": ["zero_chunks"]}

    Returns:
        List of documents and their reindex status
    """
    if request is None:
        request = ReindexRequest()

    try:
        import requests

        # Get incomplete documents from completeness endpoint
        resp = requests.get('http://localhost:8000/documents/completeness', timeout=300)
        data = resp.json()

        # Filter by issue types if specified
        allowed_issues = request.issue_types or ['zero_chunks', 'processing_incomplete', 'missing_embeddings']
        incomplete = [
            i for i in data.get('issues', [])
            if i['issue'] in allowed_issues
        ]

        if not incomplete:
            return ReindexResponse(
                documents_found=0,
                documents_reindexed=0,
                documents_failed=0,
                dry_run=request.dry_run,
                results=[],
                message="No incomplete documents found"
            )

        results = []
        success_count = 0
        failed_count = 0

        if request.dry_run:
            # Just show what would be reindexed
            results = [
                ReindexResult(
                    file_path=item['file_path'],
                    filename=Path(item['file_path']).name,
                    success=True,
                    error=None
                )
                for item in incomplete[:100]  # Limit response
            ]
        else:
            # Actually reindex each document
            for item in incomplete:
                path = item['file_path']
                try:
                    resp = requests.post(
                        'http://localhost:8000/documents/reindex',
                        params={'path': path, 'force': 'true'},
                        timeout=300
                    )
                    if resp.status_code == 200:
                        results.append(ReindexResult(
                            file_path=path,
                            filename=Path(path).name,
                            success=True
                        ))
                        success_count += 1
                    else:
                        results.append(ReindexResult(
                            file_path=path,
                            filename=Path(path).name,
                            success=False,
                            error=f"HTTP {resp.status_code}"
                        ))
                        failed_count += 1
                except Exception as e:
                    results.append(ReindexResult(
                        file_path=path,
                        filename=Path(path).name,
                        success=False,
                        error=str(e)
                    ))
                    failed_count += 1

        return ReindexResponse(
            documents_found=len(incomplete),
            documents_reindexed=success_count if not request.dry_run else 0,
            documents_failed=failed_count,
            dry_run=request.dry_run,
            results=results[:100],  # Limit response size
            message=f"{'Would reindex' if request.dry_run else 'Reindexed'} {len(incomplete)} documents"
        )

    except requests.exceptions.ConnectionError:
        raise HTTPException(
            status_code=503,
            detail="Cannot connect to completeness endpoint. Is the server fully started?"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reindex failed: {e}")
