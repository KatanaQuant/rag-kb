# RAG-KB v0.11.0-alpha Release Notes

Release Date: 2025-11-21

## Overview

This release brings significant improvements in performance, architecture, and language support. Key highlights include 4x faster processing through concurrent pipelines, Go language support for code indexing, and major code quality improvements following industry best practices.

## Major Features

### 1. Concurrent Processing Pipeline

Implemented a 3-stage concurrent pipeline for document processing:
- **ChunkWorker**: Extracts text and chunks documents
- **EmbedWorkerPool**: Parallel embedding workers (configurable, default: 3 workers)
- **StoreWorker**: Database persistence

**Benefits**:
- 4x throughput improvement for large document queues
- Non-blocking extraction and chunking
- Configurable parallelism via `EMBED_WORKERS` environment variable

**Architecture**:
```
IndexingQueue (Priority) → IndexingWorker → PipelineCoordinator
                                              ↓
                                      ChunkWorker (1 thread)
                                              ↓
                                      EmbedWorkerPool (3 threads)
                                              ↓
                                      StoreWorker (1 thread)
```

### 2. Go Language Support

**Complete Go Code Indexing**
- AST-based chunking using tree-sitter for Go source files
- Intelligent function, method, and type extraction
- Full test coverage with 4/4 tests passing
- Proper file filtering for Go projects (vendor/, go.mod, binaries)

**Go-Specific Features:**
- Filters `vendor/` directory (equivalent to `node_modules`)
- Excludes `go.mod`, `go.sum`, `go.work`, `go.work.sum`
- Excludes compiled binaries (`*.exe`)
- Excludes certificate files (`*.pem`, `*.key`, `*.crt`)
- Supports package, function, method, type, const, var, and import declarations

### 3. Modular Architecture

**main.py Refactoring**
- Reduced main.py from 1246 lines to 530 lines (57% reduction)
- Extracted 9 classes into dedicated service modules
- Improved separation of concerns
- Better testability through dependency injection

**New Directory Structure:**
- `api/api_services/` - Application service layer (9 modules)
- `api/startup/` - Application startup and lifecycle management
- `api/routes/` - Route handlers (prepared for future extraction)

**Extracted Modules:**
- `ModelLoader` → `api_services/model_loader.py`
- `FileWalker` → `api_services/file_walker.py`
- `DocumentIndexer` → `api_services/document_indexer.py`
- `IndexOrchestrator` → `api_services/index_orchestrator.py`
- `QueryExecutor` → `api_services/query_executor.py`
- `OrphanDetector` → `api_services/orphan_detector.py`
- `DocumentLister` → `api_services/document_lister.py`
- `DocumentSearcher` → `api_services/document_searcher.py`
- `StartupManager` → `startup/manager.py`

### 4. Priority-Based Queue System

- HIGH priority for orphan repair and data integrity
- NORMAL priority for new file indexing
- Ensures critical files process first
- Queue management API endpoints for monitoring

### 5. Sanitization Stage

Pre-indexing validation and cleanup:
- Orphan detection and automatic repair
- File hash validation
- Automatic recovery from inconsistent states
- Runs before background indexing starts

### 6. Enhanced Queue Management API

**New Endpoints**:

**GET `/queue/jobs`** - Monitor queue and worker status
```json
{
  "queue_sizes": {
    "chunk": 1546,
    "embed": 10,
    "store": 0
  },
  "active_jobs": {
    "chunk": "document.pdf",
    "embed": ["doc1.md", "doc2.md", "doc3.md"],
    "store": null
  },
  "workers_running": {
    "chunk": true,
    "embed": true,
    "store": true
  }
}
```

**POST `/indexing/pause`** - Pause queue processing
**POST `/indexing/resume`** - Resume queue processing
**POST `/indexing/clear`** - Clear pending queue
**POST `/orphans/repair`** - Queue orphaned files for reindexing

## Performance Improvements

### Throughput
- **Before**: ~2 files/hour for large PDFs (sequential processing)
- **After**: ~8 files/hour (4x improvement with 3 embedding workers)

### Resource Utilization
- Better CPU utilization with parallel embedding
- Non-blocking extraction allows continuous file processing
- Queue-based throttling prevents memory exhaustion

## Configuration

### New Environment Variables

```bash
# Concurrent processing
CHUNK_WORKERS=1          # Number of parallel chunking threads (default: 1)
EMBED_WORKERS=3          # Number of parallel embedding threads (default: 3)

# Model configuration
EMBEDDING_MODEL=Snowflake/snowflake-arctic-embed-l
EMBEDDING_DIMENSION=1024
```

**Performance Notes:**
- Set `CHUNK_WORKERS=2` if processing many large PDFs with OCR
- Single chunk worker prevents resource contention but may bottleneck on slow files
- Multiple chunk workers split CPU resources but process files in parallel

## Pipeline Improvements

**Better Logging**
- Fixed misleading `[Chunk]` label for already-indexed files
- Now correctly uses `[Skip]` label when files are skipped
- Improved pipeline stage visibility

**Smarter File Persistence**
- Files that fail extraction (0 chunks) are no longer marked as "processed"
- Allows automatic pickup when support is added for new file types
- Reduces false positives in the "already indexed" logic

## Bug Fixes

- Fixed Go files showing as "Unsupported" despite having GoChunker
- Fixed certificate files (`.pem`, `.key`, `.crt`) being indexed
- Fixed pipeline logging confusion between skipped and chunked files
- Fixed file persistence for unsupported file types
- Fixed orphan repair bypass of queue system
- Corrected pipeline stage naming for clarity
- Fixed FileHasher import issues
- Resolved queue reference issues in endpoint handlers
- Improved worker monitoring visibility

## Testing

- All existing tests remain passing
- New Go language support tests: 4/4 passing
- Pipeline logging tests: 3/3 passing
- File filter tests: 24/24 passing (including 5 new Go tests)

## Breaking Changes

None. All changes are backward compatible.

## Known Issues

1. Test suite requires pytest installation in Docker
2. Some repository classes have high method counts (acceptable for CRUD operations)

## Migration Guide

### From v0.10.1-alpha

No migration required. The concurrent pipeline activates automatically with existing configuration.

### Optional Tuning

Adjust concurrent workers based on CPU cores:
```bash
# For 8-core machine
EMBED_WORKERS=6

# For 4-core machine
EMBED_WORKERS=3
```

### For Developers

- Imports from `main.py` classes now come from `api_services.*` or `startup.manager`
- Main application logic unchanged, only reorganized

## Compatibility

- Python 3.8+
- No new dependencies added
- Existing configuration unchanged
- Docker image compatible

## Next Steps

Future releases will focus on:
- Further extraction of route handlers into dedicated router modules
- Breaking up large extractor classes (EpubExtractor at 291 lines)
- Additional language support (Rust, C++, etc.)
- Performance optimizations in concurrent pipeline

---

For questions or issues, please open a GitHub issue.
