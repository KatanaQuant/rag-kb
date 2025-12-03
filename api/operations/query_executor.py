from typing import List, Optional
from models import QueryRequest, QueryResponse, SearchResult


class QueryExecutor:
    """Executes semantic search queries with optional reranking"""

    def __init__(self, model, vector_store, cache=None, reranker=None):
        self.model = model
        self.store = vector_store
        self.cache = cache
        self.reranker = reranker

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
        """Search vector store with optional reranking.

        If reranker is enabled, fetches more candidates (top_n) and reranks
        to final top_k. This improves retrieval quality by ~20-30%.
        """
        # Determine how many candidates to fetch
        fetch_k = request.top_k
        if self.reranker and self.reranker.is_enabled:
            # Fetch more candidates for reranking (default: 20)
            fetch_k = max(request.top_k, getattr(self.reranker, 'top_n', 20))

        # Search vector store
        results = await self.store.search(
            query_embedding=embedding.tolist(),
            top_k=fetch_k,
            threshold=request.threshold,
            query_text=request.text,
            use_hybrid=True
        )

        # Rerank if enabled
        if self.reranker and self.reranker.is_enabled and results:
            results = self.reranker.rerank(request.text, results, request.top_k)

        return results

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

