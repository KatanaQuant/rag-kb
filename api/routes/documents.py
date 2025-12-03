"""Document routes module."""
from pathlib import Path

from fastapi import APIRouter, Request, HTTPException

from config import default_config
from models import DocumentInfoResponse
from operations.document_lister import DocumentLister
from operations.document_searcher import DocumentSearcher
from pipeline import Priority
from routes.deps import get_app_state

router = APIRouter()


@router.get("/document/{filename}", response_model=DocumentInfoResponse)
async def get_document_info(filename: str, request: Request):
    """Get document information including extraction method"""
    try:
        app_state = get_app_state(request)
        info = await app_state.get_async_vector_store().get_document_info(filename)
        if not info:
            raise HTTPException(status_code=404, detail=f"Document not found: {filename}")
        return DocumentInfoResponse(**info)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to retrieve document info")


@router.get("/documents")
async def list_documents(request: Request):
    """List all documents"""
    try:
        app_state = get_app_state(request)
        lister = DocumentLister(app_state.get_async_vector_store())
        return await lister.list_all()
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="Failed to list documents"
        )


@router.get("/documents/search")
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


@router.delete("/document/{file_path:path}")
async def delete_document(file_path: str, request: Request):
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
        app_state = get_app_state(request)
        # Delete from vector store (documents + chunks)
        result = await app_state.get_async_vector_store().delete_document(file_path)

        # Delete from processing progress
        progress_tracker = app_state.get_progress_tracker()
        if progress_tracker:
            try:
                progress_tracker.delete_document(file_path)
            except Exception as e:
                print(f"Warning: Failed to delete progress record: {e}")

        return {
            "status": "success",
            "file_path": file_path,
            **result
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete document: {str(e)}"
        )


@router.post("/document/{file_path:path}/reindex")
async def reindex_document(file_path: str, request: Request):
    """Re-index a document: delete from DB and queue for re-processing

    This is a convenience endpoint that combines:
    1. DELETE /document/{path} - removes from index
    2. POST /indexing/priority/{path}?force=true - queues for re-indexing

    Use cases:
    - E2E testing: validate full pipeline (security scan → chunk → embed → store)
    - Force re-processing after pipeline changes
    - Re-index after manual file edits

    Args:
        file_path: Full path to the document (e.g., /app/knowledge_base/file.pdf)

    Returns:
        Status including deletion stats and queue position
    """
    try:
        app_state = get_app_state(request)

        # Verify file exists on disk
        path = Path(file_path)
        if not path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"File not found on disk: {file_path}"
            )

        # Step 1: Delete from DB (if indexed)
        deletion_result = {"deleted": False, "chunks_deleted": 0}
        try:
            result = await app_state.get_async_vector_store().delete_document(file_path)
            deletion_result = {"deleted": True, **result}

            # Also delete progress record
            progress_tracker = app_state.get_progress_tracker()
            if progress_tracker:
                try:
                    progress_tracker.delete_document(file_path)
                except Exception:
                    pass  # Progress record may not exist
        except Exception:
            pass  # Document may not be indexed yet

        # Step 2: Queue for re-indexing with HIGH priority
        if not app_state.get_indexing_queue():
            raise HTTPException(
                status_code=400,
                detail="Indexing queue not initialized"
            )

        app_state.add_to_queue(path, priority=Priority.HIGH, force=True)

        return {
            "status": "success",
            "file_path": file_path,
            "action": "reindex",
            "deletion": deletion_result,
            "queued": True,
            "priority": "HIGH",
            "queue_size": app_state.queue_size()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reindex document: {str(e)}"
        )
