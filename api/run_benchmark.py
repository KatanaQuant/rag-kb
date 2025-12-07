#!/usr/bin/env python3
"""
RAG-KB Benchmark Suite

Runs a comprehensive set of queries against the RAG system and measures:
- Accuracy: Did the expected source appear in results?
- Relevance: What score did the expected source receive?
- Latency: How long did the query take?
- Position: Where did the expected source appear in rankings?

EVALUATION CATEGORIES:
- CORRECT: Exact expected source returned as top result
- ACCEPTABLE: Related/relevant content returned (e.g., blog post about the book)
- WRONG: Completely unrelated content returned

The `acceptable_alt` field in queries defines patterns that count as "acceptable"
even if not the exact expected source. This is important because:
- A blog post BY the author ABOUT the book is still useful
- A related article on the same topic is still useful
- But completely unrelated content is a failure

Usage:
    PYENV_VERSION=system python3 benchmarks/run_benchmark.py
    # or
    docker exec rag-api python /app/benchmarks/run_benchmark.py

NOTE FOR FUTURE AGENTS:
Always run this benchmark before and after making changes to measure impact.
Compare results to previous baselines in benchmarks/*.json files.
"""

import json
import time
import sys
from datetime import datetime
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: requests library required. Install with: pip install requests")
    sys.exit(1)

API_URL = "http://localhost:8000"

