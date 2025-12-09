"""
Tests for hybrid search functionality
"""
import sqlite3
import pytest
from hybrid_search import KeywordSearcher, BM25Searcher, RankFusion, HybridSearcher


@pytest.fixture
def db_conn():
    """Create test database with sample data"""
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

    # Sample documents
    conn.execute("INSERT INTO documents VALUES (1, '/books/machine_learning_basics.pdf', 'hash1')")
    conn.execute("INSERT INTO documents VALUES (2, '/books/24_assets_portfolio.pdf', 'hash2')")

    # Sample chunks
    conn.execute("INSERT INTO chunks VALUES (1, 1, 'machine learning algorithms for beginners', 1)")
    conn.execute("INSERT INTO chunks VALUES (2, 1, 'deep neural networks explained', 2)")
    conn.execute("INSERT INTO chunks VALUES (3, 2, 'portfolio construction with 24 assets', 1)")
    conn.execute("INSERT INTO chunks VALUES (4, 2, 'asset allocation strategies', 2)")

    # FTS5 entries
    conn.execute("INSERT INTO fts_chunks VALUES (1, 'machine learning algorithms for beginners')")
    conn.execute("INSERT INTO fts_chunks VALUES (2, 'deep neural networks explained')")
    conn.execute("INSERT INTO fts_chunks VALUES (3, 'portfolio construction with 24 assets')")
    conn.execute("INSERT INTO fts_chunks VALUES (4, 'asset allocation strategies')")
    conn.commit()
    return conn


# =====================
# BM25Searcher Tests
# =====================

def test_bm25_searcher_finds_matches(db_conn):
    """Test BM25 probabilistic keyword search"""
    searcher = BM25Searcher(db_conn)
    results = searcher.search("machine learning", top_k=5)
    assert len(results) > 0
    assert "machine learning" in results[0][1]


def test_bm25_searcher_partial_match(db_conn):
    """Test BM25 returns partial matches (unlike FTS5 boolean AND)"""
    searcher = BM25Searcher(db_conn)
    # This would fail with FTS5 because "quantum" doesn't exist
    results = searcher.search("machine quantum", top_k=5)
    # BM25 should still return results for "machine" even though "quantum" is missing
    assert len(results) > 0


def test_bm25_searcher_empty_query(db_conn):
    """Test BM25 handles empty query"""
    searcher = BM25Searcher(db_conn)
    results = searcher.search("", top_k=5)
    assert len(results) == 0


def test_bm25_searcher_no_matches(db_conn):
    """Test BM25 handles completely unrelated query"""
    searcher = BM25Searcher(db_conn)
    results = searcher.search("xyzabc123", top_k=5)
    assert len(results) == 0


def test_bm25_title_boost(db_conn):
    """Test title boosting improves ranking for matching filenames"""
    searcher = BM25Searcher(db_conn)
    # Query "24 assets" should boost results from "24_assets_portfolio.pdf"
    results = searcher.search("24 assets", top_k=5)
    assert len(results) > 0
    # The chunk from 24_assets_portfolio.pdf should rank higher
    top_result = results[0]
    assert "24" in top_result[1] or "asset" in top_result[1].lower()


def test_bm25_refresh(db_conn):
    """Test BM25 index refresh after adding documents"""
    searcher = BM25Searcher(db_conn)

    # Add new document
    db_conn.execute("INSERT INTO documents VALUES (3, '/books/new_book.pdf', 'hash3')")
    db_conn.execute("INSERT INTO chunks VALUES (5, 3, 'brand new unique content', 1)")
    db_conn.commit()

    # Before refresh, shouldn't find new content
    results_before = searcher.search("brand new unique", top_k=5)

    # Refresh index
    searcher.refresh()

    # After refresh, should find new content
    results_after = searcher.search("brand new unique", top_k=5)
    assert len(results_after) > 0


# =====================
# KeywordSearcher Tests (deprecated but still functional)
# =====================

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


# =====================
# RankFusion Tests (k=20)
# =====================

def test_rank_fusion_merges_results():
    """Test RRF algorithm merges results"""
    fusion = RankFusion(k=20)
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
    fusion = RankFusion(k=20)
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
    fusion = RankFusion(k=20)
    vector_results = [
        {'content': 'machine learning', 'source': 'test.pdf', 'page': 1, 'score': 0.5}
    ]
    keyword_results = [
        (1, 'machine learning', 'test.pdf', 1, -2.5)
    ]

    merged = fusion.fuse(vector_results, keyword_results)
    # With k=20, score should be 1/(20+1) + 1/(20+1) = 2/21 ≈ 0.095
    assert merged[0]['score'] > 0.09


def test_rank_fusion_default_k_is_20():
    """Test RankFusion defaults to k=20 for better accuracy"""
    fusion = RankFusion()
    assert fusion.k == 20


def test_rank_fusion_make_key_consistency():
    """Test key generation is consistent"""
    fusion = RankFusion()
    result1 = {'content': 'test content', 'source': 'file.pdf', 'page': 1, 'score': 0.9}
    result2 = {'content': 'test content', 'source': 'file.pdf', 'page': 1, 'score': 0.5}

    key1 = fusion._make_key(result1)
    key2 = fusion._make_key(result2)
    assert key1 == key2


# =====================
# HybridSearcher Tests
# =====================

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


def test_hybrid_searcher_graceful_fallback(db_conn):
    """Test hybrid search returns results even when BM25 partially fails"""
    hybrid = HybridSearcher(db_conn)
    vector_results = [
        {'content': 'test', 'source': 'test.pdf', 'page': 1, 'score': 0.9}
    ]

    # Corrupt the database to trigger potential errors
    db_conn.execute("DROP TABLE chunks")

    # Search should still return results (from BM25's cached index or vector fallback)
    results = hybrid.search("test query", vector_results, top_k=5)
    assert len(results) >= 1
    # Check content is preserved
    assert results[0]['content'] == 'test'


def test_hybrid_searcher_uses_bm25(db_conn):
    """Test HybridSearcher uses BM25Searcher internally"""
    hybrid = HybridSearcher(db_conn)
    assert isinstance(hybrid.keyword, BM25Searcher)


def test_hybrid_searcher_refresh(db_conn):
    """Test hybrid searcher can refresh BM25 index"""
    hybrid = HybridSearcher(db_conn)

    # Should have method to refresh
    assert hasattr(hybrid, 'refresh_keyword_index')

    # Should not raise
    hybrid.refresh_keyword_index()
