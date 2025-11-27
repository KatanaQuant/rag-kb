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

### 2. Orphans Created During Initial Indexing Not Auto-Repaired

**Severity**: LOW (manual workaround)

Orphan files (marked "completed" in progress but missing from documents table) created *during* initial indexing aren't caught by startup self-healing.

**Root Cause**: Startup sanitization runs BEFORE new file indexing begins:
1. Resume incomplete files
2. Repair existing orphans ← runs here
3. Self-healing (empty docs, chunk backfill)
4. Index new files ← orphans created here won't be caught

**Impact**: Orphans from interrupted indexing persist until next restart or manual trigger.

**Workaround**: Call the maintenance API manually after initial indexing completes:
```bash
curl -X POST http://localhost:8000/api/maintenance/reindex-orphaned-files
```

**Planned Fix**: Post-indexing orphan check or periodic background repair.

---

### 4. Embedding Stage Appears Single-Core Bound

**Severity**: LOW (performance investigation needed)

**Observation**: During indexing, the embedding stage uses significantly fewer resources than the chunking stage. Despite `EMBEDDING_WORKERS=2` (default), CPU utilization during embedding is much lower than expected.

**Possible Causes**:
- sentence-transformers model inference may be GIL-bound
- Thread pool not fully utilized due to batching
- I/O bottleneck between chunking queue and embedding workers
- Model loading overhead per worker

**Current Config** (docker-compose.yml):
```
EMBEDDING_WORKERS=2      # Concurrent embedding threads
OMP_NUM_THREADS=2        # OpenMP threads per worker
MKL_NUM_THREADS=2        # MKL threads per worker
```

**Investigation Needed**:
- Profile embedding worker CPU usage during indexing
- Test with higher `EMBEDDING_WORKERS` values (4, 8)
- Measure if batching or queue depth is the bottleneck
- Consider GPU acceleration (v2.0.0 roadmap)

**Workaround**: None currently. Embedding throughput is acceptable but not optimal.

**Planned**: v1.7.x performance profiling or v2.0.0 GPU support.

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

</details>

---

## Contributing

Found a new issue? Document it with:
- Clear description
- Root cause analysis
- Current impact
- Workaround (if any)
- Related code links
