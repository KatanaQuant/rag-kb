"""
Tests for query caching
"""
import pytest
from query_cache import QueryCache


def test_cache_miss_returns_none():
    """Test cache returns None on miss"""
    cache = QueryCache(max_size=10)
    result = cache.get("test query", top_k=5, threshold=None)
    assert result is None


def test_cache_hit_returns_result():
    """Test cache returns cached result"""
    cache = QueryCache(max_size=10)
    results = [{'content': 'test', 'score': 0.9}]

    cache.put("test query", top_k=5, threshold=None, results=results)
    cached = cache.get("test query", top_k=5, threshold=None)

    assert cached == results


def test_cache_key_case_insensitive():
    """Test cache keys are case insensitive"""
    cache = QueryCache(max_size=10)
    results = [{'content': 'test', 'score': 0.9}]

    cache.put("Test Query", top_k=5, threshold=None, results=results)
    cached = cache.get("test query", top_k=5, threshold=None)

    assert cached == results


def test_cache_key_whitespace_normalized():
    """Test cache keys normalize whitespace"""
    cache = QueryCache(max_size=10)
    results = [{'content': 'test', 'score': 0.9}]

    cache.put("  test query  ", top_k=5, threshold=None, results=results)
    cached = cache.get("test query", top_k=5, threshold=None)

    assert cached == results


def test_cache_different_top_k_different_entry():
    """Test different top_k creates different entry"""
    cache = QueryCache(max_size=10)
    results1 = [{'content': 'test1', 'score': 0.9}]
    results2 = [{'content': 'test2', 'score': 0.8}]

    cache.put("query", top_k=5, threshold=None, results=results1)
    cache.put("query", top_k=10, threshold=None, results=results2)

    cached1 = cache.get("query", top_k=5, threshold=None)
    cached2 = cache.get("query", top_k=10, threshold=None)

    assert cached1 == results1
    assert cached2 == results2


def test_cache_different_threshold_different_entry():
    """Test different threshold creates different entry"""
    cache = QueryCache(max_size=10)
    results1 = [{'content': 'test1', 'score': 0.9}]
    results2 = [{'content': 'test2', 'score': 0.8}]

    cache.put("query", top_k=5, threshold=None, results=results1)
    cache.put("query", top_k=5, threshold=0.5, results=results2)

    cached1 = cache.get("query", top_k=5, threshold=None)
    cached2 = cache.get("query", top_k=5, threshold=0.5)

    assert cached1 == results1
    assert cached2 == results2


def test_cache_lru_eviction():
    """Test LRU eviction when cache full"""
    cache = QueryCache(max_size=2)

    cache.put("query1", top_k=5, threshold=None, results=[{'score': 0.9}])
    cache.put("query2", top_k=5, threshold=None, results=[{'score': 0.8}])
    cache.put("query3", top_k=5, threshold=None, results=[{'score': 0.7}])

    assert cache.get("query1", top_k=5, threshold=None) is None
    assert cache.get("query2", top_k=5, threshold=None) is not None
    assert cache.get("query3", top_k=5, threshold=None) is not None


def test_cache_access_updates_lru():
    """Test accessing entry updates LRU order"""
    cache = QueryCache(max_size=2)

    cache.put("query1", top_k=5, threshold=None, results=[{'score': 0.9}])
    cache.put("query2", top_k=5, threshold=None, results=[{'score': 0.8}])

    cache.get("query1", top_k=5, threshold=None)

    cache.put("query3", top_k=5, threshold=None, results=[{'score': 0.7}])

    assert cache.get("query1", top_k=5, threshold=None) is not None
    assert cache.get("query2", top_k=5, threshold=None) is None


def test_cache_clear_empties_cache():
    """Test clear removes all entries"""
    cache = QueryCache(max_size=10)

    cache.put("query1", top_k=5, threshold=None, results=[{'score': 0.9}])
    cache.put("query2", top_k=5, threshold=None, results=[{'score': 0.8}])

    cache.clear()

    assert cache.get("query1", top_k=5, threshold=None) is None
    assert cache.get("query2", top_k=5, threshold=None) is None
    assert len(cache.cache) == 0
    assert len(cache.access_order) == 0


def test_cache_max_size_zero():
    """Test cache with max_size 0 always evicts"""
    cache = QueryCache(max_size=0)

    cache.put("query", top_k=5, threshold=None, results=[{'score': 0.9}])

    assert cache.get("query", top_k=5, threshold=None) is None


def test_cache_handles_complex_results():
    """Test cache stores complex result objects"""
    cache = QueryCache(max_size=10)
    results = [
        {'content': 'long text content', 'source': 'file.pdf', 'page': 1, 'score': 0.95},
        {'content': 'another chunk', 'source': 'file.pdf', 'page': 2, 'score': 0.85}
    ]

    cache.put("complex query", top_k=5, threshold=0.5, results=results)
    cached = cache.get("complex query", top_k=5, threshold=0.5)

    assert cached == results
    assert len(cached) == 2
