# Query Accuracy Investigation: From 73.1% to 92.3%

**Investigation Period:** December 5-6, 2025
**Status:** CLOSED - Target exceeded
**Final Result:** 92.3% usable accuracy (vs 84.6% v1.9.1 baseline)
**Related:** [Postmortem: Vectorlite HNSW Migration](postmortem-vectorlite-hnsw-complete.md)

---

## Executive Summary

| Metric | v1.9.1 (baseline) | v2.2.2 (before) | v2.2.4-beta (final) |
|--------|-------------------|-----------------|---------------------|
| Usable | 84.6% (22/26) | 73.1% (19/26) | **92.3%** (24/26) |
| Correct | 65.4% (17/26) | 53.8% (14/26) | **73.1%** (19/26) |
| Acceptable | 19.2% (5/26) | 19.2% (5/26) | 19.2% (5/26) |
| Wrong | 15.4% (4/26) | 26.9% (7/26) | **7.7%** (2/26) |
| Latency | 60,932ms | ~500ms | **553ms** |

**Resolution:** Two key fixes:
1. **Title boosting** in BM25 improved accuracy from 73.1% to 80.8%
2. **ef=150** HNSW search quality improved accuracy from 80.8% to **92.3%**

**Key insight:** The root cause was vectorlite's default ef=10 (only ~31% recall). Setting ef=150 achieves ~95% recall, and combined with title boosting, we now EXCEED the v1.9.1 baseline while maintaining 120x faster queries.

---

## Problem Statement

> **Did we always have 73% accuracy, or did vectorlite migration break something?**

**ANSWER: Vectorlite migration made specific books INVISIBLE to search**

The "11% average regression" masked the real problem: certain content was **completely unretrievable**.

---

## Root Cause Analysis

### Technical Explanation

1. **HNSW is approximate search** - vectorlite uses Hierarchical Navigable Small World graphs which trade accuracy for speed
2. **sqlite-vec uses exact search** - brute force cosine similarity across all vectors
3. **The tradeoff**: v2.2.2 was 600x faster but less accurate

### The Real Problem

| What the average said | What actually happened |
|-----------------------|------------------------|
| 11.5% less accurate | **Specific books are invisible** |
| 73% still usable | **"24 Assets" and "MAKE" can't be found** |
| Speed improved 600x | **Speed doesn't matter if you can't find content** |

### Why Specific Books Disappeared

1. **HNSW returns WRONG vectors** - not lower scores, completely different results
2. **Failure mode**: Query for "24 Assets" returns "Smart Portfolios" instead
3. **Failure mode**: Query for "MAKE exit strategy" returns "Naming Things" instead
4. **sqlite-vec exact search** found these correctly every time

---

## Investigation Phases

### Phase 1: Three-Way Search Test

**Goal**: Prove whether HNSW, BM25, or fusion is the bottleneck.

| Method | Accuracy | Conclusion |
|--------|----------|------------|
| Vector only (HNSW) | 43% (3/7) | HNSW is bottleneck |
| BM25 only (keyword) | 100% (7/7) | BM25 can rescue |
| Hybrid (RRF fusion) | 100% (7/7) | Hybrid should fix |

**Diagnosis**: HNSW returns wrong vectors for specific queries. BM25 finds correct content.

### Phase 2: Enable Hybrid Search

Wired up HybridSearcher to async queries using RRF (Reciprocal Rank Fusion).

**Results**:
| Category | Before | After | Change |
|----------|--------|-------|--------|
| programming_books | 85.7% | 100% | +14.3% |
| business_books | 100% | 75% | -25% |
| Net usable | 73.1% | 73.1% | Same |

**Key finding**: Improvements in programming_books offset by regressions in business_books.

### Phase 3: RRF Fusion Tuning

| k value | Usable Rate | Conclusion |
|---------|-------------|------------|
| k=20 | 73.1% | Same |
| k=60 | 73.1% | Same |

**Conclusion**: k-parameter doesn't affect failing queries.

### Phase 4: rank_bm25 Integration

Replaced FTS5 boolean MATCH with probabilistic BM25Okapi scoring.

**Before (FTS5)**:
```sql
-- Boolean AND - returns NOTHING if any term missing
WHERE fts_chunks MATCH 'term1 term2 term3'
```

**After (rank_bm25)**:
```python
# Probabilistic - scores ALL documents, partial matches get scores
from rank_bm25 import BM25Okapi
scores = self._bm25.get_scores(query_tokens)
```

**Result**: BM25 now returns results for partial matches, but overall accuracy unchanged at 73.1%.

### Phase 5: Options Testing

Tested ALL remaining options systematically:

| Option | What We Did | Result | Accuracy |
|--------|-------------|--------|----------|
| B: BM25 k1/b tuning | Tested k1=1.5/b=0.5, k1=2.5/b=0.9 | NO CHANGE | 73.1% |
| D: Query preprocessing | Added stop word removal | NO CHANGE (removed) | 73.1% |
| **C: Title boosting** | Boost BM25 when filename matches query | **IMPROVED** | **80.8%** |
| E: Cross-encoder reranking | BGEReranker on limited candidates | NO ADDITIONAL | 80.8% |
| G: LLM query expansion | Ollama qwen2.5:0.5b, 2-3 variants | NO ADDITIONAL (+10x latency) | 80.8% |

### Phase 6: HNSW ef Parameter Discovery (THE KEY FIX)

After title boosting plateaued at 80.8%, we discovered the HNSW ef parameter issue.

vectorlite's knn_search defaults to `ef=10` when not specified:

