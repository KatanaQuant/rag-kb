# Known Issues

This document tracks known issues, limitations, and their workarounds.

## 1. HybridChunker Can Exceed Model's Max Sequence Length

**Issue:** Docling's HybridChunker with `merge_peers=True` can create chunks that exceed the embedding model's maximum sequence length, resulting in warning messages like:

```
Token indices sequence length is longer than the specified maximum sequence length for this model (8202 > 8192). Running this sequence through the model will result in indexing errors
```

**Root Cause:**
- HybridChunker doesn't strictly enforce the `max_tokens` parameter ([docling-core#119](https://github.com/docling-project/docling-core/issues/119))
- When `merge_peers=True`, adjacent chunks with the same metadata are merged, potentially exceeding the token limit
- Long sentences or paragraphs remain unsplit even when they exceed the limit

**Current Impact:**
- **Minimal**: sentence-transformers automatically truncates oversized chunks
- Affects ~10-40 characters at the end of oversized chunks
- System continues to function normally

**Affected Configuration:**
- Models with sequence length limits (e.g., `Snowflake/snowflake-arctic-embed-l-v2.0` has 8192 token limit)
- `SEMANTIC_CHUNKING=true` (uses HybridChunker)
- Large documents with mergeable adjacent chunks

**Ideal Solution (Best Case Scenario):**

The system should handle this in layers:

1. **Prevention Layer** (Chunking):
   - HybridChunker should strictly enforce max_tokens before merging
   - OR set `CHUNK_MAX_TOKENS` to ~75% of model's limit (e.g., 6000 for 8192-token models)
   - Validate chunk sizes after merging and split oversized chunks

2. **Detection Layer** (Pre-embedding):
   ```python
   # Before encoding, validate chunk sizes
   def validate_chunk_sizes(chunks, model_max_length):
       for chunk in chunks:
           token_count = count_tokens(chunk['content'])
           if token_count > model_max_length:
               # Option A: Split oversized chunk
               # Option B: Log warning with chunk metadata
               # Option C: Truncate with explicit marker
   ```

3. **Graceful Handling Layer** (Embedding):
   ```python
   # Explicitly configure model truncation behavior
   model.max_seq_length = 8192
   embeddings = model.encode(
       texts,
       show_progress_bar=False,
       truncate_dim=model.max_seq_length  # Explicit truncation
   )
   ```

4. **Observability Layer**:
   - Log which documents/chunks were truncated
   - Track truncation metrics (frequency, token count distribution)
   - Alert if truncation rate exceeds threshold

**Current Workaround:**

Option 1 (Recommended): Accept automatic truncation
- No changes needed
- sentence-transformers handles it gracefully
- Minimal information loss (~10 tokens per affected chunk)

Option 2: Add explicit model configuration (prevents warning):
```python
# In api/main.py ModelLoader.load()
model = SentenceTransformer(model_name)
model.max_seq_length = 8192  # Match model's limit
```

Option 3: Lower CHUNK_MAX_TOKENS (requires re-indexing):
```bash
# In .env
CHUNK_MAX_TOKENS=6000  # Leave buffer for merge_peers
```

**Status:** Accepted limitation until docling-core#119 is resolved

