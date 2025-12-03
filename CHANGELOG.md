# Changelog

All notable changes to RAG-KB are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

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
