"""Health and info routes."""
from fastapi import APIRouter, Request
from models import HealthResponse
from config import default_config
from routes.deps import get_app_state

router = APIRouter()


@router.get("/", include_in_schema=False)
async def root():
    """Root endpoint with API information"""
    return {
        "message": "RAG Knowledge Base API",
        "docs": "/docs",
        "health": "/health"
    }


@router.get("/health", response_model=HealthResponse)
async def health(request: Request):
    """
    Health check endpoint

    Returns system statistics and operational status
    """
    app_state = get_app_state(request)
    stats = await app_state.get_vector_store_stats()

    return HealthResponse(
        status="healthy",
        indexed_documents=stats['indexed_documents'],
        total_chunks=stats['total_chunks'],
        model=default_config.model.name,
        indexing_in_progress=app_state.is_indexing_in_progress()
    )
