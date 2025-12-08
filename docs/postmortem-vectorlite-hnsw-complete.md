# Comprehensive Postmortem: Vectorlite HNSW Migration Issues

**Date Range**: December 4-7, 2025
**Severity**: Critical (data loss + accuracy regression + index corruption)
**Status**: RESOLVED - All issues fixed in v2.2.4-beta, **permanently eliminated by PostgreSQL migration**
**Final Result**: 92.3% accuracy (EXCEEDS v1.9.1 baseline of 84.6%)
**Reproducibility**: Verified 2025-12-07 - concurrent operations stable, graceful shutdown persists

> **Update (2025-12-08):** The project migrated entirely to PostgreSQL + pgvector, eliminating all vectorlite-related issues permanently. This postmortem documents the journey and lessons learned. See [Release Notes](RELEASES/v2.3.0-beta.md).
>
> **Related:** [Query Accuracy Investigation](postmortem-query-accuracy-investigation.md) - detailed analysis of the accuracy investigation phase (Bug 4)

---

## Executive Summary

The vectorlite migration from sqlite-vec introduced five distinct bugs that together caused:
1. **Data loss** - Newly indexed documents not persisted (Bug 1)
2. **Race conditions** - Multiple connections overwriting each other's HNSW index (Bug 2)
3. **Orphan pollution** - Delete cascade not cleaning up vector/FTS tables (Bug 3)
4. **Accuracy regression** - Default ef=10 parameter gave only ~31% recall (Bug 4)
5. **Index corruption** - Per-write flush caused file-level race conditions (Bug 5)

After fixing all issues, v2.2.4-beta achieves **92.3% usable accuracy** (vs 84.6% in v1.9.1) while maintaining **120x faster queries** (553ms vs 60,932ms).

**Key Insight**: vectorlite ONLY persists HNSW index on `conn.close()`. This single behavior caused Bugs 1, 2, and 5 - each a different manifestation of the same underlying limitation.

---

## Timeline of Events

| Date/Time | Event | Impact |
|-----------|-------|--------|
| Dec 4, 11:23 | v2.2.0-beta deployed with vectorlite HNSW | Migration from sqlite-vec |
| Dec 5, 08:09 | Bug 1: Documents not searchable after indexing | Data loss |
| Dec 5, 11:25 | Fix 1: `_flush_hnsw_index()` - close/reopen connection | Partial fix |
| Dec 5, 12:20 | Bug 2: Second document overwrites first | Race condition |
| Dec 5, 13:35 | Fix 2: Don't close async connections on refresh | Partial fix |
| Dec 5, 14:05 | Fix 3: Keep old connections alive (prevent GC) | **v2.2.1 RELEASED** |
| Dec 5, 16:00 | Bug 3: Delete cascade not cleaning vec_chunks/fts_chunks | Orphan pollution |
| Dec 5, 18:15 | Fix 4: Delete cascade + maintenance scripts | **v2.2.2 RELEASED** |
| Dec 5, 21:00 | Accuracy investigation begins | 73.1% usable (vs 84.6% baseline) |
| Dec 6, 07:00 | Title boosting implemented | 80.8% usable |
| Dec 6, 10:30 | Root cause found: ef=10 default (~31% recall) | Critical insight |
| Dec 6, 13:41 | Fix 5: ef=150 HNSW tuning | **92.3% usable** |
| Dec 7, 03:00 | Bug 5: Index corrupts to 0 bytes during concurrent ops | **Critical corruption** |
| Dec 7, 05:30 | Root cause: per-write flush creates file-level race | Diagnosis complete |
| Dec 7, 07:00 | Fix 6: Periodic flush + graceful shutdown (remove per-write) | **FINAL FIX** |
| Dec 7, 07:45 | Verification: concurrent DELETE+search stable | **v2.2.4-beta READY** |

---

## Bug 1: HNSW Index Not Persisting

### Symptoms
- Documents indexed after migration not appearing in search results
- INSERT INTO vec_chunks succeeds without error
- Data visible within session, lost after container restart

### Root Cause
vectorlite only persists the HNSW index when the database connection closes:

> "If `index_file_path` is provided, vectorlite will try to load index from the file and **save to it when db connection is closed**."

