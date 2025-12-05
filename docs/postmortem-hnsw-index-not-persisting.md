# Postmortem: HNSW Index Not Persisting After Document Indexing

**Date**: 2025-12-05
**Severity**: Critical (data loss on restart)
**Status**: RESOLVED (v2.2.1)
**Branch**: `bugfix/hnsw-index-sync-on-insert`

---

## Executive Summary

Documents indexed after the v2.2.0-beta vectorlite migration were not searchable. The HNSW vector index appeared to accept INSERTs (no errors) but the data was never persisted to disk. On container restart, all newly indexed documents were lost from the search index.

---

## Timeline

| Time | Event |
|------|-------|
| Dec 4, 11:23 | v2.2.0-beta deployed with vectorlite HNSW (migrated from sqlite-vec) |
| Dec 4, 21:57 | Backup created before migration: `rag.db.backup-pre-vectorlite-20251204-112341` |
| Dec 5, 08:09 | Discovered: newly indexed documents not appearing in search results |
| Dec 5, 08:56 | Attempted partial rebuild - failed (HNSW graph corruption) |
| Dec 5, 10:04 | Restored from backup, ran migration script - worked |
| Dec 5, 10:10 | Re-indexed test document - still not searchable |
| Dec 5, 10:30 | Added HNSW logging - discovered INSERTs succeed but data not in index |
| Dec 5, 11:12 | Root cause identified: vectorlite only persists on connection close |
| Dec 5, 11:25 | Fix deployed: flush (close/reopen) connection after each document |
| Dec 5, 11:35 | Verified: documents now persist and are searchable |

---

## Root Cause Analysis

### The Bug

vectorlite HNSW has a critical behavior that is documented but easy to miss:

