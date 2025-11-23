# Release Notes: v0.13.0-alpha

**Release Date**: 2025-11-23

**Status**: Production-ready with Docker build optimization, structured progress logging, and bug fixes

---

## New Features

### 1. Docker Build Optimization

Significantly faster Docker builds with multi-stage builds and BuildKit cache mounts.

**Performance Improvements**:
- Rebuild time: 60% faster (7-10 min → 2-4 min)
- Image size: 40-60% smaller (~3.5 GB → ~2.0-2.5 GB)
- More secure runtime (no build tools in final image)

**Implementation**:
- Multi-stage Dockerfile (builder + runtime stages)
- BuildKit cache mounts for apt and pip
- Optimized .dockerignore to reduce build context
- Image tagging in docker-compose.yml for cache reuse

**Benefits**:
- Faster iteration during development
- Smaller production images
- Reduced storage and bandwidth requirements
- Security improvement (minimal attack surface)

---

### 2. Structured Progress Logging

Real-time progress tracking across all pipeline stages with comprehensive timing and rate metrics.

**Output Format**:
```
[Chunk] document.pdf
[Embed] document.pdf | 50/100 (50%) | 12.3s elapsed | 4.1 chunks/s | ETA: 12.2s
[Store] document.pdf - 100 chunks complete in 25.4s (3.9 chunks/s)
```

**Features**:
- Time tracking with elapsed time and ETA calculation
- Processing rate (chunks/second) for all stages
- Document name and stage clearly labeled
- Progress percentage for embedding stage
- Consistent format across all logs

**Benefits**:
- Monitor long-running indexing operations in real-time
- Identify bottlenecks and performance issues
- Better visibility into system activity
- Easier troubleshooting and debugging

---

### 3. Periodic Heartbeat for Long-Running Operations

Background thread-based heartbeat provides progress updates during long-running Docling chunking operations where real-time progress is not available.

**Output Format**:
```
[Chunk] large-book.pdf
[Chunk] large-book.pdf - processing... 60s elapsed
[Chunk] large-book.pdf - processing... 120s elapsed
[Chunk] large-book.pdf - 2932 chunks complete in 10774.0s (0.3 chunks/s)
```

**Features**:
- 60-second interval updates during chunking
- Daemon threads for non-blocking operation
- Clean thread shutdown on completion
- Prevents orphaned threads

**Use Cases**:
- Large PDFs (100+ pages) taking hours to process
- Technical books with complex layouts
- Multi-hundred page ebooks

---

## Bug Fixes

### 1. Extraction Method Logging Fixed

**Problem**: The extraction method logged in processing output could show the wrong method due to stale state from previous file processing.

**Fix**: Reset `self.last_method = None` at the start of each `extract()` call in ExtractionRouter.

**Impact**: Logs now accurately reflect the extraction method used for each file.

---

### 2. EPUB Conversion Logging Fixed

**Problem**: EPUB files were logged as going through the "[Chunk]" stage when they actually go through conversion only.

**Fix**: Detect EPUB files and use "[Convert]" logging instead of "[Chunk]".

**Impact**: Logs now correctly show EPUB conversion process, reducing user confusion.

---

### 3. EPUB "Too Deeply Nested" LaTeX Error

**Problem**: EPUB files with excessive list nesting (>4-6 levels) failed conversion with LaTeX "Too deeply nested" error.

**Fix**: Expanded error detection to recognize deeply nested errors and automatically fall back to HTML conversion.

**Impact**: Fixes EPUB conversion for technical books with complex nested structures.

---

### 4. Orphaned Heartbeat Threads

Fixed two critical bugs where heartbeat threads would continue running indefinitely after files completed processing.

**Bug 1: Threads persist when new file starts**
- Problem: When a new file started processing in the same stage, old heartbeat thread kept running
- Fix: Stop all stage heartbeats before starting new ones (only one file per stage processes at a time)

**Bug 2: Threads persist for files with 0 chunks**
- Problem: Files producing no chunks (unsupported formats) left heartbeat threads running forever
- Fix: Call log_complete() with 0 chunks before early return to ensure cleanup

**Verification**: Added 4 comprehensive tests for thread lifecycle management.

---

## Improvements

### Code Refactoring

**ExtractionRouter Rename**: Renamed `TextExtractor` to `ExtractionRouter` to better reflect its purpose as a router/coordinator that delegates to specialized extractors.