```sql
-- Our code (default ef=10):
WHERE knn_search(v.embedding, knn_param(?, ?))

-- What we needed (ef=150):
WHERE knn_search(v.embedding, knn_param(?, ?, 150))
```

According to vectorlite benchmarks:
| ef | Recall Rate | Query Time |
|----|-------------|------------|
| 10 | **31.6%** | 35us |
| 50 | 72.3% | 99us |
| 100 | 88.6% | 168us |
| **150** | **95.5%** | 310us |

**We were operating at 31.6% recall!** This explains why HNSW was returning completely wrong vectors.

---

## Title Boosting Implementation

The winning approach for the BM25 component:

```python
def _get_title_boost(self, file_path: str, query_tokens: List[str]) -> float:
    """Calculate title boost multiplier based on query-title overlap."""
    filename = Path(file_path).stem.lower()
    filename_tokens = set(self._tokenize(filename))
    query_token_set = set(query_tokens)
    overlap = len(filename_tokens & query_token_set)
    if overlap >= 3: return 3.0
    elif overlap >= 2: return 2.0
    elif overlap >= 1: return 1.5
    return 1.0
```

**Why it worked**: Book queries like "24 Assets" and "MAKE" now get boosted when the filename matches, overcoming the "trading blog dominance" problem.

---

## Final Configuration

### What's Enabled
| Feature | Setting | Purpose |
|---------|---------|---------|
| HNSW ef_search | 150 | ~95% recall (was 10 = 31%) |
| Hybrid search | RRF k=20 | Combine vector + keyword |
| rank_bm25 | BM25Okapi | Probabilistic keyword scoring |
| Title boosting | 1.5x-3x | Boost when filename matches query |

### What's Disabled
| Feature | Reason |
|---------|--------|
| RERANKING_ENABLED | No improvement over title boosting |
| QUERY_EXPANSION_ENABLED | +10x latency without accuracy gain |

---

## Remaining Failures (2/26)

Both are code file queries - a known limitation:

| Query | Expected | Got | Root Cause |
|-------|----------|-----|------------|
| "Python trading system random price" | randompriceexample.py | Blog post | Code file findability |
| "Jupyter notebook trading rule" | asimpletradingrule.ipynb | Blog post | Notebook search |

Would need better code/notebook chunking or contextual embeddings.

---

## Category Performance

| Category | v1.9.1 | v2.2.4-beta |
|----------|--------|-------------|
| business_books | 100% | 100% |
| programming_books | 85.7% | 100% |
| trading_content | 60% | 100% |
| code_files | 66.7% | 33.3% |
| known_problematic | 100% | 100% |

---

## Lessons Learned

### 1. RTFM - Default Parameters Matter
vectorlite's ef=10 default is documented but buried:
> "ef defaults to 10" - vectorlite overview

We should have tested recall explicitly during migration.

### 2. Test the Full Lifecycle
Our migration testing validated:
- [x] Migration script works
- [x] Queries return results
- [ ] Restart and re-query (would have caught persistence bugs)
- [ ] Accuracy benchmarks (would have caught ef=10 issue)

### 3. Approximate Search Needs Calibration
HNSW trades accuracy for speed. The trade-off must be explicitly tuned:
- ef=10: 31% recall, 35us (unusable)
- ef=150: 95% recall, 310us (production-ready)
- exact: 100% recall, milliseconds (too slow for large corpus)

### 4. Establish Baseline Before Migration
We should have run the benchmark suite BEFORE and AFTER migration:
- v1.9.1: 84.6% usable, 60,932ms
- v2.2.0-beta: Would have shown immediate regression

---

## Our Stack vs LangChain/LlamaIndex

| Component | Our Implementation | LangChain | LlamaIndex | Verdict |
|-----------|-------------------|-----------|------------|---------|
| **Vector Store** | vectorlite (HNSW) | FAISS/Chroma (HNSW) | FAISS/Qdrant (HNSW) | Same |
| **Keyword Search** | rank_bm25 (BM25Okapi) | BM25Retriever | BM25 | Same |
| **Fusion** | RRF (k=20) | EnsembleRetriever (RRF) | QueryFusionRetriever | Same |
| **Query Transform** | None | MultiQueryRetriever | HyDEQueryTransform | Gap (future) |
| **Reranking** | BGEReranker (disabled) | FlashrankRerank | SentenceTransformerRerank | Have it |

**Key Finding**: Persistence layer is FINE. The difference is in query processing, not storage.

---

## Future Improvements

### Short-term (v2.2.x)
- Monitor title boosting effectiveness
- Tune RRF k if needed

### Medium-term (v2.3.0)
- **Contextual embeddings** - Anthropic claims +35%, but requires re-indexing
- Better code/notebook chunking

---

## References

- [Anthropic Contextual Retrieval](https://www.anthropic.com/news/contextual-retrieval) - Future improvement reference
- [vectorlite benchmarks](https://dev.to/yefuwang/introducing-vectorlite-a-fast-and-tunable-vector-search-extension-for-sqlite-4dcl)
- [hnswlib ALGO_PARAMS.md](https://github.com/nmslib/hnswlib/blob/master/ALGO_PARAMS.md)

---

## Related Files

| File | Purpose |
|------|---------|
| `api/hybrid_search.py` | BM25Searcher (with title boosting), RankFusion, HybridSearcher |
| `api/ingestion/async_repositories.py` | ef=150 HNSW search |
| `api/operations/query_executor.py` | Query orchestration |
| `docs/postmortem-vectorlite-hnsw-complete.md` | Full HNSW bug postmortem |
