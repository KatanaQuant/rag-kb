import asyncio
import re
from typing import List, Optional, Tuple
from models import QueryRequest, QueryResponse, SearchResult, DecompositionInfo


class QueryExecutor:
    """Executes semantic search queries with optional reranking and query expansion"""

    def __init__(self, model, vector_store, cache=None, reranker=None, query_expander=None):
        self.model = model
        self.store = vector_store
        self.cache = cache
        self.reranker = reranker
        self.query_expander = query_expander

    async def execute(self, request: QueryRequest) -> QueryResponse:
        """Execute search query (async for non-blocking database access)

        v2 Decomposition: If a compound query is detected (e.g., "X and Y"),
        searches each sub-query separately and merges results for better recall.

        v3 Query Expansion: If Ollama is available and enabled, expands the query
        into multiple variants using LLM, then searches all variants and merges.
        """
        self._validate(request.text)

        # Check for query decomposition
        decomposition = self._analyze_decomposition(request.text, request.decompose)

        if self.cache:
            cached = self.cache.get(
                request.text, request.top_k, request.threshold, request.decompose
            )
            if cached:
                return self._format(cached, request.text, decomposition)

        # v3: Expand query using LLM if enabled
        if self.query_expander and self.query_expander.is_enabled:
            expanded_queries = await asyncio.to_thread(
                self.query_expander.expand, request.text
            )
            if len(expanded_queries) > 1:
                # Search all expanded queries and merge results
                results = await self._search_expanded(expanded_queries, request)
            else:
                embedding = await asyncio.to_thread(self._gen_embedding, request.text)
                results = await self._search(embedding, request)
        # v2: Execute sub-queries if compound query detected
        elif decomposition.applied and len(decomposition.sub_queries) >= 2:
            results = await self._search_decomposed(decomposition.sub_queries, request)
        else:
            embedding = await asyncio.to_thread(self._gen_embedding, request.text)
            results = await self._search(embedding, request)

        if self.cache:
            self.cache.put(
                request.text, request.top_k, request.threshold, results, request.decompose
            )

        return self._format(results, request.text, decomposition)

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
            # Fetch more candidates for reranking (ensures enough for larger top_k)
            fetch_k = max(request.top_k * 2, 40)

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

    async def _search_multi_query(self, queries: List[str], request) -> List:
        """Search multiple queries and merge deduplicated results.

        Common logic for both v2 decomposition and v3 query expansion.
        Searches each query, deduplicates by (source, content_prefix),
        sorts by score, and optionally reranks against original query.
        """
        all_results = []
        seen_chunks = set()

        fetch_k = request.top_k
        if self.reranker and self.reranker.is_enabled:
            fetch_k = max(request.top_k * 2, 40)

        for query in queries:
            embedding = await asyncio.to_thread(self._gen_embedding, query)
            results = await self.store.search(
                query_embedding=embedding.tolist(),
                top_k=fetch_k,
                threshold=request.threshold,
                query_text=query,
                use_hybrid=True
            )
            for r in results:
                chunk_key = (r['source'], r['content'][:100])
                if chunk_key not in seen_chunks:
                    seen_chunks.add(chunk_key)
                    all_results.append(r)

        all_results.sort(key=lambda x: x['score'], reverse=True)

        if self.reranker and self.reranker.is_enabled and all_results:
            all_results = self.reranker.rerank(
                request.text, all_results[:fetch_k], request.top_k
            )
        else:
            all_results = all_results[:request.top_k]

        return all_results

    async def _search_decomposed(self, sub_queries: List[str], request) -> List:
        """Search each sub-query separately and merge results (v2 decomposition)."""
        return await self._search_multi_query(sub_queries, request)

    async def _search_expanded(self, expanded_queries: List[str], request) -> List:
        """Search each expanded query and merge results (v3 query expansion)."""
        return await self._search_multi_query(expanded_queries, request)

    @staticmethod
    def _format(results: List, query: str, decomposition: DecompositionInfo = None) -> QueryResponse:
        """Format response"""
        search_results = QueryExecutor._to_models(results)
        suggestions = QueryExecutor._generate_suggestions(results, query)
        return QueryResponse(
            results=search_results,
            query=query,
            total_results=len(search_results),
            suggestions=suggestions,
            decomposition=decomposition or DecompositionInfo()
        )

    @staticmethod
    def _analyze_decomposition(query: str, decompose: bool) -> DecompositionInfo:
        """Analyze query for potential decomposition.

        Detects compound queries using conjunctions and question patterns.
        Returns decomposition info without actually splitting execution (v1).
        """
        if not decompose:
            return DecompositionInfo(applied=False, sub_queries=[])

        # Patterns that indicate compound queries
        compound_patterns = [
            r'\band\b',          # "X and Y"
            r'\bor\b',           # "X or Y"
            r'\bvs\.?\b',        # "X vs Y"
            r'\bversus\b',       # "X versus Y"
            r'\bcompare\b',      # "compare X with Y"
            r'\?.*\?',           # Multiple question marks
        ]

        query_lower = query.lower()
        is_compound = any(re.search(p, query_lower) for p in compound_patterns)

        if not is_compound:
            return DecompositionInfo(applied=False, sub_queries=[])

        # Split on common conjunctions
        sub_queries = QueryExecutor._split_compound_query(query)

        if len(sub_queries) < 2:
            return DecompositionInfo(applied=False, sub_queries=[])

        return DecompositionInfo(applied=True, sub_queries=sub_queries)

    @staticmethod
    def _split_compound_query(query: str) -> List[str]:
        """Split compound query into sub-queries."""
        # Try splitting patterns in order of specificity
        split_patterns = [
            r'\s+vs\.?\s+',      # "X vs Y" or "X vs. Y"
            r'\s+versus\s+',     # "X versus Y"
            r'\s+and\s+',        # "X and Y"
            r'\s+or\s+',         # "X or Y"
        ]

        parts = [query]
        for pattern in split_patterns:
            if len(parts) == 1:
                parts = re.split(pattern, query, flags=re.IGNORECASE)

        # Clean up parts
        sub_queries = []
        for part in parts:
            cleaned = part.strip()
            if cleaned and len(cleaned) > 3:  # Skip very short fragments
                sub_queries.append(cleaned)

        return sub_queries

    @staticmethod
    def _generate_suggestions(results: List, query: str) -> List[str]:
        """Generate follow-up query suggestions from result content.

        Simple approach: extract frequent terms not in original query.
        """
        if not results:
            return []

        # Combine content from top results
        combined = " ".join(r.get("content", "") for r in results[:3])

        # Simple term extraction (words 4+ chars, not in query)
        query_terms = set(query.lower().split())
        words = combined.lower().split()

        # Count term frequency
        term_counts = {}
        for word in words:
            # Clean word, skip short/common words
            clean = "".join(c for c in word if c.isalnum())
            if len(clean) >= 4 and clean not in query_terms:
                term_counts[clean] = term_counts.get(clean, 0) + 1

        # Get top terms by frequency
        top_terms = sorted(term_counts.items(), key=lambda x: -x[1])[:5]

        # Generate suggestions
        suggestions = []
        for term, _ in top_terms[:3]:
            suggestions.append(f"more about {term}")

        return suggestions

    @staticmethod
    def _to_models(results: List) -> List[SearchResult]:
        """Convert to models"""
        return [
            SearchResult(
                content=r['content'],
                source=r['source'],
                page=r['page'],
                score=r['score'],
                rerank_score=r.get('rerank_score')
            )
            for r in results
        ]

