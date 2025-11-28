# Known Issues

Active issues and limitations in RAG-KB. Resolved issues are archived at the bottom.

---

## Active Issues

---

### 1. GIL Contention with Multiple Embedding Workers

**Severity**: LOW (architectural limitation)

**Observation**: Multiple embedding workers (`EMBEDDING_WORKERS > 1`) don't scale linearly because Python's GIL serializes CPU-bound model inference.

**Root Cause**: Embedding workers use `threading.Thread`, not `multiprocessing.Process`. All threads share the GIL, so only one can execute model inference at a time.

**Mitigation Applied (v1.7.0)**: Implemented `BatchEncoder` class for batch encoding - processes multiple chunks per model.encode() call instead of one-at-a-time. This reduces forward pass overhead by 10-50x for large documents. Also fixed EMBEDDING_WORKERS default from 3→2 in all locations.

**Remaining Limitation**: GIL contention still limits multi-worker parallelism. True parallel embedding requires:
- GPU acceleration (v2.0.0 roadmap) - See [internal_planning/GPU_INFRASTRUCTURE.md](../internal_planning/GPU_INFRASTRUCTURE.md)
- Go worker coordinator with Python ML subprocesses - See [internal_planning/PERFORMANCE_OPTIMIZATION.md](../internal_planning/PERFORMANCE_OPTIMIZATION.md)

**Current Config** (docker-compose.yml):
```
EMBEDDING_WORKERS=2      # Concurrent embedding threads
EMBEDDING_BATCH_SIZE=32  # Chunks per batch (new in v1.7.0)
```

