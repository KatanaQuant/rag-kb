"""
Database routes module

Extracted from main.py following POODR principles:
- Single responsibility: database operations only
- Dependency injection via FastAPI Request
"""
from fastapi import APIRouter, Request, HTTPException

from api_services.orphan_detector import OrphanDetector

router = APIRouter()


@router.post("/repair-orphans")
async def repair_orphans(request: Request):
    """Repair orphaned files (processed but not embedded)

    Orphaned files occur when processing completes but embedding fails.
    This endpoint detects and repairs them by reindexing.
    """
    try:
        app_state = request.app.state.app_state
        if not app_state.core.progress_tracker:
            raise HTTPException(
                status_code=400,
                detail="Progress tracking not enabled"
            )

        detector = OrphanDetector(app_state.core.progress_tracker, app_state.core.vector_store)
        orphans = detector.detect_orphans()

        if not orphans:
            return {
                "status": "success",
                "orphans_found": 0,
                "orphans_repaired": 0,
                "message": "No orphaned files found"
            }

        # Repair orphans by adding to queue with HIGH priority
        queued = detector.repair_orphans(app_state.indexing.queue)

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


@router.get("/database/check-duplicates")
async def check_database_duplicates(request: Request):
    """Check for duplicate chunks in the database

    Returns statistics about duplicate chunks within documents and across documents.
    Within-document duplicates are usually problematic and should be cleaned up.
    Cross-document duplicates may be intentional (shared content).
    """
    try:
        app_state = request.app.state.app_state
        conn = app_state.core.vector_store.conn
        cursor = conn.cursor()

        # Get total stats
        cursor.execute("SELECT COUNT(*) FROM chunks")
        total_chunks = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM documents")
        total_docs = cursor.fetchone()[0]

        # Check for duplicate chunks within same document
        cursor.execute("""
            SELECT document_id, content, COUNT(*) as cnt
            FROM chunks
            GROUP BY document_id, content
            HAVING cnt > 1
        """)
        doc_duplicates = cursor.fetchall()

        # Check for duplicate content across documents (limited to top 10)
        cursor.execute("""
            SELECT content, COUNT(*) as cnt, COUNT(DISTINCT document_id) as doc_count
            FROM chunks
            GROUP BY content
            HAVING doc_count > 1
            ORDER BY cnt DESC
            LIMIT 10
        """)
        cross_doc_duplicates = cursor.fetchall()

        # Calculate total duplicate chunks
        duplicate_chunks_count = sum(cnt - 1 for _, _, cnt in doc_duplicates)

        return {
            "status": "success",
            "total_documents": total_docs,
            "total_chunks": total_chunks,
            "within_document_duplicates": {
                "count": len(doc_duplicates),
                "total_duplicate_chunks": duplicate_chunks_count,
                "impact": "These are usually problematic and should be cleaned"
            },
            "cross_document_duplicates": {
                "count": len(cross_doc_duplicates),
                "top_10": [
                    {
                        "content_preview": content[:100],
                        "occurrences": cnt,
                        "documents": doc_count
                    }
                    for content, cnt, doc_count in cross_doc_duplicates
                ],
                "impact": "May be intentional (shared content like headers, footers)"
            },
            "recommendation": "Run /database/cleanup-duplicates to remove within-document duplicates" if duplicate_chunks_count > 0 else "Database is clean"
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to check duplicates: {str(e)}"
        )


@router.post("/database/cleanup-duplicates")
async def cleanup_database_duplicates(request: Request):
    """Clean up duplicate chunks within documents

    Removes duplicate chunks that appear multiple times within the same document.
    Keeps the first occurrence and deletes the rest.
    Cross-document duplicates are NOT removed (may be intentional).

    Returns the number of duplicate chunks removed.
    """
    try:
        app_state = request.app.state.app_state
        conn = app_state.core.vector_store.conn
        cursor = conn.cursor()

        # Find duplicate chunks within same document
        cursor.execute("""
            SELECT document_id, content, MIN(id) as keep_id, COUNT(*) as cnt
            FROM chunks
            GROUP BY document_id, content
            HAVING cnt > 1
        """)
        doc_duplicates = cursor.fetchall()

        if not doc_duplicates:
            return {
                "status": "success",
                "duplicates_found": 0,
                "chunks_deleted": 0,
                "message": "No duplicate chunks found within documents"
            }

        deleted_count = 0

        for doc_id, content, keep_id, count in doc_duplicates:
            # Delete all chunks with same document_id + content EXCEPT the one with keep_id
            cursor.execute("""
                DELETE FROM chunks
                WHERE document_id = ? AND content = ? AND id != ?
            """, (doc_id, content, keep_id))

            deleted = count - 1
            deleted_count += deleted

        # Clean up orphaned vector and FTS entries
        cursor.execute("""
            DELETE FROM vec_chunks
            WHERE chunk_id NOT IN (SELECT id FROM chunks)
        """)

        cursor.execute("""
            DELETE FROM fts_chunks
            WHERE chunk_id NOT IN (SELECT id FROM chunks)
        """)

        conn.commit()

        # Get updated stats
        cursor.execute("SELECT COUNT(*) FROM chunks")
        final_chunks = cursor.fetchone()[0]

        return {
            "status": "success",
            "duplicates_found": len(doc_duplicates),
            "chunks_deleted": deleted_count,
            "final_chunk_count": final_chunks,
            "message": f"Successfully removed {deleted_count} duplicate chunks from {len(doc_duplicates)} documents"
        }

    except Exception as e:
        conn.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to cleanup duplicates: {str(e)}"
        )
