"""
Query route module

Extracted from main.py following POODR principles:
- Single responsibility: query operations only
- Dependency injection via FastAPI Request
"""
from fastapi import APIRouter, Request, HTTPException
from models import QueryRequest, QueryResponse
from api_services.query_executor import QueryExecutor

router = APIRouter()


@router.post("/query", response_model=QueryResponse)
async def query(request_data: QueryRequest, request: Request):
    """
    Query the knowledge base using semantic search

    Args:
        request_data: Query parameters
        request: FastAPI request for accessing app state

    Returns:
        QueryResponse with search results
    """
    try:
        app_state = request.app.state.app_state
        executor = QueryExecutor(
            app_state.core.model,
            app_state.core.async_vector_store,  # Use async store for non-blocking queries
            app_state.query.cache
        )
        return await executor.execute(request_data)  # Now async, non-blocking!
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
