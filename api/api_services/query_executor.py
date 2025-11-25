from typing import List
from models import QueryRequest, QueryResponse, SearchResult


class QueryExecutor:
    """Executes semantic search queries"""

    def __init__(self, model, vector_store, cache=None):
        self.model = model
        self.store = vector_store
        self.cache = cache

    async def execute(self, request: QueryRequest) -> QueryResponse:
        """Execute search query (async for non-blocking database access)"""
        self._validate(request.text)

        if self.cache:
            cached = self.cache.get(request.text, request.top_k, request.threshold)
            if cached:
                return self._format(cached, request.text)

        embedding = self._gen_embedding(request.text)
        results = await self._search(embedding, request)  # Now async!

        if self.cache:
            self.cache.put(request.text, request.top_k, request.threshold, results)

        return self._format(results, request.text)

    @staticmethod
    def _validate(text: str):
        """Validate query text"""
        if not text.strip():
            raise ValueError("Query cannot be empty")

    def _gen_embedding(self, text: str):
        """Generate query embedding"""
        return self.model.encode(text, show_progress_bar=False)

    async def _search(self, embedding, request):
        """Search vector store (async for non-blocking database access)"""
        return await self.store.search(
            query_embedding=embedding.tolist(),
            top_k=request.top_k,
            threshold=request.threshold,
            query_text=request.text,
            use_hybrid=True
        )

    @staticmethod
    def _format(results: List, query: str) -> QueryResponse:
        """Format response"""
        search_results = QueryExecutor._to_models(results)
        return QueryResponse(
            results=search_results,
            query=query,
            total_results=len(search_results)
        )

    @staticmethod
    def _to_models(results: List) -> List[SearchResult]:
        """Convert to models"""
        return [
            SearchResult(
                content=r['content'],
                source=r['source'],
                page=r['page'],
                score=r['score']
            )
            for r in results
        ]