The RAG API keeps connections open indefinitely → index never saved → data lost on restart.

### Fix
Added `_flush_hnsw_index()` to force persist after each document:

```python
def _flush_hnsw_index(self):
    """Force HNSW index to persist by closing and reopening connection."""
    self.conn.close()
    self.conn = self.db_conn.connect()
    self.repo = VectorRepository(self.conn)
```

---

## Bug 2: AsyncVectorStore Race Condition

### Symptoms
- First document persists, second document lost
- Non-deterministic behavior

### Root Cause
Two database stores exist:
- **Sync VectorStore**: Pipeline writes (indexing)
- **Async AsyncVectorStore**: API reads (queries)

When sync store flushes (closes connection), async store detects file change and calls `refresh()`:

```python
async def refresh(self):
    await self.close()      # <-- SAVES STALE IN-MEMORY INDEX!
    await self.initialize()
```

The async `close()` overwrites the valid index with its stale in-memory version.

### Fix Attempts
1. **SQLite read-only mode**: Prevents SQLite writes but NOT vectorlite HNSW writes (separate files)
2. **Don't close on refresh**: Works until garbage collector closes abandoned connection
3. **Keep old connections alive**: Final fix - prevent GC from triggering save

```python
def __init__(self, ...):
    self._old_connections = []  # Prevent GC

async def refresh(self):
    if self.db_conn:
        self._old_connections.append(self.db_conn)  # Keep alive!
    await self.initialize()
```

---

## Bug 3: Delete Cascade Missing

### Symptoms
- knn_search returns "NO CHUNK" entries
- Same content appears with different chunk IDs
- Search returns stale/orphan results

### Root Cause
`AsyncVectorStore.delete_document()` only cleaned chunks and documents tables:

```python
async def _delete_document_data(self, doc_id: int):
    await self.conn.execute("DELETE FROM chunks WHERE document_id = ?", (doc_id,))
    await self.conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    # MISSING: DELETE FROM vec_chunks
    # MISSING: DELETE FROM fts_chunks
```

### Impact Assessment
| Metric | Value |
|--------|-------|
| Orphan chunks (invalid doc_id) | 3,113 |
| Orphan vec_chunks embeddings | 7,233 |
| Orphan fts_chunks entries | 23,505 |

### Fix
Added cascade deletes + maintenance scripts:
- `scripts/cleanup_orphans.py` - One-time cleanup
- `scripts/rebuild_hnsw_index.py` - Fast HNSW rebuild (copies valid embeddings)
- `scripts/rebuild_fts.py` - FTS rebuild

---

## Bug 4: Default ef=10 Causes ~31% Recall

### Symptoms
- 73.1% usable accuracy (down from 84.6% in v1.9.1)
- Specific books "invisible" to search (wrong vectors returned)
- Hybrid search helped but couldn't fully compensate

### Root Cause (THE BIG ONE)

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
| 10 | **31.6%** | 35µs |
| 50 | 72.3% | 99µs |
| 100 | 88.6% | 168µs |
| **150** | **95.5%** | 310µs |

**We were operating at 31.6% recall!** This explains why HNSW was returning completely wrong vectors.

### Why Title Boosting Helped But Wasn't Enough
Title boosting improved accuracy from 73.1% → 80.8% by helping BM25 rescue queries where the filename matched. But the underlying HNSW recall was still broken.

### Fix
Set ef=150 in both async and sync repositories:

```python
async def _execute_vector_search(self, blob: bytes, top_k: int, ef: int = 150):
    cursor = await self.conn.execute("""
        SELECT v.rowid, v.distance
        FROM vec_chunks v
        WHERE knn_search(v.embedding, knn_param(?, ?, ?))
    """, (blob, top_k, ef))
```

### Result
| Metric | v2.2.2 (ef=10) | v2.2.4-beta (ef=150) | v1.9.1 (exact) |
|--------|----------------|-----------------|----------------|
| Usable | 73.1% | **92.3%** | 84.6% |
| Latency | ~500ms | ~553ms | 60,932ms |

v2.2.4-beta now **exceeds** the v1.9.1 baseline while maintaining 120x faster queries!

---

