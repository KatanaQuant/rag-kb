# Changelog

All notable changes to RAG-KB are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

---

## [2.2.2] - 2025-12-05

Critical bugfix for hybrid search (FTS5 was completely broken).

### Fixed
- **FTS JOIN bug** - Keyword search returned nothing for most queries
  - Root cause: FTS5 contentless tables don't store UNINDEXED column values
  - `fts.chunk_id` was always NULL, breaking the JOIN condition
  - Fix: Changed JOIN to use `fts.rowid` instead of `fts.chunk_id`
- **FTS INSERT bug** - New chunks weren't searchable via keywords
  - INSERT didn't set `rowid = chunk_id`, causing rowid mismatch
  - Fix: Explicit `INSERT INTO fts_chunks(rowid, chunk_id, content)`
  - Updated: chunk_repository.py, async_repositories.py, rebuild_fts.py
- **Delete cascade** - Deleting documents left orphan embeddings in HNSW
  - v2.2.2-beta commit (8b523cf) fixed the cascade
  - This release includes HNSW health check at startup

### Added
- **HNSW health check** - Detects orphan embeddings at startup (detection only)
- **rebuild_hnsw_index.py** - Fast HNSW rebuild script (~55s)
- **rebuild_fts_inline.py** - FTS rebuild helper script

### Changed (Query Tuning)
- RRF k=60 → k=20 (better top-result differentiation)
- Keyword fetch multiplier 2x → 4x (more BM25 candidates)
- Fixed fetch_k calculation for reranking scenarios

### Validation
- Benchmark: 73.1% accuracy (same %, but results now CORRECT)
- "Tidy First" query now works (was completely broken before)
- Zero orphan embeddings after cleanup

### If You're Affected
If keyword searches aren't working correctly:
```bash
# Rebuild FTS index (inside container or via temp container)
docker exec rag-api python /app/scripts/rebuild_fts_inline.py /app/data/rag.db

# Rebuild HNSW index if orphans exist
docker exec rag-api python /app/scripts/rebuild_hnsw_index.py /app/data/rag.db
```

---

## [2.2.1] - 2025-12-05

Critical bugfix release for HNSW index persistence.

### Fixed
- **HNSW index not persisting** - Documents indexed after v2.2.0-beta upgrade were lost on container restart
  - Root cause 1: vectorlite only saves HNSW index when database connection closes
  - Root cause 2: AsyncVectorStore refresh() triggered garbage collection, overwriting valid index
  - Fix: Added `_flush_hnsw_index()` to force persistence after each document
  - Fix: Keep old connections alive to prevent GC overwrite

### Known Issues
- `_old_connections` list grows unbounded (minor memory leak, ~1 connection per document)
- DELETE API endpoint may not work correctly (async store connection issues)
- Pre-existing orphan data from delete cascade bug (to be fixed in v2.2.2)

### Documentation
- Added detailed postmortem: `docs/postmortem-hnsw-index-not-persisting.md`

### If You're Affected
If you upgraded to v2.2.0-beta and indexed documents that aren't searchable:
```bash
# Force reindex affected documents
curl -X POST "http://localhost:8000/documents/{path}/reindex?force=true"

# Or re-run migration for full rebuild
docker exec rag-api python /app/ingestion/vector_migration.py /app/data/rag.db 1024
```

---

## [2.2.0-beta] - 2025-12-04

Performance release: 200x faster queries with persistent vector index.

### Added
- **Vectorlite HNSW index** - Persistent approximate nearest neighbor search (~10ms queries, was ~2s)
- **Query decomposition v2** - Break compound queries into sub-queries (+5.6% top score)
- **Follow-up suggestions** - `suggestions` field in `/query` response with related queries
- **Confidence scores** - `rerank_score` field in results when reranking enabled
- **Migration script** - `api/ingestion/vector_migration.py` for sqlite-vec to vectorlite migration
- **Migration tests** - Integration tests verifying migration script works correctly
- Benchmark scripts for agentic query testing

### Changed
- **API Response** - `/query` now returns `decomposition` object and `suggestions` array
- **API Request** - `/query` accepts `decompose` parameter (default: true)
- Query cache key now includes `decompose` parameter

