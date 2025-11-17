from pydantic import BaseModel, Field
from typing import List, Optional


class QueryRequest(BaseModel):
    text: str = Field(..., description="The query text to search for")
    top_k: int = Field(default=5, ge=1, le=50, description="Number of results to return")
    threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Minimum similarity score")


class SearchResult(BaseModel):
    content: str
    source: str
    page: Optional[int] = None
    score: float
    metadata: Optional[dict] = None


class QueryResponse(BaseModel):
    results: List[SearchResult]
    query: str
    total_results: int


class HealthResponse(BaseModel):
    status: str
    indexed_documents: int
    total_chunks: int
    model: str
    indexing_in_progress: bool


class IndexRequest(BaseModel):
    force_reindex: bool = Field(default=False, description="Force reindexing of all documents")


class IndexResponse(BaseModel):
    status: str
    indexed_files: int
    total_chunks: int
    message: str


class DocumentInfoResponse(BaseModel):
    file_path: str
    extraction_method: str
    indexed_at: Optional[str] = None