**Related:**
- [Docling HybridChunker Issue #119](https://github.com/docling-project/docling-core/issues/119)
- [config.py:28](../api/config.py#L28) - CHUNK_MAX_TOKENS default
- [extractors.py:81-87](../api/ingestion/extractors.py#L81-L87) - HybridChunker initialization

---

## 2. ~~TextExtractor Naming is Misleading~~ [RESOLVED in v0.13.0]

**Issue:** The `TextExtractor` class was named like a specific extractor, but it was actually a **router/coordinator** that delegates to specialized extractors.

**Resolution:** Renamed `TextExtractor` to `ExtractionRouter` in v0.13.0-alpha to clarify its purpose.

**Changes Made:**
- [extractors.py:660](../api/ingestion/extractors.py#L660) - Renamed class to `ExtractionRouter`
- [processing.py:23](../api/ingestion/processing.py#L23) - Updated import
- [processing.py:145](../api/ingestion/processing.py#L145) - Updated instantiation
- [ingestion/__init__.py](../api/ingestion/__init__.py) - Updated exports
- [tests/test_ingestion.py](../tests/test_ingestion.py) - Updated test class

**Status:** ** RESOLVED

---

## 3. ~~Extraction Method Logging Shows Incorrect Method~~ [RESOLVED in v0.13.0]

**Issue:** The extraction method logged in processing output could show the wrong method. For example, a PDF processed with Docling could be logged as `obsidian_graph_rag`.

**Example:**
```
Extraction complete (obsidian_graph_rag): UNIX and Linux System Administration.pdf - 2,870,514 chars extracted
```

**Root Cause:**
The `TextExtractor.last_method` instance variable ([extractors.py:635](../api/ingestion/extractors.py#L635)) persists between file processing calls. If a markdown file sets `last_method = 'obsidian_graph_rag'` and the next file is a PDF, the old value may be displayed even though the PDF actually used Docling.

The method tracking happens at [extractors.py:665](../api/ingestion/extractors.py#L665):
```python
self.last_method = method_map.get(ext, 'unknown')
return self.extractors[ext](file_path)
```

However, the special markdown handling path ([extractors.py:647-648](../api/ingestion/extractors.py#L647-L648)) calls `_extract_markdown_intelligently()` which may set `last_method` differently, and this value can persist.

**Resolution:** Fixed in v0.13.0-alpha by resetting `self.last_method = None` at the start of each `extract()` call.

**Changes Made:**
- [extractors.py:673-674](../api/ingestion/extractors.py#L673-L674) - Added reset line at beginning of `extract()` method:
  ```python
  def extract(self, file_path: Path) -> ExtractionResult:
      """Extract text based on file extension"""
      # Reset last_method to prevent stale values from previous extractions
      self.last_method = None
      # ... rest of method
  ```

**Status:** ** RESOLVED

---

## 4. ~~EPUB Conversion Logs Appear as "Chunk" Stage~~ [RESOLVED in v0.13.0]

**Issue:** EPUB files were logged as going through the "[Chunk]" stage when they actually go through conversion only. The logs showed:

```
[Chunk] The Data Science Design Manual - Steven S Skiena.epub
Converting EPUB to PDF: The Data Science Design Manual - Steven S Skiena.epub
[Chunk] The Data Science Design Manual - Steven S Skiena.epub - no chunks extracted
[Chunk] The Data Science Design Manual - Steven S Skiena.epub - 0 chunks complete in 46.0s (0.0 chunks/s)
```

**Root Cause:**
- EPUBs don't actually get "chunked" - they get **converted** to PDF via Pandoc
- The pipeline coordinator ([pipeline_coordinator.py:117](../api/services/pipeline_coordinator.py#L117)) logs all files as "[Chunk]" regardless of operation type
- EPUB extractor returns empty result ([extractors.py:310](../api/ingestion/extractors.py#L310)) with `method='epub_conversion_only'`
- The converted PDF is saved and will be processed separately by the watcher/startup scan

**Current Impact:**
- **Cosmetic only**: Misleading log messages
- **No functional impact**: EPUB conversion works correctly
- Can confuse users monitoring logs (wondering why EPUBs show 0 chunks)

**Correct Flow:**
1. EPUB → Pandoc → PDF conversion
2. Original EPUB moved to `original/` directory
3. Converted PDF stays in `knowledge_base/`
4. Watcher/startup picks up PDF for actual processing
5. PDF goes through real Chunk → Embed → Store pipeline

**Resolution:** Fixed in v0.13.0-alpha by detecting EPUB files and using "[Convert]" logging instead of "[Chunk]".

**Changes Made:**
- [pipeline_coordinator.py:116-120](../api/services/pipeline_coordinator.py#L116-L120) - Detect EPUB files and set stage name:
  ```python
  # File needs processing - determine stage name based on file type
  # EPUB files are converted to PDF, not chunked
  stage = "Convert" if item.path.suffix.lower() == '.epub' else "Chunk"

  self.progress_logger.log_start(stage, item.path.name)
  # ... rest of processing
  ```

**Status:** ** RESOLVED

---

## 5. API Endpoints Block During Indexing

**Issue:** API endpoints (`/health`, `/search`, `/queue/jobs`) can take 10+ seconds to respond or timeout during heavy indexing operations.

**Example:**
```bash
# During indexing, health check takes >10 seconds
$ time curl http://localhost:8000/health
# ... 10+ second delay ...
{"status":"healthy",...}

real    0m10.234s
```

**Root Cause:**
- FastAPI uses async I/O, but database operations are **synchronous**
- Synchronous database calls in VectorStore/VectorRepository block the event loop
- During heavy indexing (thousands of chunks being stored), the single-threaded event loop is blocked
- All API requests wait for database operations to complete before being served

**Current Impact:**
- **Medium severity**: Endpoints remain functional but very slow during indexing
- Health checks may timeout in monitoring systems
- Users may think the service is unresponsive
- Cannot reliably query progress during large indexing jobs

**Affected Code:**
- [database.py](../api/ingestion/database.py) - VectorStore with synchronous SQLite operations
- [routes.py](../api/routes.py) - All endpoints share the same event loop
- Heavy indexing scenarios (processing hundreds of PDFs/ebooks)

**Why This Happens:**

FastAPI runs on a single async event loop. When you make a synchronous database call:
```python
# This blocks the entire event loop
def store_embeddings(self, chunks):
    conn = sqlite3.connect(self.db_path)  # Blocking I/O
    cursor = conn.cursor()
    cursor.executemany(...)  # Blocking I/O
    conn.commit()  # Blocking I/O
```

All other requests (health checks, searches) must wait for this to finish.

**Ideal Solution:**

Migrate to async database operations using `aiosqlite`:

```python
# Non-blocking async version
async def store_embeddings(self, chunks):
    async with aiosqlite.connect(self.db_path) as conn:
        async with conn.cursor() as cursor:
            await cursor.executemany(...)
            await conn.commit()
```

This allows FastAPI to interleave database operations with API requests, keeping endpoints responsive.

**Alternative Solutions:**

1. **Use run_in_executor** (temporary fix):
   ```python
   loop = asyncio.get_event_loop()
   await loop.run_in_executor(None, self.store_embeddings, chunks)
   ```
   Offloads blocking calls to thread pool, but doesn't solve WAL mode locking issues

2. **Separate read/write connections**:
   - Read-only connection for queries (non-blocking with WAL mode)
   - Write connection for indexing (can still block)
   - Improves read performance but writes still block

3. **Database connection pooling**:
   - Reduces connection overhead
   - Doesn't solve blocking issue

**Current Workaround:**

None required - endpoints remain functional, just slower during indexing. For production deployments with monitoring:

1. Increase health check timeout to 30s
2. Schedule large indexing jobs during off-hours
3. Monitor indexing progress via logs instead of API

**Status:** Known architectural limitation - fix planned for v0.13.0-alpha or v0.14.0-alpha

**Related:**
- [ROADMAP.md #13](ROADMAP.md) - Async Database Migration (planned fix)
- [database.py](../api/ingestion/database.py) - VectorStore implementation
- [routes.py](../api/routes.py) - API endpoints
- [aiosqlite](https://github.com/omnilib/aiosqlite) - Async SQLite library

---

## 6. Test Limitations

### 4.1 API Endpoint Mock Recursion

**Issue:** The `test_delete_document_success` test in [tests/test_api_endpoints.py:410](../tests/test_api_endpoints.py#L410) cannot use Mock objects for `state.core.vector_store` because FastAPI's JSON encoder encounters circular references when serializing Mock objects.

**Error:**
```
RecursionError: maximum recursion depth exceeded in comparison
/usr/local/lib/python3.11/site-packages/fastapi/encoders.py:298: in jsonable_encoder
```

**Root Cause:**
Mock objects have internal attributes that create circular references. When FastAPI tries to serialize the response (which may include state references), it recursively traverses the Mock object structure until hitting the recursion limit.

**Current Status:** Test is marked with `@pytest.mark.skip`

**Ideal Solution:**
Use integration testing approach instead of mocking:
```python
def test_delete_document_success_integration(self, client, tmp_path):
    """Integration test: Actually create and delete a document"""
    # Setup: Add real document to database
    # Action: Call DELETE endpoint
    # Verify: Document removed from database
```

**Workaround:** Skip unit test and rely on manual/integration testing for this endpoint

**Related:**
- [tests/test_api_endpoints.py:410](../tests/test_api_endpoints.py#L410) - Skipped test

---

### 4.2 Database Transaction Tests

**Issue:** Three tests in `TestDatabaseTransactions` class ([tests/test_database.py:587](../tests/test_database.py#L587)) are skipped because they require manual transaction control which conflicts with the auto-commit behavior of the VectorStore implementation.

**Tests Affected:**
- `test_commit_persists_changes`
- `test_rollback_reverts_changes`
- `test_concurrent_reads_work_with_wal_mode`

**Root Cause:**
The VectorStore and VectorRepository implementations use auto-commit for operations. The tests expect to manually call `conn.commit()` and `conn.rollback()`, but the actual implementation commits after each operation.

**Current Status:** Entire `TestDatabaseTransactions` class marked with `@pytest.mark.skip`

**Ideal Solution:**
- Option A: Add explicit transaction context manager to VectorStore for testing:
  ```python
  with store.transaction():
      store.add_document(...)
      # Can test rollback here
  ```
- Option B: Test transaction behavior at integration level with actual concurrent operations
- Option C: Accept that transaction semantics are implicit and tested through regular usage

**Workaround:** Skip unit tests and rely on integration testing to verify data persistence

**Related:**
- [tests/test_database.py:587](../tests/test_database.py#L587) - Skipped test class
- [ingestion/database.py](../api/ingestion/database.py) - VectorStore implementation

---

## Contributing

Found a new issue? Please document it here with:
- Clear description of the problem
- Root cause analysis
- Current impact assessment
- Ideal solution (best case scenario)
- Current workarounds
- Related code/documentation links