### Performance
- Vector search: ~10ms (was ~2s with NumPy brute-force)
- Startup: ~1s index load (persistent HNSW index on disk)
- Query overhead: +81% latency for decomposition (acceptable with vectorlite speed)

### Migration
**Existing users must run migration script** (one-time, ~78s for 59K vectors):
```bash
docker exec rag-api python /app/ingestion/vector_migration.py /app/data/rag.db 1024
```
New installations create vectorlite tables automatically.

---

## [2.1.5-beta] - 2025-12-03

Major version bump due to breaking changes. See Migration Guide in `docs/RELEASES/v2.1.5-beta.md`.

### Breaking Changes
- **Directory rename**: `knowledge_base/` → `kb/`
- **MCP stdio removed**: Only HTTP transport supported

### Added
- Pre-queue validation system (validates before queuing, not after)
- Pipeline architecture refactoring for clearer responsibilities
- Debug logging for malware detection cache operations
- Debug logging for pipeline rejection tracking
- Domain model documentation (`docs/domain/`) - glossary, context map, aggregates

### Changed
- **License**: Changed from Unlicense to CC BY-NC 4.0 (non-commercial use only)

### Improved
- Test skip messages now include paths for easier debugging
- Removed stale BACKLOG entry (test_delete_document_success now passes)

### Fixed
- Pipeline coordinator responsibilities clarified

### Migration
See `docs/RELEASES/v2.1.5-beta.md` for migration guide from v1.9.1.

---

## [1.9.1] - 2025-11-xx

### Added
- MCP HTTP transport support
- `/documents/{path}/reindex` endpoint for force reindexing
- Documentation consolidation

### Changed
- MCP now uses HTTP transport exclusively

---

## [1.7.11] - 2025-11-xx

### Added
- `.go` file support in file watcher
- Performance optimizations

### Fixed
- File watcher now detects Go files

---

## [1.6.7] - 2025-11-xx

### Added
- `POST /api/security/scan/file` endpoint for single-file scanning
- MCP integration guides

### Fixed
- Security validation_action config mismatch (was "warn", now "reject")
- Malware files now correctly rejected and quarantined

---

## [1.6.6] - 2025-11-xx

### Changed
- Code quality improvements - complexity reduction across codebase

---

## [1.6.5] - 2025-11-xx

### Changed
- Codebase refactoring
- CPU-optimized defaults

---

## [1.6.3] - 2025-11-xx

### Removed
- `manage.py` CLI (use REST API instead)

### Fixed
- ClamAV socket contention

---

## [1.6.2] - 2025-11-xx

### Fixed
- N+1 query in completeness API (1300x faster)

---

## [1.6.0] - 2025-11-xx

### Added
- Security REST API with parallel scanning and caching
  - `POST /api/security/scan` - Start background scan
  - `GET /api/security/scan/{job_id}` - Get scan results
  - `GET /api/security/scan` - List all scans
  - `GET /api/security/cache/stats` - Cache statistics
  - `DELETE /api/security/cache` - Clear cache
  - `GET /api/security/rejected` - List rejected files
  - `GET /api/security/quarantine` - List quarantined files
  - `POST /api/security/quarantine/restore` - Restore file
  - `POST /api/security/quarantine/purge` - Purge old files
- Parallel scanning with ThreadPoolExecutor (~100x faster)
- Scan result caching by file hash

### Changed
- Malware detection enabled by default

---

## [1.5.0] - 2025-11-xx

### Added
- Advanced malware detection (ClamAV, YARA, hash blacklist)

---

## [1.4.0] - 2025-11-xx

### Added
- Quarantine system for dangerous files

---

## [1.3.0] - 2025-11-xx

### Added
- Rejection tracking for validation failures

---

## [1.2.0] - 2025-11-xx

### Added
- Anti-malware security validation

---

## [1.1.0] - 2025-11-xx

### Added
- Document completeness verification
- PDF integrity validation

---

## [1.0.0] - 2025-xx-xx

### Added
- Production-ready RAG knowledge base
- Async database operations
- Code quality audit and refactoring

---

## Pre-1.0 Releases

See git history for alpha releases (v0.x.x).