# Benchmark queries organized by category
# Each query can have:
#   - expected: The ideal source to return
#   - acceptable_alt: List of patterns that are "good enough" (related content)
#   - partial_match: If True, expected can match anywhere in source name
BENCHMARK_QUERIES = {
    "business_books": [
        # 24 Assets - Daniel Priestley
        {
            "text": "24 Assets intangible intellectual property",
            "expected": "24 Assets",
            "category": "business",
            "style": "keyword",
        },
        {
            "text": "seven types of assets for entrepreneurs",
            "expected": "24 Assets",
            "category": "business",
            "style": "semantic",
        },
        # Side Hustle - Chris Guillebeau
        {
            "text": "side hustle business ideas",
            "expected": "Side Hustle",
            "category": "business",
            "style": "keyword",
        },
        {
            "text": "27 days launch business",
            "expected": "Side Hustle",
            "category": "business",
            "style": "keyword",
        },
        # High Output Management - Andy Grove
        {
            "text": "High Output Management leverage",
            "expected": "High Output Management",
            "category": "business",
            "style": "keyword",
        },
        {
            "text": "output indicators manager productivity",
            "expected": "High Output Management",
            "category": "business",
            "style": "semantic",
        },
        # MAKE - Pieter Levels
        {
            "text": "MAKE Pieter Levels ship startup",
            "expected": "MAKE",
            "category": "business",
            "style": "keyword",
        },
        {
            "text": "indie maker blueprint bootstrapping",
            "expected": "MAKE",
            "category": "business",
            "style": "semantic",
        },
    ],
    "programming_books": [
        # Tidy First - Kent Beck
        {
            "text": "tidy first refactoring Kent Beck",
            "expected": "Tidy First",
            "category": "programming",
            "style": "keyword",
            # 99Bottles also by Sandi Metz is about refactoring - acceptable
            "acceptable_alt": ["99bottles", "refactoring"],
        },
        {
            "text": "code cleanup before feature",
            "expected": "Tidy First",
            "category": "programming",
            "style": "semantic",
            # Content about refactoring/cleanup is acceptable
            "acceptable_alt": ["99bottles", "refactoring"],
        },
        # The Little Go Book
        {
            "text": "Go programming basics Karl Seguin",
            "expected": "Little Go Book",
            "category": "programming",
            "style": "keyword",
            # Any Go programming content is acceptable
            "acceptable_alt": ["lets-go", ".go", "golang"],
        },
        # Domain-Driven Design
        {
            "text": "domain driven design bounded context",
            "expected": "Domain-Driven Design",
            "category": "programming",
            "style": "keyword",
            # DDD with Golang book is also acceptable
            "acceptable_alt": ["domain-driven", "ddd"],
        },
        {
            "text": "aggregate root entity value object",
            "expected": "Domain-Driven Design",
            "category": "programming",
            "style": "semantic",
            "acceptable_alt": ["domain-driven", "ddd"],
        },
        # Refactoring - Martin Fowler
        {
            "text": "refactoring Martin Fowler code smells",
            "expected": "Refactoring",
            "category": "programming",
            "style": "keyword",
            # 99Bottles is also about refactoring - acceptable
            "acceptable_alt": ["99bottles", "tidy first"],
        },
        # Test-Driven Development
        {
            "text": "TDD test driven development Kent Beck",
            "expected": "Test-Driven Development",
            "category": "programming",
            "style": "keyword",
        },
    ],
    "trading_content": [
        # Smart Portfolios - Robert Carver
        {
            "text": "Smart Portfolios Robert Carver",
            "expected": "Smart Portfolios",
            "category": "trading",
            "style": "keyword",
            # Blog posts BY Carver ABOUT the book are acceptable
            "acceptable_alt": ["carver", "smart-portfolios", "portfolio"],
        },
        {
            "text": "portfolio optimization asset allocation",
            "expected": "Smart Portfolios",
            "category": "trading",
            "style": "semantic",
            # Any portfolio optimization content is acceptable
            "acceptable_alt": ["portfolio", "asset allocation", "carver"],
        },
        # Efficiently Inefficient
        {
            "text": "Efficiently Inefficient hedge fund strategies",
            "expected": "Efficiently Inefficient",
            "category": "trading",
            "style": "keyword",
            # Hedge fund related content is acceptable
            "acceptable_alt": ["hedge fund", "pedersen", "efficiently"],
        },
        # Robot Wealth articles
        {
            "text": "volatility risk premium VIX trading",
            "expected": "vix",
            "category": "trading",
            "style": "semantic",
            "partial_match": True,
            "acceptable_alt": ["volatility", "vrp", "risk premium"],
        },
        {
            "text": "backtesting trading strategy simulation",
            "expected": "backtest",
            "category": "trading",
            "style": "semantic",
            "partial_match": True,
            "acceptable_alt": ["trading", "strategy", "simulation"],
        },
    ],
    "code_files": [
        # Python trading code
        {
            "text": "Python trading system random price",
            "expected": "randompriceexample.py",
            "category": "code",
            "style": "keyword",
            # Any Python trading code is acceptable
            "acceptable_alt": [".py", "trading", "pysystemtrade"],
        },
        # Go context middleware
        {
            "text": "Go context middleware web",
            "expected": "context.go",
            "category": "code",
            "style": "keyword",
            # Any Go web/middleware code is acceptable
            "acceptable_alt": [".go", "lets-go", "middleware"],
        },
        # Jupyter notebook trading
        {
            "text": "Jupyter notebook trading rule",
            "expected": "asimpletradingrule.ipynb",
            "category": "code",
            "style": "keyword",
            # Any trading notebook is acceptable
            "acceptable_alt": [".ipynb", "trading", "notebook"],
        },
    ],
    "known_problematic": [
        # These queries have been observed to fail - included to track improvements
        {
            "text": "24 Assets Daniel Priestley categories types business building progression",
            "expected": "24 Assets",
            "category": "business",
            "style": "long_semantic",
            "note": "KNOWN ISSUE: Long queries dilute BM25 matching",
            # Business/entrepreneurship content might be acceptable
            "acceptable_alt": ["priestley", "entrepreneur", "business"],
        },
        {
            "text": "24 Assets seven categories",
            "expected": "24 Assets",
            "category": "business",
            "style": "short",
            "note": "KNOWN ISSUE: Previously returned Smart Portfolios",
        },
        {
            "text": "MAKE exit strategy sell company",
            "expected": "MAKE",
            "category": "business",
            "style": "semantic",
            "note": "KNOWN ISSUE: Previously returned Naming Things",
            # Startup/business exit content is acceptable
            "acceptable_alt": ["startup", "business", "exit", "indie"],
        },
    ],
}


def run_query(text: str, top_k: int = 5) -> dict:
    """Execute a query against the RAG API."""
    start = time.time()
    try:
        response = requests.post(
            f"{API_URL}/query",
            json={"text": text, "top_k": top_k},
            timeout=None,  # No timeout for v1.9.1 sqlite-vec
        )
        elapsed = time.time() - start

        if response.status_code != 200:
            return {
                "error": f"HTTP {response.status_code}",
                "latency_ms": elapsed * 1000,
            }

        data = response.json()
        return {
            "results": data.get("results", []),
            "latency_ms": elapsed * 1000,
        }
    except requests.exceptions.RequestException as e:
        return {
            "error": str(e),
            "latency_ms": (time.time() - start) * 1000,
        }


