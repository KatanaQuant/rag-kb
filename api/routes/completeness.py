"""
Document completeness/integrity routes

Provides API endpoints for checking document integrity.

Following Sandi Metz patterns:
- Single Responsibility: route handlers only
- Dependency Injection: receive services via Request
"""
from fastapi import APIRouter, Request, HTTPException

from operations.completeness_reporter import CompletenessReporter


router = APIRouter()


@router.get("/documents/integrity")
async def get_integrity_report(request: Request):
    """Check document integrity across the knowledge base

    Analyzes all indexed documents for integrity issues:
    - Zero chunks: Documents that produced no content
    - Processing incomplete: Documents that didn't finish processing
    - Missing embeddings: Documents missing vector embeddings
    - Chunk count mismatch: Expected vs actual chunk counts differ

    Returns:
        total_documents: Total indexed documents
        complete: Documents passing all integrity checks
        incomplete: Documents with issues
        issues: List of specific issues found
    """
    try:
        app_state = request.app.state.app_state
        reporter = CompletenessReporter(
            progress_tracker=app_state.core.progress_tracker,
            vector_store=app_state.core.async_vector_store
        )
        return reporter.generate_report()
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate completeness report: {str(e)}"
        )


@router.get("/documents/integrity/{file_path:path}")
async def get_document_integrity(file_path: str, request: Request):
    """Check integrity of a specific document

    Args:
        file_path: Full path to document

    Returns:
        Integrity status and any issues found
    """
    try:
        app_state = request.app.state.app_state
        reporter = CompletenessReporter(
            progress_tracker=app_state.core.progress_tracker,
            vector_store=app_state.core.async_vector_store
        )
        result = reporter.analyze_single(file_path)

        if not result:
            raise HTTPException(
                status_code=404,
                detail=f"Document not found: {file_path}"
            )

        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to analyze document: {str(e)}"
        )
