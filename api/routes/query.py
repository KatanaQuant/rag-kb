"""Query route module."""
from fastapi import APIRouter, Request, HTTPException
from models import QueryRequest, QueryResponse
from operations.query_executor import QueryExecutor
from routes.deps import get_app_state

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
        app_state = get_app_state(request)
        executor = QueryExecutor(
            app_state.get_model(),
            app_state.get_async_vector_store(),
            app_state.get_query_cache(),
            app_state.get_reranker(),
            app_state.get_query_expander()
        )
        return await executor.execute(request_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