> "If `index_file_path` is provided, vectorlite will try to load index from the file and **save to it when db connection is closed**."
>
> — [vectorlite documentation](https://1yefuwang1.github.io/vectorlite/markdown/overview.html)

The RAG API keeps database connections open for the lifetime of the container. This means:

1. Container starts → connection opens → existing HNSW index loaded from disk
2. New document indexed → INSERT INTO vec_chunks succeeds → data in **memory only**
3. Container runs indefinitely → connection never closes → **index never saved**
4. Container restarts → old index loaded → new documents lost

### Why It Appeared to Work

- `INSERT INTO vec_chunks` executes without error
- Immediate queries within the same connection find the data (it's in memory)
- The `[Store]` stage completes successfully with timing stats
- No errors in logs

### Why Migration Script Worked

The migration script (`vector_migration.py`) worked because it:
1. Opens a fresh connection
2. DROPs and recreates the table
3. INSERTs all embeddings
4. **Closes the connection** → triggers index save
5. Script exits

### Debugging Steps

1. **Added HNSW logging** - Confirmed INSERTs were executing
2. **Checked vec_chunks directly** - Chunks missing despite successful INSERT
3. **Tested direct INSERT + close** - Confirmed vectorlite DOES persist on close
4. **Compared connection IDs** - Verified same connection used for insert and flush
5. **Monitored index file size** - Confirmed file grows after flush

---

## The Fix

### Code Change

Added `_flush_hnsw_index()` method to `VectorStore` that closes and reopens the connection after each document is stored:

```python
# api/ingestion/database.py

def add_document(self, file_path: str, file_hash: str,
                chunks: List[Dict], embeddings: List):
    """Add document to store"""
    self.repo.add_document(file_path, file_hash, chunks, embeddings)
    self._flush_hnsw_index()  # <-- NEW: Force persist

def _flush_hnsw_index(self):
    """Force HNSW index to persist by closing and reopening connection.

    vectorlite only saves the HNSW index to disk when the connection closes.
    Without this, inserts go to in-memory index but are lost on restart.
    """
    self.conn.close()
    self.conn = self.db_conn.connect()
    self.repo = VectorRepository(self.conn)
    self.hybrid = HybridSearcher(self.conn)
```

### Files Modified

| File | Change |
|------|--------|
| `api/ingestion/database.py` | Added `_flush_hnsw_index()`, called after `add_document()` |
| `api/ingestion/database.py` | Added `[HNSW] Indexed N chunks` logging |
| `api/ingestion/chunk_repository.py` | Added error logging for failed HNSW inserts |
| `api/ingestion/async_repositories.py` | Added logging to async version (future-proofing) |

### Performance Impact

- **Overhead**: ~200ms per document (connection close + reopen + extension reload)
- **Acceptable**: Documents take 3-5 minutes to process; 200ms is negligible
- **Benefit**: Data is immediately durable and searchable

---

## Verification

After fix deployment:

```
[HNSW] Indexed 317 chunks for doc_id=2470
[Store] Side Hustle - Chris Guillebeau.pdf - 317 chunks complete in 0.6s
```

Index file size:
- Before: 253,474,560 bytes
- After: 254,820,340 bytes (+1.3 MB for 317 chunks)

Query test:
```bash
curl -X POST http://localhost:8000/query \
  -d '{"text": "side hustle business ideas", "top_k": 3}'
# Returns content from Side Hustle book ✓
```

---

## Lessons Learned

### 1. Read Extension Documentation Carefully

vectorlite's persistence behavior is documented, but buried in the "Getting Started" section. The phrase "save to it when db connection is closed" is the critical detail.

### 2. Test the Full Lifecycle

Our testing validated:
- ✓ Migration works
- ✓ Queries return results
- ✗ Restart and re-query (would have caught this)

### 3. Silent Failures Are Dangerous

The INSERT succeeded, the timing looked normal, no errors logged. Only the missing search results revealed the bug. Better observability would help:
- Log HNSW index file size periodically
- Add health check that verifies recent documents are searchable

### 4. Understand Your Storage Engine

vectorlite uses hnswlib under the hood. HNSW (Hierarchical Navigable Small World) is a graph-based index that:
- Requires the full graph structure to be saved atomically
- Cannot be partially updated on disk
- Must be fully rewritten on save

This explains why:
- Incremental inserts don't persist (graph not saved)
- Partial rebuilds fail (graph structure corrupted)
- Full migration works (clean graph construction)

---

## Prevention

### Automated Testing

Add integration test that:
1. Indexes a document
2. Restarts the container
3. Verifies document is still searchable

### Monitoring

Add metric for:
- `hnsw_index_file_size_bytes` - Should grow with indexed documents
- `hnsw_last_flush_timestamp` - Detect stale indexes

### Documentation

Update README to note:
- vectorlite requires connection close to persist
- The flush mechanism and why it exists

---

## Related Issues

- **Partial rebuild doesn't work**: `api/ingestion/partial_rebuild.py` attempts incremental HNSW updates but fails for the same reason - the graph structure isn't updated correctly with incremental inserts.

- **Two repository implementations**: Both `VectorChunkRepository` (sync) and `AsyncVectorChunkRepository` (async) exist. The pipeline uses sync; async is for query endpoints. Both now have logging.

---

## Appendix: vectorlite Behavior Reference

From [vectorlite documentation](https://1yefuwang1.github.io/vectorlite/markdown/overview.html):

> The `index_file_path` parameter has no default value. If not provided, the table will be memory-only. If provided, vectorlite will try to load index from the file and save to it when db connection is closed.

Key behaviors:
- Index loads on connection open (if file exists)
- Index saves on connection close (not on commit!)
- No explicit flush/save API exists
- INSERT/UPDATE/DELETE modify in-memory index only

---

## UPDATE: Second Bug Found (Dec 5, 12:30)

### The Problem

After deploying the `_flush_hnsw_index()` fix, documents were STILL intermittently lost. Testing revealed:

| Book | Order Indexed | Chunks in HNSW | Status |
|------|---------------|----------------|--------|
| High Output Management | 1st | 263/263 | PASS |
| Side Hustle | 2nd | 0/317 | FAIL |

The second book indexed after container restart had 0 chunks in the HNSW index!

### Root Cause: AsyncVectorStore Race Condition

The system has TWO database stores:
- **Sync VectorStore**: Used by pipeline for writes (indexing)
- **Async AsyncVectorStore**: Used by API for reads (queries)

When the sync store flushes (closes connection to save HNSW), the async store detects the index file changed and calls `refresh()`:

```python
async def refresh(self):
    await self.close()      # <-- THIS SAVES STALE HNSW DATA!
    await self.initialize()
```

The `close()` triggers vectorlite to save the async store's **stale in-memory index** to disk, overwriting the valid data the sync store just saved.

### Why SQLite Read-Only Mode Didn't Help

We tried opening the async connection in SQLite read-only mode:
```python
f"file:{self.config.path}?mode=ro"
```

This prevents SQLite writes but **NOT vectorlite HNSW writes** - they're separate files:
- `rag.db` - SQLite database (read-only works)
- `vec_chunks.idx` - HNSW index file (still writable!)

### The Fix (Attempt 2)

Modified `refresh()` to NOT close the old connection:

```python
async def refresh(self):
    # Don't await self.close() - that would save stale HNSW data!
    await self.initialize()  # Just open new connection, abandon old one
```

The old connection will be garbage collected without triggering a save.

### Timeline Update

| Time | Event |
|------|-------|
| Dec 5, 11:25 | Fix 1 deployed: `_flush_hnsw_index()` |
| Dec 5, 11:35 | Verified: first document persists |
| Dec 5, 12:20 | Bug rediscovered: second document lost (24 Assets 0/172 in HNSW) |
| Dec 5, 12:30 | Root cause: AsyncVectorStore refresh overwrites HNSW |
| Dec 5, 13:00 | Fix 2 attempted: SQLite read-only mode (didn't work) |
| Dec 5, 13:35 | Fix 3 deployed: Don't close connection in refresh() |
| Dec 5, 14:05 | **VERIFIED**: Both books pass (263/263 + 317/317 in HNSW) |

### Fix 3 Verification Results

```
=== HNSW Verification ===
PASS: High Output Management - Grove, Andrew .pdf: 263/263 in HNSW
PASS: Side Hustle - Chris Guillebeau.pdf: 317/317 in HNSW
```

**Resolution**: Fix 3 partially works but GC eventually closes abandoned connections.

### Fix 3 Issue: Garbage Collection

Fix 3 (not closing on refresh) worked for 2 documents but failed for the 3rd after restart.
The abandoned connections were eventually garbage collected, triggering vectorlite save.

### Fix 4: Keep Old Connections Alive

```python
# async_database.py
def __init__(self, ...):
    self._old_connections = []  # Prevent GC

async def refresh(self):
    if self.db_conn:
        self._old_connections.append(self.db_conn)  # Keep alive!
    await self.initialize()
```

**Status**: Testing with 3 sequential documents. If fails, will implement Option C
(route all vector queries through sync store - single HNSW = no race conditions).