## Bug 5: Index Corruption During Concurrent Operations

### Symptoms
- HNSW index (`vec_chunks.idx`) truncates to 0 bytes during DELETE + search
- Search returns 0 results despite 51k+ chunks in database
- Index corrupts during `docker-compose build --no-cache` followed by API calls
- Non-deterministic - depends on timing of concurrent operations

### Reproduction Test Results (2025-12-07)

| Step | Index Size | Checksum | Status |
|------|------------|----------|--------|
| Before test | 218MB | `831fe0fe...` | Good |
| After `--no-cache` build | 218MB | `831fe0fe...` | Good |
| After container startup | 218MB | `831fe0fe...` | Good |
| **After DELETE call** | **0 bytes** | - | **CORRUPTED** |
| After search call | 218MB | (different) | Rebuilt but broken |
| Search test | - | - | **0 results** |

### Root Cause

The fix for Bug 1 (`_flush_hnsw_index()` after every write) created a new problem: **file-level race conditions**.

```python
def _flush_hnsw_index_unlocked(self):
    self.conn.close()      # vectorlite starts writing 218MB HNSW to disk
    # === RACE WINDOW ===
    # Another thread's operation interferes with file write
    # File may be truncated or partially written
    self.conn = self.db_conn.connect()  # Opens corrupted/partial file
    self.repo = VectorRepository(self.conn)
```

**The issue:** vectorlite's write on `conn.close()` is NOT atomic. During the 218MB file write:
1. Background indexing calls `add_document()` → `_flush_hnsw_index_unlocked()`
2. `conn.close()` begins writing 218MB HNSW file
3. API DELETE request arrives via `asyncio.to_thread()`
4. DELETE's database operations interfere with file write
5. Result: 0-byte file (truncated during write)

### Architecture Context

The dual-store was already consolidated (commit 60e17f0):
- Single `VectorStore` instance with `threading.RLock`
- `AsyncVectorStoreAdapter` wraps it with `asyncio.to_thread()`

**The RLock DOES protect Python-level access, but cannot prevent file-level races** because vectorlite writes happen outside Python's control during `conn.close()`.

### Fix

**Remove per-write flush entirely.** Instead:

1. **Keep connection open** during app lifetime - no close/reopen race
2. **Periodic background flush** (every 5 minutes) with thread-safe locking
3. **Graceful shutdown** flushes via `close()` method

```python
class VectorStore:
    FLUSH_INTERVAL_SECONDS = 300  # 5 minutes

    def __init__(self, config):
        self._lock = threading.RLock()
        self._flush_timer = None
        self._closed = False
        # ... initialization ...
        self._start_periodic_flush()

    def _start_periodic_flush(self):
        """Start periodic HNSW flush timer as safety net."""
        def flush_and_reschedule():
            if self._closed:
                return
            try:
                self._flush_hnsw_index()
            finally:
                if not self._closed:
                    self._flush_timer = threading.Timer(
                        self.FLUSH_INTERVAL_SECONDS,
                        flush_and_reschedule
                    )
                    self._flush_timer.daemon = True
                    self._flush_timer.start()

        self._flush_timer = threading.Timer(...)
        self._flush_timer.daemon = True
        self._flush_timer.start()

    def close(self):
        """Close connection and persist HNSW index."""
        self._closed = True
        self._stop_periodic_flush()
        self.db_conn.close()  # Triggers HNSW persist
```

### Verification (2025-12-07)

| Test | Before Fix | After Fix |
|------|------------|-----------|
| Concurrent DELETE + search | **0-byte corruption** | 218MB stable |
| Graceful shutdown (`docker stop`) | N/A | Checksum changes (persisted) |
| Restart preservation | Lost data | 1634 docs preserved |

### Known Limitation

vectorlite lacks Write-Ahead Log (WAL). With periodic flush every 5 minutes:
- **Maximum data loss on crash**: 5 minutes of new embeddings
- **Recovery**: Run `rebuild_hnsw` script (~55 seconds)

This is a fundamental vectorlite limitation. For production systems requiring zero data loss, consider migrating to pgvector (PostgreSQL with full ACID compliance).

---

## Complete Fix Summary

