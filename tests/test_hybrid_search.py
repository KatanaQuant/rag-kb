"""
Tests for hybrid search functionality
"""
import sqlite3
import pytest
from hybrid_search import KeywordSearcher, BM25Searcher, RankFusion, HybridSearcher


@pytest.fixture
def db_conn():
    """Create test database with FTS5 support"""
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE documents (
            id INTEGER PRIMARY KEY,
            file_path TEXT,
            file_hash TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE chunks (
            id INTEGER PRIMARY KEY,
            document_id INTEGER,
            content TEXT,
            page INTEGER
        )
    """)
    conn.execute("""
        CREATE VIRTUAL TABLE fts_chunks
        USING fts5(chunk_id UNINDEXED, content)
    """)

    conn.execute("INSERT INTO documents VALUES (1, 'test.pdf', 'hash1')")
    conn.execute("INSERT INTO chunks VALUES (1, 1, 'machine learning algorithms', 1)")
    conn.execute("INSERT INTO chunks VALUES (2, 1, 'deep neural networks', 2)")
    conn.execute("INSERT INTO fts_chunks VALUES (1, 'machine learning algorithms')")
    conn.execute("INSERT INTO fts_chunks VALUES (2, 'deep neural networks')")
    conn.commit()
    return conn


@pytest.fixture
def db_conn_no_fts():
    """Create test database without FTS5 (for BM25 testing)"""
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE documents (
            id INTEGER PRIMARY KEY,
            file_path TEXT,
            file_hash TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE chunks (
            id INTEGER PRIMARY KEY,
            document_id INTEGER,
            content TEXT,
            page INTEGER
        )
    """)

    conn.execute("INSERT INTO documents VALUES (1, 'test.pdf', 'hash1')")
    conn.execute("INSERT INTO chunks VALUES (1, 1, 'machine learning algorithms', 1)")
    conn.execute("INSERT INTO chunks VALUES (2, 1, 'deep neural networks', 2)")
    conn.execute("INSERT INTO chunks VALUES (3, 1, 'launch your business in 27 days', 3)")
    conn.commit()
    return conn


def test_keyword_searcher_finds_matches(db_conn):
    """Test FTS5 keyword search"""
    searcher = KeywordSearcher(db_conn)
    results = searcher.search("machine learning", top_k=5)
    assert len(results) > 0
    assert "machine learning" in results[0][1]


def test_keyword_searcher_empty_results(db_conn):
    """Test keyword search with no matches"""
    searcher = KeywordSearcher(db_conn)
    results = searcher.search("quantum physics", top_k=5)
    assert len(results) == 0


def test_rank_fusion_merges_results():
    """Test RRF algorithm merges results"""
    fusion = RankFusion(k=60)
    vector_results = [
        {'content': 'deep neural networks', 'source': 'test.pdf', 'page': 2, 'score': 0.9}
    ]
    keyword_results = [
        (1, 'machine learning algorithms', 'test.pdf', 1, -2.5)
    ]

    merged = fusion.fuse(vector_results, keyword_results)
    assert len(merged) >= 1
    assert all('score' in r for r in merged)


def test_rank_fusion_deduplicates():
    """Test RRF deduplicates same content"""
    fusion = RankFusion(k=60)
    vector_results = [
        {'content': 'machine learning', 'source': 'test.pdf', 'page': 1, 'score': 0.9}
    ]
    keyword_results = [
        (1, 'machine learning', 'test.pdf', 1, -2.5)
    ]

    merged = fusion.fuse(vector_results, keyword_results)
    assert len(merged) == 1


def test_rank_fusion_boosts_overlap():
    """Test RRF boosts items in both results"""
    fusion = RankFusion(k=60)
    vector_results = [
        {'content': 'machine learning', 'source': 'test.pdf', 'page': 1, 'score': 0.5}
    ]
    keyword_results = [
        (1, 'machine learning', 'test.pdf', 1, -2.5)
    ]

    merged = fusion.fuse(vector_results, keyword_results)
    assert merged[0]['score'] > 0.01


def test_hybrid_searcher_graceful_fallback(db_conn):
    """Test hybrid search falls back to vector on BM25 search error

    When BM25 search or fusion fails, HybridSearcher should return
    the original vector results unchanged.
    """
    from unittest.mock import patch

    hybrid = HybridSearcher(db_conn)
    vector_results = [
        {'content': 'test', 'source': 'test.pdf', 'page': 1, 'score': 0.9}
    ]

    # Mock BM25 search to raise an exception
    with patch.object(hybrid.keyword, 'search', side_effect=Exception("BM25 failure")):
        results = hybrid.search("test query", vector_results, top_k=5)

    # Should fall back to vector results unchanged when BM25 search fails
    assert results == vector_results


def test_hybrid_searcher_combines_results(db_conn):
    """Test hybrid search combines vector and keyword"""
    hybrid = HybridSearcher(db_conn)
    vector_results = [
        {'content': 'deep neural networks', 'source': 'test.pdf', 'page': 2, 'score': 0.9}
    ]

    results = hybrid.search("machine learning", vector_results, top_k=5)
    assert len(results) >= 1


def test_hybrid_searcher_respects_top_k(db_conn):
    """Test hybrid search respects top_k limit"""
    hybrid = HybridSearcher(db_conn)
    vector_results = [
        {'content': f'result {i}', 'source': 'test.pdf', 'page': i, 'score': 0.9}
        for i in range(10)
    ]

    results = hybrid.search("test", vector_results, top_k=3)
    assert len(results) <= 3


def test_rank_fusion_make_key_consistency():
    """Test key generation is consistent"""
    fusion = RankFusion()
    result1 = {'content': 'test content', 'source': 'file.pdf', 'page': 1, 'score': 0.9}
    result2 = {'content': 'test content', 'source': 'file.pdf', 'page': 1, 'score': 0.5}

    key1 = fusion._make_key(result1)
    key2 = fusion._make_key(result2)
    assert key1 == key2
