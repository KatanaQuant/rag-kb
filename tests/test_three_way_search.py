#!/usr/bin/env python3
"""
Three-Way Search Diagnostic Test

Purpose: Isolate whether HNSW, BM25, or RRF fusion is the accuracy bottleneck.

For each failing query, we test:
1. Vector only (HNSW) - Does it find the right content?
2. BM25 only (keyword) - Does it find the right content?
3. Hybrid (both + RRF) - Does fusion help or hurt?

Results help determine the fix path:
- Vector ✗, BM25 ✓ → Enable hybrid search (Phase 2)
- Vector ✓, BM25 ✓, Hybrid ✗ → Fix RRF fusion (Phase 5)
- Vector ✗, BM25 ✗ → Indexing problem (different investigation)

Run in container: python /app/tests/test_three_way_search.py
"""

import sqlite3
import json
import sys
import os
from pathlib import Path
from typing import List, Dict, Any, Tuple
from datetime import datetime

# Container paths - adjust if running locally
sys.path.insert(0, "/app")

from hybrid_search import BM25Searcher, HybridSearcher, RankFusion
from ingestion.database import VectorStore


# The 7 failing queries from v2.2.2 benchmark
FAILING_QUERIES = [
    {
        "query": "tidy first refactoring Kent Beck",
        "expected": "Tidy First",
        "expected_patterns": ["tidy first", "kent beck"],
        "category": "programming_books",
    },
    {
        "query": "Efficiently Inefficient hedge fund strategies",
        "expected": "Efficiently Inefficient",
        "expected_patterns": ["efficiently inefficient", "pedersen", "hedge fund"],
        "category": "trading_content",
    },
    {
        "query": "volatility risk premium VIX trading",
        "expected": "vix",
        "expected_patterns": ["vix", "volatility risk premium"],
        "category": "trading_content",
    },
    {
        "query": "Python trading system random price",
        "expected": "randompriceexample.py",
        "expected_patterns": ["randompriceexample", "random", "price", ".py"],
        "category": "code_files",
    },
    {
        "query": "Jupyter notebook trading rule",
        "expected": "asimpletradingrule.ipynb",
        "expected_patterns": ["asimpletradingrule", "trading", "rule", ".ipynb"],
        "category": "code_files",
    },
    {
        "query": "24 Assets Daniel Priestley categories types business building progression",
        "expected": "24 Assets",
        "expected_patterns": ["24 assets", "priestley", "daniel"],
        "category": "known_problematic",
    },
    {
        "query": "MAKE exit strategy sell company",
        "expected": "MAKE",
        "expected_patterns": ["make", "pieter levels", "indie maker"],
        "category": "known_problematic",
    },
]


def check_result_matches(results: List[Dict], expected_patterns: List[str]) -> bool:
    """Check if any result matches expected patterns."""
    if not results:
        return False

    # Check top 5 results
    for result in results[:5]:
        source = result.get("source", "").lower()
        content = result.get("content", "").lower()
        combined = f"{source} {content}"

        for pattern in expected_patterns:
            if pattern.lower() in combined:
                return True

    return False


def get_top_sources(results: List[Dict], n: int = 3) -> List[str]:
    """Get top N source names from results."""
    return [r.get("source", "?")[:40] for r in results[:n]]


