# Known Issues

Active issues and limitations in RAG-KB. Resolved issues are archived at the bottom.

---

## Active Issues

### 1. HybridChunker Can Exceed Model's Max Sequence Length

**Severity**: LOW (auto-handled)

Docling's HybridChunker with `merge_peers=True` can create chunks exceeding the embedding model's max sequence length (8192 tokens).

**Impact**: Minimal - sentence-transformers auto-truncates (~10-40 chars lost per affected chunk)

**Workaround**: Accept auto-truncation (recommended) or set `CHUNK_MAX_TOKENS=6000`

**Root Cause**: [docling-core#119](https://github.com/docling-project/docling-core/issues/119) - HybridChunker doesn't strictly enforce max_tokens when merging.

---

### 2. Test Limitations

#### 2.1 API Endpoint Mock Recursion
Test `test_delete_document_success` is skipped - FastAPI's JSON encoder hits recursion errors with Mock objects.

**Status**: Skipped, relies on integration testing

#### 2.2 Database Transaction Tests
`TestDatabaseTransactions` class skipped - VectorStore uses auto-commit, tests expect manual transaction control.

**Status**: Skipped, transaction behavior tested implicitly

---

### 3. ClamAV Socket Contention

**Severity**: LOW (cosmetic)

Parallel security scanning (8 workers) can produce "Bad file descriptor" errors in logs when multiple threads hit the ClamAV socket simultaneously.

**Impact**: Cosmetic only - scans complete successfully, just noisy logs

**Workaround**: None needed - errors are benign

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

### Completeness API N+1 Query [RESOLVED v1.6.2]
`/documents/completeness` was slow (~3 min for 1300 docs) due to N+1 query pattern.
Fixed with batch preloading - now completes in <1 sec.

</details>

---

## Contributing

Found a new issue? Document it with:
- Clear description
- Root cause analysis
- Current impact
- Workaround (if any)
- Related code links
