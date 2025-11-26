# Known Issues

## Critical

### 1. ~~Broken PDF Detection Gap~~ ✅ FIXED
**Status:** IMPLEMENTED in v1.1.0

PDF integrity validation now detects:
- Empty files (0 bytes)
- Missing PDF header signature
- Truncated files (missing `%%EOF` marker)
- Corrupt xref tables
- Unreadable page structures

Implementation:
- [api/ingestion/pdf_integrity.py](api/ingestion/pdf_integrity.py) - Validator using pypdfium2
- Integrated into [DoclingExtractor](api/ingestion/extractors/docling_extractor.py:78) - Pre-flight check
- [PDFIntegrityStrategy](api/ingestion/completeness_strategies.py:238) - Completeness check
- 10 tests in [test_pdf_integrity.py](tests/test_pdf_integrity.py)
- 3 tests in [test_completeness_strategies.py](tests/test_completeness_strategies.py:332)

**What it catches:**
- Partially downloaded PDFs
- Corrupted files from failed transfers
- Truncated files from interrupted writes
- Invalid PDF structure

**What it WON'T catch:**
- Content hash mismatches (need separate tracking)
- Deliberate content changes to same file
- Page count validation (PDF metadata unreliable)

---

## Performance

### 2. Database Query Blocking (Async Not Fully Async)
**Priority:** HIGH - Investigate

Both `/documents/completeness` (3+ minutes) and `/queue/jobs` (seconds delay) are slow, even with async database migration.

**Symptoms:**
- API endpoints that query DB block other requests
- Long response times for simple queries
- Not just N+1 - even simple queries are slow

**Hypothesis:** Synchronous sqlite3 calls are blocking the asyncio event loop. The "async database migration" may not have converted ALL query paths.

**Investigation needed:**
```python
# Check if these are truly async or blocking:
- ProcessingProgressTracker.get_progress()
- ChunkRepository.count_by_document()  # Opens NEW connection per call!
- DocumentRepository.list_all()
```

**Possible solutions:**
1. Use connection pool instead of per-query connections
2. Convert remaining sync sqlite3 to aiosqlite
3. Run sync queries in thread pool executor
4. Dedicated read replica / connection for read-heavy endpoints

---

### 3. Completeness API N+1 Query Pattern
**Priority:** MEDIUM

The `/documents/completeness` endpoint does 2659 queries for 1329 documents:

```python
# Current pattern (BAD):
for doc in documents:                    # 1329 iterations
    progress = tracker.get_progress()    # 1 query each
    chunk_count = repo.count_by_document() # 1 query + NEW CONNECTION each
```

**Fix:** Single batch query:
```sql
SELECT
    d.id, d.file_path,
    pp.status, pp.total_chunks, pp.chunks_processed,
    (SELECT COUNT(*) FROM chunks c WHERE c.document_id = d.id) as actual_chunks
FROM documents d
LEFT JOIN processing_progress pp ON d.file_path = pp.file_path
```

---

## Tracking

### 4. 11 Documents Without Progress Records
**Priority:** LOW

After migration, 11 documents have chunks but no `processing_progress` record. These were likely indexed before progress tracking was added.

**Fix:** Re-index these files or create backfill script for progress records.

---

## Investigation Queue

- [ ] Profile DB query times to identify bottlenecks
- [ ] Check if aiosqlite is used consistently across all endpoints
- [ ] Measure connection pool vs per-query connection performance
- [ ] Consider read-only replica for analytics endpoints