def check_match(result_source: str, expected: str, partial_match: bool = False) -> bool:
    """Check if result matches expected source."""
    if not result_source or not expected:
        return False

    source_lower = result_source.lower()
    expected_lower = expected.lower()

    if partial_match:
        return expected_lower in source_lower
    return expected_lower in source_lower


def check_acceptable(result_source: str, acceptable_patterns: list) -> bool:
    """Check if result matches any acceptable alternative pattern."""
    if not result_source or not acceptable_patterns:
        return False

    source_lower = result_source.lower()
    for pattern in acceptable_patterns:
        if pattern.lower() in source_lower:
            return True
    return False


def evaluate_query(query: dict, response: dict) -> dict:
    """
    Evaluate query results against expectations.

    Returns evaluation with one of three grades:
    - "correct": Exact expected source returned as top result
    - "acceptable": Related/relevant content returned (matches acceptable_alt)
    - "wrong": Completely unrelated content returned
    """
    result = {
        "query": query["text"],
        "expected": query["expected"],
        "acceptable_alt": query.get("acceptable_alt", []),
        "category": query.get("category", "unknown"),
        "style": query.get("style", "unknown"),
        "note": query.get("note", ""),
        "latency_ms": response.get("latency_ms", 0),
    }

    if "error" in response:
        result["error"] = response["error"]
        result["grade"] = "wrong"
        result["correct"] = False
        result["acceptable"] = False
        result["position"] = -1
        result["top_score"] = 0
        result["top_result"] = None
        result["all_results"] = []
        return result

    results = response.get("results", [])
    partial_match = query.get("partial_match", False)
    acceptable_patterns = query.get("acceptable_alt", [])

    # Find position of expected result
    position = -1
    for i, r in enumerate(results):
        if check_match(r.get("source", ""), query["expected"], partial_match):
            position = i + 1  # 1-indexed
            break

    top_result = results[0].get("source", "") if results else None

    # Determine grade
    is_correct = position == 1
    is_acceptable = not is_correct and check_acceptable(top_result, acceptable_patterns)

    if is_correct:
        grade = "correct"
    elif is_acceptable:
        grade = "acceptable"
    else:
        grade = "wrong"

    result["grade"] = grade
    result["correct"] = is_correct
    result["acceptable"] = is_acceptable
    result["in_top_5"] = position > 0
    result["position"] = position
    result["top_result"] = top_result
    result["top_score"] = results[0].get("score", 0) if results else 0
    result["expected_score"] = (
        results[position - 1].get("score", 0) if position > 0 else 0
    )
    result["all_results"] = [
        {"source": r.get("source", ""), "score": r.get("score", 0)} for r in results[:5]
    ]

    return result