**Files Changed**:
- api/ingestion/extractors.py - Class renamed
- api/ingestion/processing.py - Updated import
- api/ingestion/__init__.py - Updated exports
- tests/test_ingestion.py - Updated test class

**Impact**: Improved code clarity and semantic meaning.

---

### Documentation

- Added comprehensive Docker build instructions in README.md and QUICK_START.md
- Updated ROADMAP.md with v1.0.0 release plan
- Created V1_RELEASE_PLAN.md in internal_planning/ with detailed timeline
- Updated KNOWN_ISSUES.md marking 3 issues as resolved
- Added blue-green deployment guide (DEVELOPMENT.md)

---

### Code Quality

- Following POODR principles throughout (Single Responsibility, Dependency Injection)
- Test-Driven Development approach for all new features
- 13 new tests for progress logging functionality
- All tests passing

---

## Technical Details

### Multi-Stage Docker Build

The Dockerfile now uses two stages:

**Stage 1: Builder**
- Python 3.11 slim base
- Installs build dependencies (gcc, g++, make)
- Creates virtual environment
- Compiles Python packages with pip cache mount
- BuildKit cache significantly speeds up rebuilds

**Stage 2: Runtime**
- Python 3.11 slim base
- Installs only runtime dependencies (no build tools)
- Copies compiled packages from builder stage
- Runs as non-root user (appuser)
- Minimal attack surface

**BuildKit Cache Mounts**:
- `/var/cache/apt` - apt package cache
- `/var/lib/apt` - apt database cache
- `/root/.cache/pip` - pip package cache

---

### ProgressLogger Class

```python
class ProgressLogger:
    """Logs progress with timing and context for pipeline stages"""

    def log_start(stage: str, document: str)
    def log_progress(stage: str, document: str, current: int, total: int)
    def log_complete(stage: str, document: str, total: int)
    def start_heartbeat(stage: str, document: str, interval: int = 60)
```

**Key Features**:
- Independent time tracking per document
- Rate calculation (items/elapsed time)
- ETA estimation (remaining / rate)
- Thread-safe heartbeat management
- Automatic cleanup on completion

---

### Pipeline Integration

**Chunk Stage**:
- Start logging at beginning
- Periodic heartbeat every 60 seconds
- Completion logging with final stats

**Embed Stage**:
- Progress updates every 5 chunks
- Shows current/total, percentage, rate, ETA

**Store Stage**:
- Start and completion logging
- Final storage metrics

---

## Known Issues

No new known issues introduced in this release. See [KNOWN_ISSUES.md](KNOWN_ISSUES.md) for existing limitations.

**Resolved in this release**:
- Extraction method logging shows incorrect method (FIXED)
- EPUB conversion logs appear as [Chunk] stage (FIXED)
- TextExtractor naming is misleading (FIXED - renamed to ExtractionRouter)

**Notable existing issues**:
- HybridChunker can exceed model's max sequence length (minimal impact, auto-truncated)
- API endpoints block during heavy indexing (architectural limitation, fix planned for v0.14.0)

---

## Migration Notes

### From v0.12.0-alpha

No breaking changes. This is a minor release with new features and bug fixes.

**Docker Rebuild Required**: Yes (for optimizations and bug fixes)

```bash
# Enable BuildKit for faster builds (recommended)
export DOCKER_BUILDKIT=1

# Rebuild with BuildKit cache support
docker-compose down
docker-compose build
docker-compose up -d
```

**No Configuration Changes**: All new features work automatically with existing configuration.

---

## Statistics

- **Commits**: Consolidated release
- **Files Changed**: 12 files modified, 1 new file (.dockerignore)
- **New Files**: progress_logger.py, test_progress_logger.py, .dockerignore, V1_RELEASE_PLAN.md
- **Tests Added**: 13 new tests for progress logging
- **Documentation**: Multiple updates (README, QUICK_START, ROADMAP, KNOWN_ISSUES, DEVELOPMENT)

---

## Next Release

**v0.14.0-alpha** (Target: 4-8 weeks)
- Async database migration (fix API blocking during indexing)
- Notion export support
- ClamAV malware scanning
- Chunking strategy evaluation

See [ROADMAP.md](ROADMAP.md) for full roadmap and v1.0.0 release plan.

---

## Links

- **Repository**: https://github.com/KatanaQuant/rag-kb
- **Issues**: https://github.com/KatanaQuant/rag-kb/issues
- **Email**: horoshi@katanaquant.com
