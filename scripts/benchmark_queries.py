#!/usr/bin/env python3
"""
Benchmark query tool for RAG-KB.

Runs predefined queries and saves responses for before/after comparison.

Usage:
    # Capture baseline
    python scripts/benchmark_queries.py --output benchmarks/baseline.json

    # After implementation
    python scripts/benchmark_queries.py --output benchmarks/enhanced.json

    # Compare
    python scripts/benchmark_queries.py --compare benchmarks/baseline.json benchmarks/enhanced.json
"""

import argparse
import json
import sys
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

# Benchmark queries covering actual KB content
BENCHMARK_QUERIES = [
    # OOP/Refactoring
    "what is the single responsibility principle",
    "how to refactor long methods",
    "extract method refactoring and when to use it",
    "dependency injection vs service locator",
    # Systematic Trading
    "what is position sizing",
    "how to calculate sharpe ratio",
    "momentum strategy implementation and backtesting",
    "risk management for trading systems",
]

DEFAULT_API_URL = "http://localhost:8000"


def run_queries(api_url: str, top_k: int = 5) -> dict:
    """Run all benchmark queries and collect responses."""
    results = {
        "timestamp": datetime.now().isoformat(),
        "api_url": api_url,
        "top_k": top_k,
        "queries": {},
    }

    for query in BENCHMARK_QUERIES:
        print(f"  Running: {query[:50]}...")
        try:
            req_data = json.dumps({"text": query, "top_k": top_k}).encode("utf-8")
            req = urllib.request.Request(
                f"{api_url}/query",
                data=req_data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=120) as response:
                data = json.loads(response.read().decode("utf-8"))

            results["queries"][query] = {
                "status": "success",
                "total_results": data.get("total_results", 0),
                "results": data.get("results", []),
                # New fields (will be null/missing in baseline)
                "suggestions": data.get("suggestions"),
                "decomposition": data.get("decomposition"),
            }
        except Exception as e:
            results["queries"][query] = {
                "status": "error",
                "error": str(e),
            }

    return results


def save_results(results: dict, output_path: Path) -> None:
    """Save benchmark results to JSON file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Saved to: {output_path}")


def load_results(path: Path) -> dict:
    """Load benchmark results from JSON file."""
    with open(path) as f:
        return json.load(f)


def compare_results(baseline_path: Path, enhanced_path: Path) -> None:
    """Compare baseline and enhanced benchmark results."""
    baseline = load_results(baseline_path)
    enhanced = load_results(enhanced_path)

    print("\n" + "=" * 60)
    print("BENCHMARK COMPARISON")
    print("=" * 60)
    print(f"Baseline:  {baseline['timestamp']}")
    print(f"Enhanced:  {enhanced['timestamp']}")
    print("=" * 60)

    for query in BENCHMARK_QUERIES:
        print(f"\nQuery: {query}")
        print("-" * 40)

        b_data = baseline["queries"].get(query, {})
        e_data = enhanced["queries"].get(query, {})

        # Compare result counts
        b_count = b_data.get("total_results", 0)
        e_count = e_data.get("total_results", 0)
        print(f"  Results: {b_count} -> {e_count}")

        # Check for new fields
        if e_data.get("suggestions"):
            print(f"  Suggestions: {e_data['suggestions']}")
        else:
            print("  Suggestions: (none)")

        decomp = e_data.get("decomposition")
        if decomp and decomp.get("applied"):
            print(f"  Decomposition: {decomp.get('sub_queries', [])}")
        else:
            print("  Decomposition: (not applied)")

        # Compare top result scores
        b_results = b_data.get("results", [])
        e_results = e_data.get("results", [])

        if b_results and e_results:
            b_score = b_results[0].get("score", 0)
            e_score = e_results[0].get("score", 0)
            e_rerank = e_results[0].get("rerank_score")

            score_str = f"  Top score: {b_score:.3f} -> {e_score:.3f}"
            if e_rerank is not None:
                score_str += f" (rerank: {e_rerank:.3f})"
            print(score_str)

    print("\n" + "=" * 60)


def main():
    parser = argparse.ArgumentParser(description="RAG-KB Query Benchmark Tool")
    parser.add_argument(
        "--output", "-o", type=Path, help="Output file for benchmark results"
    )
    parser.add_argument(
        "--compare",
        "-c",
        nargs=2,
        type=Path,
        metavar=("BASELINE", "ENHANCED"),
        help="Compare two benchmark files",
    )
    parser.add_argument(
        "--api-url",
        default=DEFAULT_API_URL,
        help=f"API URL (default: {DEFAULT_API_URL})",
    )
    parser.add_argument(
        "--top-k", type=int, default=5, help="Number of results per query (default: 5)"
    )

    args = parser.parse_args()

    if args.compare:
        compare_results(args.compare[0], args.compare[1])
    elif args.output:
        print(f"Running {len(BENCHMARK_QUERIES)} benchmark queries...")
        results = run_queries(args.api_url, args.top_k)
        save_results(results, args.output)

        # Summary
        success = sum(
            1 for q in results["queries"].values() if q.get("status") == "success"
        )
        print(f"\nCompleted: {success}/{len(BENCHMARK_QUERIES)} queries successful")
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