**Related**: [ROADMAP.md - v2.0.0 GPU Support](ROADMAP.md#v200---gpu--advanced-features)

---

### 2. Pipeline Queue Architecture Issues

**Severity**: MEDIUM (causes duplicate processing, inefficient queuing)

#### 2.1 ~~Duplicate Processing of In-Progress Files~~ [FIXED v1.7.3]

`IndexingQueue.add()` now ALWAYS checks `queued_files` set, regardless of `force` flag.
The `force` flag only affects reindexing behavior, not queue deduplication.

#### 2.2 ~~Missing Pre-Stage Skip Check~~ [FIXED v1.7.3]

`PipelineCoordinator.add_file()` now checks `is_document_indexed()` BEFORE adding to chunk_queue.
Only files needing processing enter the queue. Already-indexed files are filtered out immediately.

#### 2.3 ~~Queue Worker Verification Needed~~ [VERIFIED v1.7.3]

Tests confirm workers operate independently:
- Chunk, embed, store workers don't block each other
- Security scans use separate thread pool (not pipeline queues)
- Errors in one worker don't crash others

#### 2.4 ~~Queue Dedup Race Condition~~ [FIXED v1.7.4]

Files were removed from `queued_files` tracking when dequeued via `get()`. This allowed duplicate
watcher events (e.g., `on_created` + `on_modified` during file copy) to re-queue files that were
still being processed, causing duplicate entries in chunk/embed queues.

Fixed by:
- `get()` no longer removes from tracking set
- Added `mark_complete(path)` method called after pipeline completion
- All pipeline exit points (success, skip, error) now call `mark_complete()`

---

### 3. Low Boundary Coherence for Certain File Types

**Severity**: LOW (quality improvement opportunity)

**Observation**: Baseline chunking metrics (v1.7.8) show significant variation in boundary coherence by file type:

| File Type | Coherence | Notes |
|-----------|-----------|-------|
| .go | 96.1% | AST-based chunking works well |
| .js | 87.5% | TreeSitter chunking works well |
| .ipynb | 84.0% | Unified HybridChunker (v1.7.10) |
| .pdf | 65.9% | HybridChunker handles structure |
| .py | 49.1% | AST chunking, room for improvement |
| .md | 41.8% | Uses HybridChunker (v1.7.2+), needs reindex |

**Root Cause**:
- **.md files**: Already use Docling HybridChunker since v1.7.2, but older indexed files may use previous SemanticChunker. Reindex required.
- **.ipynb files**: ~~Cell-by-cell AST approach was fragmenting notebooks.~~ Fixed in v1.7.10 - notebooks now converted to markdown then chunked with unified HybridChunker. Coherence improved from 17.5% to 84.0%.

**Action Items**:
- [ ] **Reindex .md files** - Must be explicitly requested by user. Will pick up HybridChunker for all markdown files.
- [x] **Improve .ipynb chunking** - Fixed in v1.7.10. Unified HybridChunker approach (84% coherence).
- [x] **Reindex .ipynb files** - Completed in v1.7.10. 6 notebooks reindexed with new approach.

**Future Improvement (v2.0.0 GPU)**:
- **Embedding-based semantic chunking**: Split into units, compute embeddings, measure cosine similarity between consecutive units, start new chunk when similarity drops (semantic boundary detected). This produces truly semantic chunks where content is coherent within each chunk.
- Agentic chunking (LLM-based semantic splitting) could further improve coherence but requires GPU for acceptable performance.
- See [internal_planning/CHUNKING_STRATEGY_EVALUATION.md](../internal_planning/CHUNKING_STRATEGY_EVALUATION.md) for detailed analysis

**Measurement**: Run `python -m evaluation.baseline_report --db-path data/rag.db` to regenerate baseline.

**Related**: [ROADMAP.md - v2.0.0 Semantic Chunking](ROADMAP.md#embedding-based-semantic-chunking)

---

### 4. EPUB Orphan Detection False Positive

**Severity**: LOW (cosmetic logging issue)

**Observation**: During startup orphan checks, converted EPUBs are detected as orphans and logged, even though they're handled correctly.

**Example Log**:
```
Found 1 orphaned files (processed but not embedded)
Sample orphaned files:
  - Tidy First - Kent Beck.epub (2025-11-28T17:21:24.008853+00:00)
Repairing orphaned files...
Converted EPUBs cleaned: 1
Orphan repair complete: 0 files queued for reindexing
```

**Root Cause**: EPUB conversion workflow creates expected orphans:
1. EPUB is processed (creates progress entry)
2. EPUB is converted to PDF (0 chunks extracted from EPUB)
3. EPUB moved to `original/` subdirectory
4. PDF is indexed separately (has chunks)
5. EPUB progress entry remains (0 chunks) → flagged as orphan

**Current Behavior**: OrphanDetector correctly identifies and cleans these (`_is_converted_epub()` check) but logs them as "orphaned" first, which is confusing.

**Mitigation**: The orphan is **correctly handled** - progress entry is deleted, file is not re-queued. The EPUB workflow is working as designed (convert → move → index PDF).

**Impact**: None (cosmetic only). The log message is misleading but the behavior is correct.

**Future Improvement**: Pre-filter converted EPUBs before orphan detection to avoid confusing logs.

---

### 5. Test Limitations

#### 5.1 API Endpoint Mock Recursion
Test `test_delete_document_success` is skipped - FastAPI's JSON encoder hits recursion errors with Mock objects.

**Status**: Skipped, relies on integration testing

#### 5.2 Database Transaction Tests
`TestDatabaseTransactions` class skipped - VectorStore uses auto-commit, tests expect manual transaction control.

**Status**: Skipped, transaction behavior tested implicitly

---

## Resolved Issues

<details>
<summary>Click to expand resolved issues</summary>

### TextExtractor Naming [RESOLVED v0.13.0]
Renamed `TextExtractor` to `ExtractionRouter` to clarify its router/coordinator role.

### Extraction Method Logging [RESOLVED v0.13.0]
Fixed `last_method` persistence between file processing - now resets at start of each `extract()` call.

### EPUB Conversion Logs [RESOLVED v0.13.0]
EPUB files now show "[Convert]" instead of misleading "[Chunk]" in logs.

### API Endpoints Block During Indexing [RESOLVED v0.16.0]
Migrated to hybrid async/sync database architecture. API responds <100ms during heavy indexing.

### File Watcher Re-queues [RESOLVED v0.13.1]
IndexingQueue now has duplicate detection - prevents re-queuing files already in pipeline.

### PDF Integrity Validation [RESOLVED v1.1.0]
PDF integrity validation detects empty files, missing headers, truncation, corrupt xref tables.

### Integrity API N+1 Query [RESOLVED v1.6.2]
`/documents/integrity` (formerly `/documents/completeness`) was slow (~3 min for 1300 docs) due to N+1 query pattern.
Fixed with batch preloading - now completes in <1 sec.

### ClamAV Socket Contention [RESOLVED v1.6.3]
Parallel security scanning (8 workers) produced "Bad file descriptor" errors in logs when multiple threads hit the ClamAV socket simultaneously.
Fixed with thread-local ClamAV connections - each worker gets its own socket connection.

### Confusing Directory Structure [RESOLVED v1.6.5]
`services/` and `api_services/` naming was unclear. Duplicate classes existed across routes and service layers.
Fixed by renaming: `services/`→`pipeline/` (background processing), `api_services/`→`operations/` (API operations).
Removed duplicate classes from routes (now import from operations layer).

### Security Validation Config Mismatch [RESOLVED v1.6.7]
`validation_action` config in environment_config_loader.py used "warn" instead of "reject" as default.
This caused malware files to be logged but not quarantined/rejected during indexing.
Fixed by correcting the default to match the intended behavior from v1.5.0.

### File Move UNIQUE Constraint Failure [RESOLVED v1.7.0]
When files were moved in the knowledge base, path updates failed with "UNIQUE constraint failed: documents.file_path"
if the destination path already existed in the database (e.g., duplicate content detected at new location).
Fixed by checking if destination path exists before update - if so, deletes stale source record instead of updating.

### Orphans During Initial Indexing Not Auto-Repaired [RESOLVED v1.7.1]
Orphan files created *during* initial indexing weren't caught by startup sanitization (which runs before indexing).
Fixed by adding post-indexing orphan check in `_background_indexing_task()`.

### EPUB Conversion Misleading Logs [RESOLVED v1.7.1]
EPUB conversions logged "no chunks extracted" and "0 chunks complete" which was misleading.
EPUBs are converted to PDF (no chunks expected) - the PDF is processed separately.
Fixed by detecting Convert stage and logging "conversion complete, PDF queued for indexing".

### Obsidian SemanticChunker Oversized Chunks [RESOLVED v1.7.2]
Obsidian markdown files were using a custom `SemanticChunker` that didn't split very long single lines.
Files with minified content, base64 data, or extremely long paragraphs (252K+ chars on one line) created
chunks exceeding 60K tokens - far beyond the model's 8192 token limit.
Root cause: SemanticChunker only split on headers and `\n`, not on character/token limits within lines.
Fixed by switching Obsidian extraction to use Docling's HybridChunker (same as PDF/DOCX).

### JavaScript/TSX File Extraction Failure [RESOLVED v1.7.6]
JavaScript (.js), TSX (.tsx), and JSX (.jsx) files failed during extraction with "Unsupported Programming Language".
Root cause: `astchunk` library only supports Python, Java, and TypeScript - not JavaScript/TSX/JSX.
Fixed by routing these languages to `TreeSitterChunker` (which uses `tree-sitter-language-pack`), similar to Go.
JSX files are parsed using the JavaScript parser (which handles JSX syntax).

</details>

---

## Contributing

Found a new issue? Document it with:
- Clear description
- Root cause analysis
- Current impact
- Workaround (if any)
- Related code links
