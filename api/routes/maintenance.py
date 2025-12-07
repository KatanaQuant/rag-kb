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


class IntegrityCheckDetail(BaseModel):
    """Detail of a single integrity check"""
    name: str
    passed: bool
    details: str


class VerifyIntegrityResponse(BaseModel):
    """Response from verify-integrity operation"""
    healthy: bool
    issues: List[str]
    checks: List[IntegrityCheckDetail]
    table_counts: dict


class CleanupOrphansRequest(BaseModel):
    """Request for cleanup-orphans operation"""
    dry_run: bool = False


class CleanupOrphansResponse(BaseModel):
    """Response from cleanup-orphans operation"""
    dry_run: bool
    orphan_chunks_found: int
    orphan_chunks_deleted: int
    orphan_vec_chunks_estimate: int
    orphan_fts_chunks_estimate: int
    message: str


class RebuildHnswRequest(BaseModel):
    """Request for rebuild-hnsw operation"""
    dry_run: bool = False


class RebuildHnswResponse(BaseModel):
    """Response from rebuild-hnsw operation

    CRITICAL: This is the response from HNSW index recovery.
    Used to recover from index corruption after HNSW write errors.
    """
    embeddings_before: int
    embeddings_after: int
    valid_embeddings: int
    orphans_found: int
    orphans_removed: int
    dry_run: bool
    elapsed_time: float
    message: str
    error: Optional[str] = None


class RebuildFtsRequest(BaseModel):
    """Request for rebuild-fts operation"""
    dry_run: bool = False


class RebuildFtsResponse(BaseModel):
    """Response from rebuild-fts operation

    FTS5 index rebuild statistics.
    """
    chunks_found: int
    chunks_indexed: int
    fts_entries_before: int
    fts_entries_after: int
    dry_run: bool
    time_taken: float
    message: str
    errors: Optional[List[str]] = None


class ReindexPathRequest(BaseModel):
    """Request for reindex-path operation"""
    path: str
    dry_run: bool = False


class ReindexPathResult(BaseModel):
    """Result for a single file in reindex-path operation"""
    file_path: str
    filename: str
    deleted_from_db: bool
    queued: bool
    chunks_deleted: int = 0
    error: Optional[str] = None


class ReindexPathResponse(BaseModel):
    """Response from reindex-path operation"""
    path: str
    is_directory: bool
    files_found: int
    files_deleted: int
    files_queued: int
    total_chunks_deleted: int
    dry_run: bool
    results: List[ReindexPathResult]
    message: str


class RepairIndexesRequest(BaseModel):
    """Request for repair-indexes operation"""
    dry_run: bool = False


class HnswStats(BaseModel):
    """HNSW rebuild statistics"""
    embeddings_before: int
    embeddings_after: int
    valid_embeddings: int
    orphans_found: int
    orphans_removed: int
    elapsed_time: float
    error: Optional[str] = None


class FtsStats(BaseModel):
    """FTS rebuild statistics"""
    chunks_found: int
    chunks_indexed: int
    fts_entries_before: int
    fts_entries_after: int
    time_taken: float
    errors: Optional[List[str]] = None


class RepairIndexesResponse(BaseModel):
    """Response from repair-indexes operation

    Combined HNSW and FTS rebuild statistics.
    """
    dry_run: bool
    total_time: float
    hnsw: HnswStats
    fts: FtsStats
    message: str
    error: Optional[str] = None


class RebuildEmbeddingsRequest(BaseModel):
    """Request for rebuild-embeddings operation"""
    dry_run: bool = False


class RebuildEmbeddingsResponse(BaseModel):
    """Response from rebuild-embeddings operation

    Full embedding rebuild statistics. This is a LONG-RUNNING operation.
    """
    dry_run: bool
    documents_found: int
    chunks_found: int
    chunks_embedded: int
    embeddings_before: int
    embeddings_after: int
    time_taken: float
    message: str
    errors: Optional[List[str]] = None
    model_name: Optional[str] = None
    embedding_dim: Optional[int] = None


