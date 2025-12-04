#!/usr/bin/env python3
"""
Benchmark agentic query features (decomposition, suggestions, reranking).

Compares four configurations:
  A: No agentic features (decompose=false)
  B: v1 detection only (decompose=true, but v1 code that doesn't execute sub-queries)
  C: v2 execution (decompose=true with sub-query execution)
  D: v2 + reranking

Usage:
    # Run all benchmarks (assumes API has v2 code)
    python scripts/benchmark_agentic.py

    # Save results
    python scripts/benchmark_agentic.py --output .claude/research/agentic-benchmark-results.json
"""

import json
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

API_URL = "http://localhost:8000"

# Test queries: simple (shouldn't decompose) and compound (should decompose)
# Reduced set for CPU reranking benchmarks (~20-30s per query)
QUERIES = {
    "simple": [
        "What is technical debt?",
        "How does position sizing work?",
    ],
    "compound": [
        "Position sizing vs risk management",
        "Compare momentum and mean reversion strategies",
    ],
}


def query_api(text: str, decompose: bool = True, top_k: int = 5) -> dict:
    """Execute a single query against the API."""
    start = time.time()
    try:
        req_data = json.dumps({
            "text": text,
            "top_k": top_k,
            "decompose": decompose,
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{API_URL}/query",
            data=req_data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as response:
            data = json.loads(response.read().decode("utf-8"))

        elapsed = time.time() - start
        return {
            "status": "success",
            "elapsed_ms": round(elapsed * 1000, 1),
            "total_results": data.get("total_results", 0),
            "results": data.get("results", []),
            "suggestions": data.get("suggestions", []),
            "decomposition": data.get("decomposition", {}),
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "elapsed_ms": round((time.time() - start) * 1000, 1),
        }


def analyze_recall(results: list, query_type: str, sub_queries: list = None) -> dict:
    """Analyze recall quality for compound queries.

    For compound queries, check if results cover both sub-topics.
    """
    if not results:
        return {"coverage": 0, "sources": [], "avg_score": 0, "top_score": 0}

    sources = [r.get("source", "") for r in results]
    unique_sources = list(set(sources))

    # Source diversity as proxy for coverage
    coverage = len(unique_sources) / max(len(results), 1)

    return {
        "coverage": round(coverage, 2),
        "sources": unique_sources[:5],
        "avg_score": round(sum(r.get("score", 0) for r in results) / len(results), 4) if results else 0,
        "top_score": round(results[0].get("score", 0), 4) if results else 0,
    }


def run_benchmark_config(config_name: str, decompose: bool) -> dict:
    """Run all queries for a single configuration."""
    print(f"\n{'='*60}")
    print(f"Config {config_name}: decompose={decompose}")
    print("="*60)

    results = {
        "config": config_name,
        "decompose": decompose,
        "queries": {},
    }

    # Run simple queries
    print("\nSimple queries (should NOT decompose):")
    for query in QUERIES["simple"]:
        print(f"  {query[:50]}...", end=" ")
        data = query_api(query, decompose=decompose)
        results["queries"][query] = data

        decomp = data.get("decomposition", {})
        applied = decomp.get("applied", False)
        status = "✓" if not applied else "✗ (incorrectly decomposed)"
        print(f"{data['elapsed_ms']}ms {status}")

    # Run compound queries
    print("\nCompound queries (SHOULD decompose):")
    for query in QUERIES["compound"]:
        print(f"  {query[:50]}...", end=" ")
        data = query_api(query, decompose=decompose)
        results["queries"][query] = data

        decomp = data.get("decomposition", {})
        applied = decomp.get("applied", False)
        sub_queries = decomp.get("sub_queries", [])

        if decompose:
            status = f"✓ ({len(sub_queries)} sub-queries)" if applied else "✗ (not decomposed)"
        else:
            status = "✓ (skipped)" if not applied else "✗ (should be skipped)"

        recall = analyze_recall(data.get("results", []), "compound", sub_queries)
        print(f"{data['elapsed_ms']}ms {status} coverage={recall['coverage']}")

        results["queries"][query]["recall_analysis"] = recall

    return results


def run_single_query_benchmark(query: str, query_type: str) -> dict:
    """Run a single query with both configs, no caching between."""
    result = {
        "query": query,
        "type": query_type,
    }

    # Run with decompose=False first
    data_a = query_api(query, decompose=False)
    result["A_no_decompose"] = {
        "elapsed_ms": data_a.get("elapsed_ms", 0),
        "total_results": data_a.get("total_results", 0),
        "decomposition": data_a.get("decomposition", {}),
        "recall": analyze_recall(data_a.get("results", []), query_type),
    }

    # Run with decompose=True
    data_c = query_api(query, decompose=True)
    result["C_decompose"] = {
        "elapsed_ms": data_c.get("elapsed_ms", 0),
        "total_results": data_c.get("total_results", 0),
        "decomposition": data_c.get("decomposition", {}),
        "recall": analyze_recall(data_c.get("results", []), query_type),
        "sub_queries": data_c.get("decomposition", {}).get("sub_queries", []),
    }

    return result


def run_full_benchmark() -> dict:
    """Run the complete benchmark matrix with interleaved queries."""
    print("RAG-KB Agentic Features Benchmark")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("\nNote: Each query runs twice (A=no decompose, C=decompose)")
    print("      Queries are unique to avoid cache effects.\n")

    benchmark = {
        "timestamp": datetime.now().isoformat(),
        "api_url": API_URL,
        "results": [],
    }

    # Run simple queries
    print("Simple queries (should NOT decompose):")
    print("-" * 70)
    for query in QUERIES["simple"]:
        result = run_single_query_benchmark(query, "simple")
        benchmark["results"].append(result)

        a_ms = result["A_no_decompose"]["elapsed_ms"]
        c_ms = result["C_decompose"]["elapsed_ms"]
        c_decomp = result["C_decompose"]["decomposition"]
        applied = c_decomp.get("applied", False)
        status = "✓" if not applied else "✗ decomposed"

        print(f"  {query[:45]:<45} A:{a_ms:>6.0f}ms  C:{c_ms:>6.0f}ms  {status}")

    print()

    # Run compound queries
    print("Compound queries (SHOULD decompose):")
    print("-" * 70)
    for query in QUERIES["compound"]:
        result = run_single_query_benchmark(query, "compound")
        benchmark["results"].append(result)

        a_ms = result["A_no_decompose"]["elapsed_ms"]
        c_ms = result["C_decompose"]["elapsed_ms"]
        a_cov = result["A_no_decompose"]["recall"]["coverage"]
        c_cov = result["C_decompose"]["recall"]["coverage"]
        c_decomp = result["C_decompose"]["decomposition"]
        applied = c_decomp.get("applied", False)
        sub_queries = result["C_decompose"].get("sub_queries", [])

        if applied:
            status = f"✓ {len(sub_queries)} sub-q"
        else:
            status = "✗ not decomposed"

        cov_change = "+" if c_cov > a_cov else ("=" if c_cov == a_cov else "-")
        print(f"  {query[:40]:<40} A:{a_ms:>5.0f}ms C:{c_ms:>5.0f}ms  cov:{a_cov:.1f}→{c_cov:.1f}{cov_change}  {status}")

    return benchmark


def print_summary(benchmark: dict):
    """Print a summary comparison of configs."""
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)

    results = benchmark.get("results", [])
    compound_results = [r for r in results if r.get("type") == "compound"]

    # Timing summary
    print("\nTiming (compound queries):")
    print("-"*70)
    total_a = sum(r["A_no_decompose"]["elapsed_ms"] for r in compound_results)
    total_c = sum(r["C_decompose"]["elapsed_ms"] for r in compound_results)
    print(f"  Total A (no decompose): {total_a:.0f}ms")
    print(f"  Total C (v2 decompose): {total_c:.0f}ms")
    print(f"  Overhead: {total_c - total_a:+.0f}ms ({((total_c/total_a)-1)*100:+.1f}%)" if total_a > 0 else "")

    # Score comparison
    print("\nScore comparison (compound queries):")
    print("-"*70)
    a_avg_scores = [r["A_no_decompose"]["recall"]["avg_score"] for r in compound_results]
    c_avg_scores = [r["C_decompose"]["recall"]["avg_score"] for r in compound_results]
    a_top_scores = [r["A_no_decompose"]["recall"]["top_score"] for r in compound_results]
    c_top_scores = [r["C_decompose"]["recall"]["top_score"] for r in compound_results]

    print(f"  Avg score (A): {sum(a_avg_scores)/len(a_avg_scores):.3f}")
    print(f"  Avg score (C): {sum(c_avg_scores)/len(c_avg_scores):.3f}")
    print(f"  Top score (A): {sum(a_top_scores)/len(a_top_scores):.3f}")
    print(f"  Top score (C): {sum(c_top_scores)/len(c_top_scores):.3f}")

    # Coverage summary
    print("\nCoverage (source diversity):")
    print("-"*70)
    improved = 0
    same = 0
    worse = 0
    for r in compound_results:
        a_cov = r["A_no_decompose"]["recall"]["coverage"]
        c_cov = r["C_decompose"]["recall"]["coverage"]
        if c_cov > a_cov:
            improved += 1
        elif c_cov == a_cov:
            same += 1
        else:
            worse += 1
    print(f"  Improved: {improved}/{len(compound_results)}")
    print(f"  Same:     {same}/{len(compound_results)}")
    print(f"  Worse:    {worse}/{len(compound_results)}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Benchmark agentic query features")
    parser.add_argument("--output", "-o", type=Path, help="Save results to JSON file")
    args = parser.parse_args()

    benchmark = run_full_benchmark()
    print_summary(benchmark)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w") as f:
            json.dump(benchmark, f, indent=2)
        print(f"\nResults saved to: {args.output}")


if __name__ == "__main__":
    main()