def run_three_way_test(db_path: str = "/app/data/rag.db"):
    """
    Run the three-way search diagnostic test.

    Tests each failing query with:
    1. Vector search only (HNSW)
    2. BM25 keyword search only
    3. Hybrid search (Vector + BM25 + RRF fusion)
    """
    print(f"\n{'='*70}")
    print("THREE-WAY SEARCH DIAGNOSTIC TEST")
    print(f"{'='*70}")
    print(f"Database: {db_path}")
    print(f"Started: {datetime.now().isoformat()}")
    print(f"Testing {len(FAILING_QUERIES)} failing queries")
    print(f"{'='*70}\n")

    # Initialize stores
    store = VectorStore()
    conn = store.conn

    # Initialize BM25 and hybrid searchers
    bm25_searcher = BM25Searcher(conn)
    hybrid_searcher = HybridSearcher(conn)

    # Get embedding model
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer("Snowflake/snowflake-arctic-embed-l")

    results = {
        "timestamp": datetime.now().isoformat(),
        "queries": [],
        "summary": {
            "vector_found": 0,
            "bm25_found": 0,
            "hybrid_found": 0,
            "total": len(FAILING_QUERIES),
        }
    }

    for i, test_case in enumerate(FAILING_QUERIES, 1):
        query = test_case["query"]
        expected = test_case["expected"]
        patterns = test_case["expected_patterns"]
        category = test_case["category"]

        print(f"\n[{i}/{len(FAILING_QUERIES)}] Query: \"{query[:50]}...\"")
        print(f"     Expected: {expected}")
        print(f"     Category: {category}")

        # Generate query embedding
        embedding = model.encode(query).tolist()

        # 1. VECTOR ONLY (HNSW)
        vector_results = store.repo.search(embedding, top_k=10, threshold=None)
        vector_found = check_result_matches(vector_results, patterns)

        # 2. BM25 ONLY (keyword)
        bm25_raw = bm25_searcher.search(query, top_k=20)
        # Convert to dict format
        bm25_results = []
        for row in bm25_raw:
            bm25_results.append({
                "content": row[1],
                "source": Path(row[2]).name,
                "page": row[3],
                "score": float(row[4]),
            })
        bm25_found = check_result_matches(bm25_results, patterns)

        # 3. HYBRID (Vector + BM25 + RRF)
        hybrid_results = hybrid_searcher.search(query, vector_results, top_k=10)
        hybrid_found = check_result_matches(hybrid_results, patterns)

        # Print results
        v_mark = "✓" if vector_found else "✗"
        b_mark = "✓" if bm25_found else "✗"
        h_mark = "✓" if hybrid_found else "✗"

        print(f"     Vector (HNSW): {v_mark}  Top: {get_top_sources(vector_results)}")
        print(f"     BM25 (keyword): {b_mark}  Top: {get_top_sources(bm25_results)}")
        print(f"     Hybrid (fused): {h_mark}  Top: {get_top_sources(hybrid_results)}")

        # Update summary
        if vector_found:
            results["summary"]["vector_found"] += 1
        if bm25_found:
            results["summary"]["bm25_found"] += 1
        if hybrid_found:
            results["summary"]["hybrid_found"] += 1

        # Store detailed results
        results["queries"].append({
            "query": query,
            "expected": expected,
            "category": category,
            "vector_found": vector_found,
            "bm25_found": bm25_found,
            "hybrid_found": hybrid_found,
            "vector_top_3": get_top_sources(vector_results),
            "bm25_top_3": get_top_sources(bm25_results),
            "hybrid_top_3": get_top_sources(hybrid_results),
        })

    # Print summary
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")

    total = results["summary"]["total"]
    v_pct = results["summary"]["vector_found"] / total * 100
    b_pct = results["summary"]["bm25_found"] / total * 100
    h_pct = results["summary"]["hybrid_found"] / total * 100

    print(f"Vector only (HNSW):  {results['summary']['vector_found']}/{total} ({v_pct:.0f}%)")
    print(f"BM25 only (keyword): {results['summary']['bm25_found']}/{total} ({b_pct:.0f}%)")
    print(f"Hybrid (fused):      {results['summary']['hybrid_found']}/{total} ({h_pct:.0f}%)")

    # Diagnosis
    print(f"\n{'='*70}")
    print("DIAGNOSIS")
    print(f"{'='*70}")

    if v_pct < 50 and b_pct >= 50:
        print("→ HNSW is the bottleneck. BM25 finds content that HNSW misses.")
        print("→ ACTION: Enable hybrid search in async path (Phase 2)")
    elif v_pct >= 50 and b_pct >= 50 and h_pct < max(v_pct, b_pct):
        print("→ RRF fusion is DEGRADING results.")
        print("→ ACTION: Tune RRF parameters (Phase 5)")
    elif v_pct < 50 and b_pct < 50:
        print("→ BOTH vector and BM25 fail. Indexing problem?")
        print("→ ACTION: Check if expected content is actually indexed")
    else:
        print("→ No clear pattern. Need deeper investigation.")

    print(f"\n{'='*70}\n")

    # Save results to JSON
    output_path = Path(__file__).parent.parent / "benchmarks" / "three-way-diagnostic.json"
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Results saved to: {output_path}")

    return results


def main():
    """Run from command line or container."""
    import argparse
    parser = argparse.ArgumentParser(description="Three-way search diagnostic test")
    parser.add_argument("--db", default="/app/data/rag.db", help="Database path")
    args = parser.parse_args()

    run_three_way_test(args.db)


if __name__ == "__main__":
    main()