### v2.2.1 Fixes
1. `_flush_hnsw_index()` - Force persist after each document (later replaced)
2. Keep old async connections alive (prevent GC overwrite)

### v2.2.2 Fixes
3. Delete cascade to vec_chunks and fts_chunks
4. Maintenance scripts for orphan cleanup
5. HNSW health check on startup

### v2.2.4-beta Fixes
6. **ef=150** HNSW search quality parameter (THE KEY FIX for accuracy)
7. Title boosting for BM25 (helps book queries)
8. rank_bm25 replaces FTS5 boolean MATCH
9. **Remove per-write flush** - Eliminates corruption from file-level races
10. **Periodic background flush** (every 5 min) - Safety net for crash recovery
11. **Graceful shutdown persistence** - `close()` method triggers HNSW save
12. **Thread safety locks** - RLock on all public VectorStore methods
13. **Maintenance API** - 8 new endpoints for database health and repair

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
- [ ] Restart and re-query (would have caught Bug 1)
- [ ] Multiple document indexing (would have caught Bug 2)
- [ ] Delete and verify cleanup (would have caught Bug 3)
- [ ] Accuracy benchmarks (would have caught Bug 4)
- [ ] Concurrent operations (would have caught Bug 5)

### 3. Dual Store Architecture is Dangerous
Having both sync (VectorStore) and async (AsyncVectorStore) touching the same HNSW index file created race conditions. **FIXED**: Consolidated to single VectorStore with AsyncVectorStoreAdapter wrapper.

### 4. Approximate Search Needs Calibration
HNSW trades accuracy for speed. The trade-off must be explicitly tuned:
- ef=10: 31% recall, 35µs (unusable)
- ef=150: 95% recall, 310µs (production-ready)
- exact: 100% recall, milliseconds (too slow for large corpus)

### 5. Establish Baseline Before Migration
We should have run the benchmark suite BEFORE and AFTER migration:
- v1.9.1: 84.6% usable, 60,932ms
- v2.2.0-beta: Would have shown immediate regression

### 6. Fixes Can Create New Bugs (Feedback Loops)
**Critical lesson from Bug 5**: The fix for Bug 1 (per-write flush) directly caused Bug 5 (file-level corruption). The progression:
- Bug 1: Connection never closed → data not persisted
- Fix 1: Close/reopen after every write
- Bug 5: Close/reopen creates file-level race conditions

**Better approach**: Understand the underlying system behavior (vectorlite only writes on close) and design around it, rather than fighting it with frequent close/reopen cycles.

### 7. Python Locks Don't Protect File Operations
The RLock protected Python-level access, but vectorlite's HNSW file write happens at the C/SQLite level during `conn.close()`. Threading locks cannot prevent file-level races. For true atomicity, need:
- Atomic file operations (temp file + rename)
- WAL-based databases (PostgreSQL/pgvector)
- File-level locking (fcntl/flock)

### 8. Consider Vector Database Maturity
vectorlite is lightweight and fast, but lacks production durability features:
- No WAL (Write-Ahead Log)
- No crash recovery
- Non-atomic writes

For production systems, consider purpose-built vector databases:
- **pgvector**: Full PostgreSQL ACID, WAL, crash recovery
- **Weaviate**: Purpose-built with WAL + snapshots
- **Chroma**: Simpler but less mature persistence

---

## Configuration Reference (v2.2.4-beta)

### What's Enabled
| Feature | Setting | Purpose |
|---------|---------|---------|
| HNSW ef_search | 150 | ~95% recall (was 10 = 31%) |
| Hybrid search | RRF k=20 | Combine vector + keyword |
| rank_bm25 | BM25Okapi | Probabilistic keyword scoring |
| Title boosting | 1.5x-3x | Boost when filename matches query |
| Periodic HNSW flush | 300s (5 min) | Safety net for crash recovery |
| Graceful shutdown flush | On close() | Ensures data persistence |

### What's Disabled
| Feature | Reason |
|---------|--------|
| RERANKING_ENABLED | No improvement over title boosting |
| QUERY_EXPANSION_ENABLED | +10x latency without accuracy gain |
| Per-write HNSW flush | **Removed** - caused file-level corruption |

