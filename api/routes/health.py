"""
Health and info routes

Extracted from main.py following POODR principles:
- Single responsibility: health/info endpoints only
- Dependency injection: app state injected via FastAPI dependency
"""
from fastapi import APIRouter, Request
from models import HealthResponse
from config import default_config

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
    app_state = request.app.state.app_state
    stats = await app_state.get_vector_store_stats()  # Now async, non-blocking!

    return HealthResponse(
        status="healthy",
        indexed_documents=stats['indexed_documents'],
        total_chunks=stats['total_chunks'],
        model=default_config.model.name,
        indexing_in_progress=app_state.runtime.indexing_in_progress
    )