def run_benchmark(categories: list = None) -> dict:
    """Run full benchmark suite."""
    if categories is None:
        categories = list(BENCHMARK_QUERIES.keys())

    all_results = []
    category_stats = {}

    print(f"\n{'='*60}")
    print(f"RAG-KB Benchmark Suite - v1.9.1 Baseline (sqlite-vec)")
    print(f"{'='*60}")
    print(f"API: {API_URL}")
    print(f"Categories: {', '.join(categories)}")
    print(f"Started: {datetime.now().isoformat()}")
    print(f"{'='*60}\n")

    for category in categories:
        if category not in BENCHMARK_QUERIES:
            print(f"WARNING: Unknown category '{category}', skipping")
            continue

        queries = BENCHMARK_QUERIES[category]
        print(f"\n--- {category.upper()} ({len(queries)} queries) ---\n")

        category_results = []
        for query in queries:
            response = run_query(query["text"])
            result = evaluate_query(query, response)
            category_results.append(result)
            all_results.append(result)

            # Print result with grade-based status
            grade = result.get("grade", "wrong")
            if grade == "correct":
                status = "\u2705"  # Green checkmark
            elif grade == "acceptable":
                status = "\U0001F7E1"  # Yellow circle
            else:
                status = "\u274c"  # Red X

            print(f"{status} \"{query['text'][:50]}...\"" if len(query["text"]) > 50 else f"{status} \"{query['text']}\"")
            print(f"   Expected: {query['expected']}")
            print(f"   Got: {result['top_result']} (score: {result['top_score']:.3f})")
            print(f"   Grade: {grade.upper()}")
            if result["position"] > 1:
                print(f"   Expected at position: {result['position']} (score: {result['expected_score']:.3f})")
            print(f"   Latency: {result['latency_ms']:.0f}ms")
            if result.get("note"):
                print(f"   Note: {result['note']}")
            print()
            sys.stdout.flush()  # Ensure output appears immediately

        # Category statistics
        correct = sum(1 for r in category_results if r["correct"])
        acceptable = sum(1 for r in category_results if r.get("acceptable"))
        wrong = sum(1 for r in category_results if r.get("grade") == "wrong")
        in_top_5 = sum(1 for r in category_results if r.get("in_top_5"))
        avg_latency = sum(r["latency_ms"] for r in category_results) / len(category_results)

        category_stats[category] = {
            "total": len(category_results),
            "correct": correct,
            "acceptable": acceptable,
            "wrong": wrong,
            "in_top_5": in_top_5,
            "accuracy": correct / len(category_results),
            "usable_rate": (correct + acceptable) / len(category_results),
            "top_5_rate": in_top_5 / len(category_results),
            "avg_latency_ms": avg_latency,
        }

    # Overall statistics
    total = len(all_results)
    correct = sum(1 for r in all_results if r["correct"])
    acceptable = sum(1 for r in all_results if r.get("acceptable"))
    wrong = sum(1 for r in all_results if r.get("grade") == "wrong")
    in_top_5 = sum(1 for r in all_results if r.get("in_top_5"))
    avg_latency = sum(r["latency_ms"] for r in all_results) / total if total > 0 else 0

    summary = {
        "total": total,
        "correct": correct,
        "acceptable": acceptable,
        "wrong": wrong,
        "in_top_5": in_top_5,
        "accuracy": correct / total if total > 0 else 0,
        "usable_rate": (correct + acceptable) / total if total > 0 else 0,
        "top_5_rate": in_top_5 / total if total > 0 else 0,
        "avg_latency_ms": avg_latency,
    }

    # Print summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"Total queries: {total}")
    print(f"\u2705 Correct (exact match): {correct}/{total} ({summary['accuracy']*100:.1f}%)")
    print(f"\U0001F7E1 Acceptable (related):  {acceptable}/{total} ({acceptable/total*100:.1f}%)")
    print(f"\u274c Wrong (unrelated):     {wrong}/{total} ({wrong/total*100:.1f}%)")
    print(f"\n\U0001F4CA Usable (correct+acceptable): {correct+acceptable}/{total} ({summary['usable_rate']*100:.1f}%)")
    print(f"In top-5: {in_top_5}/{total} ({summary['top_5_rate']*100:.1f}%)")
    print(f"Average latency: {avg_latency:.0f}ms")
    print()

    print("By category:")
    for cat, stats in category_stats.items():
        print(f"  {cat}: {stats['correct']}\u2705 {stats['acceptable']}\U0001F7E1 {stats['wrong']}\u274c ({stats['usable_rate']*100:.1f}% usable)")

    # Identify wrong results (not just non-correct)
    wrong_results = [r for r in all_results if r.get("grade") == "wrong"]
    if wrong_results:
        print(f"\nWrong queries ({len(wrong_results)}) - NEED IMPROVEMENT:")
        for r in wrong_results:
            print(f"  \u274c \"{r['query'][:40]}...\" -> {r['top_result']}")
            print(f"      Expected: {r['expected']}")

    return {
        "version": "v1.9.1-baseline",
        "timestamp": datetime.now().isoformat(),
        "api_url": API_URL,
        "summary": summary,
        "category_stats": category_stats,
        "results": all_results,
    }


def save_results(results: dict, output_path: str):
    """Save benchmark results to JSON file."""
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to: {output_path}")


def main():
    """Main entry point."""
    # Check API health (no timeout - v1.9.1 sqlite-vec is slow)
    try:
        health = requests.get(f"{API_URL}/health", timeout=None)
        if health.status_code != 200:
            print(f"ERROR: API health check failed (HTTP {health.status_code})")
            sys.exit(1)
    except requests.exceptions.RequestException as e:
        print(f"ERROR: Cannot connect to API at {API_URL}: {e}")
        sys.exit(1)

    # Run benchmark
    results = run_benchmark()

    # Save results
    output_dir = Path(__file__).parent
    output_file = output_dir / "v1.9.1-baseline.json"
    save_results(results, str(output_file))


if __name__ == "__main__":
    main()