class PartialRebuildRequest(BaseModel):
    """Request for partial-rebuild operation"""
    dry_run: bool = False
    start_id: Optional[int] = None
    end_id: Optional[int] = None


class PartialRebuildResponse(BaseModel):
    """Response from partial-rebuild operation

    Partial embedding rebuild statistics for specific ID range.
    """
    dry_run: bool
    start_id: Optional[int]
    end_id: Optional[int]
    chunks_in_range: int
    chunks_embedded: int
    time_taken: float
    message: str
    errors: Optional[List[str]] = None
    model_name: Optional[str] = None


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


# ============================================================================
# Verify Integrity Endpoint
# ============================================================================

@router.get("/verify-integrity", response_model=VerifyIntegrityResponse)
async def verify_integrity():
    """Verify database integrity and consistency

    Runs comprehensive integrity checks on the database:
    - Referential integrity (chunks -> documents)
    - HNSW index consistency (vec_chunks <-> chunks)
    - FTS index consistency (fts_chunks <-> chunks)
    - Duplicate document detection

    Example:
        GET /api/maintenance/verify-integrity

    Returns:
        healthy: True if all checks pass
        issues: List of issue descriptions (empty if healthy)
        checks: Detailed results for each check
        table_counts: Row counts for relevant tables
    """
    try:
        from operations.integrity_checker import IntegrityChecker

        checker = IntegrityChecker(db_path=default_config.database.path)
        result = checker.check()

        return VerifyIntegrityResponse(
            healthy=result.healthy,
            issues=result.issues,
            checks=[
                IntegrityCheckDetail(
                    name=c['name'],
                    passed=c['passed'],
                    details=c['details']
                ) for c in result.checks
            ],
            table_counts=result.table_counts
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Integrity check failed: {e}")


# ============================================================================
# Cleanup Orphans Endpoint
# ============================================================================

@router.post("/cleanup-orphans", response_model=CleanupOrphansResponse)
async def cleanup_orphans(request: CleanupOrphansRequest = None):
    """Cleanup orphan data from the database

    Removes orphan chunks (chunks referencing non-existent documents) and their
    associated FTS entries. Also reports estimated orphan vec_chunks and fts_chunks.

    This is the full cleanup operation that handles:
    - Orphan chunks (invalid document_id)
    - Orphan vec_chunks entries (estimated, requires HNSW rebuild for full cleanup)
    - Orphan fts_chunks entries (deleted for orphan chunks)

    Note: Unlike delete-empty-documents which removes empty document records,
    this endpoint removes orphan chunks that reference missing documents.

    Args:
        dry_run: If true, show what would be deleted without making changes

    Example:
        POST /api/maintenance/cleanup-orphans
        {"dry_run": true}

    Returns:
        Counts of orphans found and deleted for each type
    """
    if request is None:
        request = CleanupOrphansRequest()

    try:
        from operations.orphan_cleaner import OrphanCleaner

        cleaner = OrphanCleaner(db_path=default_config.database.path)
        result = cleaner.clean(dry_run=request.dry_run)

        return CleanupOrphansResponse(
            dry_run=result.dry_run,
            orphan_chunks_found=result.orphan_chunks_found,
            orphan_chunks_deleted=result.orphan_chunks_deleted,
            orphan_vec_chunks_estimate=result.orphan_vec_chunks_estimate,
            orphan_fts_chunks_estimate=result.orphan_fts_chunks_estimate,
            message=result.message
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Orphan cleanup failed: {e}")


# ============================================================================
# Rebuild HNSW Index Endpoint
# ============================================================================

@router.post("/rebuild-hnsw", response_model=RebuildHnswResponse)
async def rebuild_hnsw(request: RebuildHnswRequest = None):
    """CRITICAL: Rebuild HNSW index from existing embeddings

    This is the RECOVERY MECHANISM for HNSW index corruption. Use this endpoint
    when you encounter HNSW write errors or index inconsistencies.

    What this does:
    1. Enumerates all embeddings in vec_chunks via knn_search
    2. Identifies valid embeddings (rowid exists in chunks table)
    3. Identifies orphan embeddings (rowid does NOT exist in chunks)
    4. If not dry_run: recreates vec_chunks with only valid embeddings

    What this does NOT do:
    - Re-run the embedding model (much faster than re-embedding)
    - Re-extract or re-chunk documents
    - Touch the chunks or documents tables

    IMPORTANT: This operation is safe to run - it only removes orphan embeddings
    that have no corresponding chunk. Valid embeddings are preserved exactly.

    Args:
        dry_run: If true, show what would be done without modifying the index

    Example:
        # First, preview what would be done:
        POST /api/maintenance/rebuild-hnsw
        {"dry_run": true}

        # Then execute the rebuild:
        POST /api/maintenance/rebuild-hnsw
        {"dry_run": false}

    Returns:
        embeddings_before: Total embeddings in vec_chunks before rebuild
        embeddings_after: Total embeddings after rebuild (same as valid_embeddings)
        valid_embeddings: Embeddings with matching chunk IDs (preserved)
        orphans_found: Embeddings without matching chunk IDs (removed)
        orphans_removed: Number of orphan embeddings actually removed
        elapsed_time: Time taken for the operation in seconds

    Use cases:
        - Recovery from HNSW write errors during indexing
        - Cleanup after interrupted delete operations
        - Fixing vec_chunks/chunks count mismatches
    """
    if request is None:
        request = RebuildHnswRequest()

    try:
        from operations.hnsw_rebuilder import HnswRebuilder

        rebuilder = HnswRebuilder(db_path=default_config.database.path)
        result = rebuilder.rebuild(dry_run=request.dry_run)

        # Build message based on result
        if result.error:
            message = f"Error: {result.error}"
        elif result.orphan_embeddings == 0:
            message = "HNSW index is clean - no orphan embeddings found"
        elif request.dry_run:
            message = f"Would remove {result.orphan_embeddings} orphan embeddings"
        else:
            message = f"Removed {result.orphan_embeddings} orphan embeddings"

        # Calculate orphans_removed (0 if dry_run or error)
        orphans_removed = 0
        if not request.dry_run and not result.error and result.orphan_embeddings > 0:
            orphans_removed = result.total_embeddings - result.final_embeddings

        return RebuildHnswResponse(
            embeddings_before=result.total_embeddings,
            embeddings_after=result.final_embeddings,
            valid_embeddings=result.valid_embeddings,
            orphans_found=result.orphan_embeddings,
            orphans_removed=orphans_removed,
            dry_run=result.dry_run,
            elapsed_time=result.elapsed_time,
            message=message,
            error=result.error
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"HNSW rebuild failed: {e}")


# ============================================================================
# Rebuild FTS Index Endpoint
# ============================================================================

@router.post("/rebuild-fts", response_model=RebuildFtsResponse)
async def rebuild_fts(request: RebuildFtsRequest = None):
    """Rebuild FTS5 full-text search index from existing chunks

    Rebuilds the fts_chunks FTS5 virtual table from the chunks table.
    Use this when fts_chunks is out of sync with chunks table or has orphan entries.

    What this does:
    1. Counts existing chunks and FTS entries
    2. Drops and recreates the fts_chunks table
    3. Populates fts_chunks from chunks table in batches
    4. Forces WAL checkpoint for durability

    Critical: Sets rowid = chunk_id for JOIN compatibility with hybrid_search.

    Args:
        dry_run: If true, show what would be done without modifying the index

    Example:
        # First, preview what would be done:
        POST /api/maintenance/rebuild-fts
        {"dry_run": true}

        # Then execute the rebuild:
        POST /api/maintenance/rebuild-fts
        {"dry_run": false}

    Returns:
        chunks_found: Total chunks in chunks table
        chunks_indexed: Number of chunks added to FTS index
        fts_entries_before: FTS entries before rebuild
        fts_entries_after: FTS entries after rebuild
        time_taken: Time taken for the operation in seconds

    Use cases:
        - Recovery from FTS index corruption
        - Cleanup after interrupted indexing operations
        - Fixing fts_chunks/chunks count mismatches
    """
    if request is None:
        request = RebuildFtsRequest()

    try:
        from operations.fts_rebuilder import FtsRebuilder

        rebuilder = FtsRebuilder(db_path=default_config.database.path)
        result = rebuilder.rebuild(dry_run=request.dry_run)

        return RebuildFtsResponse(
            chunks_found=result.chunks_found,
            chunks_indexed=result.chunks_indexed,
            fts_entries_before=result.fts_entries_before,
            fts_entries_after=result.fts_entries_after,
            dry_run=result.dry_run,
            time_taken=result.time_taken,
            message=result.message,
            errors=result.errors
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"FTS rebuild failed: {e}")


# ============================================================================
# Repair Indexes Endpoint (Combined HNSW + FTS)
# ============================================================================

@router.post("/repair-indexes", response_model=RepairIndexesResponse)
async def repair_indexes(request: RepairIndexesRequest = None):
    """Repair both HNSW and FTS indexes in one operation

    Convenience endpoint that runs both rebuild-hnsw and rebuild-fts
    in sequence. Use this for complete index maintenance.

    What this does:
    1. Rebuilds HNSW index (removes orphan embeddings)
    2. Rebuilds FTS5 index (recreates from chunks table)

    This is equivalent to calling rebuild-hnsw followed by rebuild-fts,
    but in a single request with combined statistics.

    Args:
        dry_run: If true, show what would be done without modifying indexes

    Example:
        # First, preview what would be done:
        POST /api/maintenance/repair-indexes
        {"dry_run": true}

        # Then execute the repair:
        POST /api/maintenance/repair-indexes
        {"dry_run": false}

    Returns:
        dry_run: Whether this was a preview operation
        total_time: Total time for both operations
        hnsw: HNSW rebuild statistics
        fts: FTS rebuild statistics
        message: Summary of what was done

    Use cases:
        - Complete index recovery after database issues
        - Scheduled maintenance to ensure index consistency
        - Recovery after interrupted indexing operations
    """
    if request is None:
        request = RepairIndexesRequest()

    try:
        from operations.index_repairer import IndexRepairer

        repairer = IndexRepairer(db_path=default_config.database.path)
        result = repairer.repair(dry_run=request.dry_run)

        # Calculate orphans_removed for HNSW
        hnsw = result.hnsw_result
        orphans_removed = 0
        if not request.dry_run and not hnsw.error and hnsw.orphan_embeddings > 0:
            orphans_removed = hnsw.total_embeddings - hnsw.final_embeddings

        return RepairIndexesResponse(
            dry_run=result.dry_run,
            total_time=result.total_time,
            hnsw=HnswStats(
                embeddings_before=hnsw.total_embeddings,
                embeddings_after=hnsw.final_embeddings,
                valid_embeddings=hnsw.valid_embeddings,
                orphans_found=hnsw.orphan_embeddings,
                orphans_removed=orphans_removed,
                elapsed_time=hnsw.elapsed_time,
                error=hnsw.error
            ),
            fts=FtsStats(
                chunks_found=result.fts_result.chunks_found,
                chunks_indexed=result.fts_result.chunks_indexed,
                fts_entries_before=result.fts_result.fts_entries_before,
                fts_entries_after=result.fts_result.fts_entries_after,
                time_taken=result.fts_result.time_taken,
                errors=result.fts_result.errors
            ),
            message=result.message,
            error=result.error
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Index repair failed: {e}")


# ============================================================================
# Reindex Path Endpoint
# ============================================================================

@router.post("/reindex-path", response_model=ReindexPathResponse)
async def reindex_path(http_request: Request, request: ReindexPathRequest):
    """Re-index a specific file or directory

    Deletes existing document(s) from the database and queues them for
    re-indexing through the full pipeline. For directories, recursively
    finds and reindexes all supported files.

    What this does:
    1. For files: Delete from documents + chunks tables, delete progress record
    2. For directories: Same as above for all supported files recursively
    3. Queue file(s) for re-indexing with HIGH priority

    Args:
        path: Absolute path to file or directory to reindex
        dry_run: If true, show what would be done without making changes

    Example:
        # Reindex a single file:
        POST /api/maintenance/reindex-path
        {"path": "/app/kb/documents/report.pdf", "dry_run": false}

        # Reindex a directory:
        POST /api/maintenance/reindex-path
        {"path": "/app/kb/documents/", "dry_run": true}

    Returns:
        path: The path that was requested
        is_directory: Whether the path was a directory
        files_found: Number of supported files found
        files_deleted: Number of files deleted from database
        files_queued: Number of files queued for reindexing
        total_chunks_deleted: Total chunks deleted across all files
        results: Per-file results (up to 100)

    Use cases:
        - Re-process a file after pipeline changes
        - Force re-indexing after manual file edits
        - Re-index a directory after bulk updates
        - E2E testing of specific files
    """
    try:
        from operations.path_reindexer import PathReindexer

        app_state = get_app_state(http_request)

        # Get supported extensions from processor if available
        processor = app_state.get_processor()
        supported_extensions = None
        if processor and hasattr(processor, 'SUPPORTED_EXTENSIONS'):
            supported_extensions = processor.SUPPORTED_EXTENSIONS

        reindexer = PathReindexer(
            vector_store=app_state.get_vector_store(),
            progress_tracker=app_state.get_progress_tracker(),
            indexing_queue=app_state.get_indexing_queue(),
            supported_extensions=supported_extensions
        )

        summary = reindexer.reindex(
            path=request.path,
            dry_run=request.dry_run
        )

        return ReindexPathResponse(
            path=summary.path,
            is_directory=summary.is_directory,
            files_found=summary.files_found,
            files_deleted=summary.files_deleted,
            files_queued=summary.files_queued,
            total_chunks_deleted=summary.total_chunks_deleted,
            dry_run=summary.dry_run,
            results=[
                ReindexPathResult(
                    file_path=r.file_path,
                    filename=r.filename,
                    deleted_from_db=r.deleted_from_db,
                    queued=r.queued,
                    chunks_deleted=r.chunks_deleted,
                    error=r.error
                ) for r in summary.results
            ],
            message=summary.message
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reindex path failed: {e}")


# ============================================================================
# Rebuild Embeddings Endpoint (Full Re-embed)
# ============================================================================

@router.post("/rebuild-embeddings", response_model=RebuildEmbeddingsResponse)
async def rebuild_embeddings(request: RebuildEmbeddingsRequest = None):
    """Full re-embed of all documents (LONG-RUNNING operation)

    Regenerates all vector embeddings from chunk content using the
    configured embedding model. Use this for complete index rebuild
    when embeddings are missing or corrupted.

    What this does:
    1. Loads the embedding model (Arctic or configured model)
    2. Drops and recreates vec_chunks table
    3. Iterates through all chunks in batches
    4. Generates new embeddings for each chunk
    5. Inserts all new embeddings into vec_chunks

    This is MUCH faster than force-reindex because it skips:
    - PDF extraction
    - Chunking
    - Security scanning

    WARNING: This is a long-running operation that may take several minutes
    for large databases. Consider running during low-traffic periods.

    Args:
        dry_run: If true, show what would be done without modifying data

    Example:
        # First, preview what would be done:
        POST /api/maintenance/rebuild-embeddings
        {"dry_run": true}

        # Then execute the rebuild:
        POST /api/maintenance/rebuild-embeddings
        {"dry_run": false}

    Returns:
        documents_found: Total documents in database
        chunks_found: Total chunks to embed
        chunks_embedded: Number of chunks successfully embedded
        embeddings_before: Embeddings before rebuild
        embeddings_after: Embeddings after rebuild
        time_taken: Time taken in seconds
        model_name: Embedding model used
        embedding_dim: Embedding dimension

    Use cases:
        - Complete HNSW index recovery when embeddings are corrupted
        - Re-embedding after model change
        - Recovery from vec_chunks table corruption
    """
    if request is None:
        request = RebuildEmbeddingsRequest()

    try:
        from operations.embedding_rebuilder import EmbeddingRebuilder

        rebuilder = EmbeddingRebuilder(db_path=default_config.database.path)
        result = rebuilder.rebuild(dry_run=request.dry_run)

        return RebuildEmbeddingsResponse(
            dry_run=result.dry_run,
            documents_found=result.documents_found,
            chunks_found=result.chunks_found,
            chunks_embedded=result.chunks_embedded,
            embeddings_before=result.embeddings_before,
            embeddings_after=result.embeddings_after,
            time_taken=result.time_taken,
            message=result.message,
            errors=result.errors if result.errors else None,
            model_name=result.model_name,
            embedding_dim=result.embedding_dim
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Embedding rebuild failed: {e}")


# ============================================================================
# Partial Rebuild Endpoint (Re-embed by ID Range)
# ============================================================================

@router.post("/partial-rebuild", response_model=PartialRebuildResponse)
async def partial_rebuild(request: PartialRebuildRequest = None):
    """Re-embed only chunks in a specific ID range

    Re-embeds chunks within a specified ID range. Unlike full rebuild,
    this ADDS to the existing vec_chunks table without dropping it.
    Use when specific chunks are missing from the HNSW index.

    What this does:
    1. Loads the embedding model
    2. Finds all chunks in the specified ID range
    3. Generates embeddings for those chunks
    4. Inserts embeddings into vec_chunks (existing table)

    This is faster than full rebuild because it only embeds missing chunks.

    Args:
        dry_run: If true, show what would be done without modifying data
        start_id: Start of chunk ID range (inclusive, optional)
        end_id: End of chunk ID range (inclusive, optional)

    Example:
        # Re-embed chunks 70778-71727 (from investigation):
        POST /api/maintenance/partial-rebuild
        {"dry_run": false, "start_id": 70778, "end_id": 71727}

        # Preview all chunks that would be embedded:
        POST /api/maintenance/partial-rebuild
        {"dry_run": true}

    Returns:
        start_id: Start of range processed
        end_id: End of range processed
        chunks_in_range: Total chunks found in range
        chunks_embedded: Number of chunks successfully embedded
        time_taken: Time taken in seconds
        model_name: Embedding model used

    Use cases:
        - Recovery after partial HNSW corruption
        - Re-embedding specific chunk ranges
        - Fixing gaps in HNSW index
    """
    if request is None:
        request = PartialRebuildRequest()

    try:
        from operations.partial_rebuilder import PartialRebuilder

        rebuilder = PartialRebuilder(db_path=default_config.database.path)
        result = rebuilder.rebuild(
            start_id=request.start_id,
            end_id=request.end_id,
            dry_run=request.dry_run
        )

        return PartialRebuildResponse(
            dry_run=result.dry_run,
            start_id=result.start_id,
            end_id=result.end_id,
            chunks_in_range=result.chunks_in_range,
            chunks_embedded=result.chunks_embedded,
            time_taken=result.time_taken,
            message=result.message,
            errors=result.errors if result.errors else None,
            model_name=result.model_name
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Partial rebuild failed: {e}")