### Files Modified
| File | Changes |
|------|---------|
| `api/ingestion/async_repositories.py` | ef=150, vector search |
| `api/ingestion/search_repository.py` | ef=150 |
| `api/ingestion/async_database.py` | Cascade delete, _old_connections |
| `api/ingestion/database.py` | Periodic flush, close(), RLock on all methods, removed per-write flush |
| `api/hybrid_search.py` | Title boosting, rank_bm25 |
| `api/startup/phases/sanitization_phase.py` | HNSW health check |
| `api/app_state.py` | Shutdown calls VectorStore.close() |

---

## Benchmark Results

### Final Comparison
| Version | Correct | Acceptable | Wrong | Usable | Latency |
|---------|---------|------------|-------|--------|---------|
| v1.9.1 (sqlite-vec) | 17 (65%) | 5 (19%) | 4 (15%) | 84.6% | 60,932ms |
| v2.2.2 (ef=10) | 14 (54%) | 5 (19%) | 7 (27%) | 73.1% | ~500ms |
| **v2.2.4-beta (ef=150)** | **19 (73%)** | **5 (19%)** | **2 (8%)** | **92.3%** | **553ms** |

### Category Performance
| Category | v1.9.1 | v2.2.4-beta |
|----------|--------|--------|
| business_books | 100% | 100% |
| programming_books | 85.7% | 100% |
| trading_content | 60% | 100% |
| code_files | 66.7% | 33.3% |
| known_problematic | 100% | 100% |

### Remaining Failures (2/26)
Both are code file queries - a known limitation:
1. "Python trading system random price" → randompriceexample.py
2. "Jupyter notebook trading rule" → asimpletradingrule.ipynb

Would need better code/notebook chunking or contextual embeddings.

---

## Prevention Measures Implemented

### Automated Testing
- E2E routine now includes benchmark suite with thresholds
- Regression gate: <85% usable blocks release
- Category-specific thresholds prevent silent degradation

### Monitoring
- HNSW health check on startup
- `verify_integrity.py` script for manual checks

### Documentation
- This postmortem
- `CHANGELOG.md` with version history
- `docs/RELEASES/v2.2.4-beta.md` for release notes

---

## References

- [vectorlite documentation](https://1yefuwang1.github.io/vectorlite/markdown/overview.html)
- [hnswlib ALGO_PARAMS.md](https://github.com/nmslib/hnswlib/blob/master/ALGO_PARAMS.md)
- [vectorlite benchmarks](https://dev.to/yefuwang/introducing-vectorlite-a-fast-and-tunable-vector-search-extension-for-sqlite-4dcl)
- [Anthropic Contextual Retrieval](https://www.anthropic.com/news/contextual-retrieval) - Future improvement reference

---

## Future Recommendations

### ~~Short-term (v2.2.x)~~ Superseded by v2.3.0
- ~~Monitor periodic flush logs for any issues~~
- ~~Keep backup of known-good HNSW index~~
- ~~If crash occurs, use `rebuild_hnsw` script for recovery~~

### ~~Medium-term (v2.3.0)~~ [x] COMPLETED
**Migrated to pgvector** for proper ACID compliance:

| Feature | vectorlite | pgvector (v2.3.0) |
|---------|-----------|-------------------|
| ACID compliance | No | Full PostgreSQL |
| WAL/durability | No | Yes |
| Crash recovery | Manual rebuild | Automatic |
| Migration effort | - | **DONE** |

**v2.3.0 migration completed 2025-12-07:**
- 1634 documents migrated
- 51542 chunks migrated
- 51361 vectors migrated
- 51542 FTS entries rebuilt
- 92.3% accuracy verified

See [v2.3.0 Release Notes](RELEASES/v2.3.0-beta.md) for migration guide.

---

## Appendix: Related Files

| File | Purpose |
|------|---------|
| `docs/ROADMAP.md` | Project roadmap including pgvector migration plan |
| `docs/MAINTENANCE.md` | Database maintenance procedures |
| `docs/TROUBLESHOOTING.md` | Common issues and solutions |
| `tests/test_hnsw_persistence.py` | TDD tests for HNSW persistence |
| `tests/test_unified_vector_store.py` | Tests for unified architecture |
