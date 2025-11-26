"""
Document routes module

Extracted from main.py following POODR principles:
- Single responsibility: document operations only
- Dependency injection via FastAPI Request
"""
from fastapi import APIRouter, Request, HTTPException

from models import DocumentInfoResponse
from operations.document_lister import DocumentLister
from operations.document_searcher import DocumentSearcher
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
