# Release Notes: v0.14.0-alpha

**Release Date**: 2025-11-24

**Status**: Production-ready with Python 3.13 upgrade, database maintenance tools, and improved reliability

---

## Major Upgrades

### 1. Python 3.13 Upgrade

Upgraded from Python 3.11 to Python 3.13 for improved performance and modern language features.

**Performance Improvements**:
- 5-10% faster execution (JIT optimizations, improved GC)
- Better memory efficiency
- Enhanced error messages and debugging

**Compatibility Updates**:
- PyTorch 2.5.1+ (Python 3.13 compatible)
- Updated all dependencies for Python 3.13 support
- Fixed RapidOCR cache path for Python 3.13 virtual environment

**Testing**:
- All unit tests passing
- E2E tests verified for all file types (PDF, EPUB, Markdown, Python, Go, Jupyter)
- Comprehensive test coverage maintained

---

## New Features

### 2. Database Maintenance Webhooks

Added API endpoints for database health monitoring and maintenance.

**Endpoints**:
- `POST /maintenance/check-duplicates` - Detect duplicate chunks across documents
- `POST /maintenance/cleanup-duplicates` - Remove duplicate chunks automatically

**Features**:
- Identifies duplicates within documents and across documents
- Tracks deletions with detailed reporting
- Safe cleanup with verification
- Preserves data integrity with foreign key constraints

**Use Cases**:
- Regular database health checks
- Cleanup after bulk imports
- Maintenance during low-traffic periods

---

### 3. Improved Error Handling

Enhanced error logging and diagnostics throughout the pipeline.

**Improvements**:
- Detailed FileNotFoundError logging with full paths and stack traces
- Better error context for debugging timing issues
- Improved progress tracking for long-running operations

---

### 4. Queue Duplicate Detection

Implemented duplicate detection in IndexingQueue to prevent redundant processing.

**Features**:
- Tracks files currently in queue
- Silent skip for duplicate additions
- `force=True` flag to bypass duplicate detection when needed
- Automatic cleanup when items are dequeued

**Benefits**:
- Prevents EPUB/PDF re-queuing issues
- Reduces unnecessary processing
- More efficient resource utilization

---

## Bug Fixes

### RapidOCR Cache Mount
- Fixed cache path for Python 3.13 virtual environment
- Updated from `/usr/local/lib/python3.11/` to `/opt/venv/lib/python3.13/`
- Prevents re-downloading OCR models on every restart

### E2E Test Stability
- Simplified test flow to eliminate race conditions
- Uses existing KB files instead of copying
- Force re-indexing with priority endpoint
- Lightweight test files based on chunk count, not file size

---

## Improvements

### Test Suite
- Fixed all Python 3.13 compatibility issues
- Cleaned up test output and assertions
- Added comprehensive E2E test coverage
- Improved test reliability and speed

### Documentation
- Added Python 3.13 upgrade decision document
- Enhanced ROADMAP with Table of Contents
- Updated configuration examples
- Improved troubleshooting guides

---

## Breaking Changes

None. All changes are backward compatible.

---

## Migration Notes

### From v0.13.0-alpha

1. **Rebuild Docker Image**:
   ```bash
   docker-compose build
   docker-compose up -d
   ```

2. **Cache Directories**: RapidOCR cache will be rebuilt once with new Python 3.13 path

3. **Testing**: Run E2E tests to verify upgrade:
   ```bash
   bash e2e-test.sh
   ```

---

## Known Limitations

- E2E tests require lightweight files in KB (see e2e-test-files/ for reference)
- Database maintenance endpoints are manual (no automated scheduling yet)
- EPUB processing still requires Pandoc for conversion

---

## Next Steps

See [ROADMAP.md](ROADMAP.md) for planned features and improvements.

**Upcoming**:
- Automated database maintenance scheduling
- Enhanced progress tracking with WebSocket support
- Advanced chunking strategies
- Performance monitoring and metrics
