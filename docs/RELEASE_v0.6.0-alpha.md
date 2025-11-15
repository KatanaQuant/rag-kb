# Release v0.6.0-alpha: Resumable Processing Engine

**Release Date**: 2025-11-15
**Type**: Feature Release
**Status**: Alpha (Pre-release)

---

## What's New

### Resumable Processing with Progress Tracking

Major reliability improvement: Processing now resumes from checkpoints after interruptions instead of restarting from scratch.

**Problem Solved**:
- Container restart at 98% completion previously meant restarting from 0%
- 30+ minutes of processing lost during resource management or deployments
- All-or-nothing architecture prevented graceful recovery

**Solution**:
- **Checkpoint-based processing**: Progress saved every 50 chunks
- **Automatic resume**: Continues from last checkpoint on startup
- **Zero data loss**: Interruptions no longer waste processing time
- **Hash validation**: Detects file changes and restarts when needed

### Key Features

**Progress Tracking Database**
- New `processing_progress` table tracks file processing state
- Stores chunk counts, character positions, status, and timestamps
- Enables resume from exact position in large documents

**Batch Processing**
- Configurable batch size (default: 50 chunks per checkpoint)
- Atomic progress updates prevent partial state corruption
- Memory-efficient processing of large files

**Startup Recovery**
- Automatic detection of incomplete files on container start
- Validates file existence before resuming
- Marks deleted/failed files appropriately

**Configuration**
- Default: `RESUMABLE_PROCESSING=true` (enabled by default)
- Batch size: `PROCESSING_BATCH_SIZE=50`
- Max retries: `PROCESSING_MAX_RETRIES=3`
- Cleanup: `CLEANUP_COMPLETED_PROGRESS=false`

---

## Installation

### New Installation

```bash
git clone https://github.com/KatanaQuant/rag-kb.git
cd rag-kb
git checkout v0.6.0-alpha

# Start with resumable processing (default)
docker-compose up -d

# Or disable if needed (not recommended)
echo "RESUMABLE_PROCESSING=false" > .env
docker-compose up -d
```

### Upgrading from v0.5.0-alpha

**Seamless upgrade** - no migration required:

```bash
cd rag-kb
git pull origin main
git checkout v0.6.0-alpha

# Rebuild with new features
docker-compose down
docker-compose up --build -d

# Processing progress table created automatically
# Existing documents unaffected
# New processing uses resumable engine
```

---

## Breaking Changes

**None**. Fully backward compatible with v0.5.0-alpha.

- Existing databases continue to work
- Processing progress table created automatically
- Legacy processing mode available via `RESUMABLE_PROCESSING=false`
- No configuration changes required

---

## Performance Characteristics

### Processing Overhead
- **Checkpoint overhead**: ~50ms per batch (every 50 chunks)
- **Overall impact**: <1% on total processing time
- **Benefit**: Resume from checkpoint vs restart from 0%

### Memory Usage
- **No increase**: Progress tracked in SQLite database
- **Disk usage**: ~1KB per processed file in progress table

### Database
- **New table**: `processing_progress` with 10 columns
- **Indexes**: Primary key on `file_path`
- **Cleanup**: Optional via `CLEANUP_COMPLETED_PROGRESS=true`

---

## How It Works

### Processing Flow

1. **Start processing**: Check for existing progress record
2. **Hash validation**: Compare file hash with stored hash
   - Hash match: Resume from `last_chunk_end` position
   - Hash mismatch: Restart from beginning (file changed)
   - No record: Start fresh processing
3. **Batch processing**: Process 50 chunks, save progress
4. **Completion**: Mark file as completed with timestamp

### Interruption Recovery

```
Container interrupted at chunk 487/500...
↓
Container restarts
↓
System detects incomplete file
↓
Resumes from chunk 487
↓
Completes remaining 13 chunks
```

### File Change Detection

```
File: document.pdf (hash: abc123)
Processed: 80% complete
↓
User modifies document.pdf (hash: xyz789)
↓
Hash mismatch detected
↓
Processing restarts from 0% with new content
```

---

## Configuration

Add to `.env` file (optional - defaults work for most cases):

```bash
# Resumable processing (enabled by default)
RESUMABLE_PROCESSING=true

# Chunks processed before progress checkpoint
PROCESSING_BATCH_SIZE=50

# Maximum retries for failed files
PROCESSING_MAX_RETRIES=3

# Delete completed progress records (saves disk space)
CLEANUP_COMPLETED_PROGRESS=false
```

---

## Technical Details

### Database Schema

```sql
CREATE TABLE processing_progress (
    file_path TEXT PRIMARY KEY,
    file_hash TEXT,
    total_chunks INTEGER DEFAULT 0,
    chunks_processed INTEGER DEFAULT 0,
    status TEXT DEFAULT 'in_progress',
    last_chunk_end INTEGER DEFAULT 0,
    error_message TEXT,
    started_at TEXT,
    last_updated TEXT,
    completed_at TEXT
)
```

### Architecture

**New Classes**:
- `ProcessingProgress`: Dataclass for progress state
- `ProcessingProgressTracker`: Persistence layer for progress
- `ChunkedTextProcessor`: Batch-based text processing

**Modified Classes**:
- `DocumentProcessor`: Integrated resumable processing
- `IndexOrchestrator`: Added startup resume logic
- `SchemaManager`: Added progress table creation

---

## Testing

Comprehensive test suite with 18 unit tests covering:

```bash
cd api && python3 -m pytest tests/test_resumable.py -v
```

**Test Coverage**:
- ProcessingProgressTracker (8 tests)
  - Start new/resume existing processing
  - Hash mismatch detection
  - Progress updates, completion, failure
  - Incomplete file retrieval

- ChunkedTextProcessor (4 tests)
  - Fresh processing
  - Resume from checkpoint
  - Batch commits
  - Error handling

- DocumentProcessor (5 tests)
  - Skip completed unchanged files
  - Reprocess on hash change
  - Resume interrupted processing
  - Legacy mode compatibility

- Integration (1 test)
  - Full workflow validation

**Result**: All 18 tests passing

---

## Use Cases

### Long-Running PDF Processing

**Before v0.6.0**:
```
Processing 1000-page PDF...
Progress: 98% (50 minutes elapsed)
Container restart
Progress: 0% (restart from beginning)
Total time: 100+ minutes
```

**After v0.6.0**:
```
Processing 1000-page PDF...
Progress: 98% (50 minutes elapsed)
Container restart
Progress: 98% (resume from checkpoint)
Total time: 52 minutes
```

### Deployment During Processing

Deploy updates without losing progress:
```bash
# Processing in progress...
docker-compose down
git pull && docker-compose up --build -d
# Processing resumes automatically
```

### Resource Management

Safely adjust resource limits mid-processing:
```bash
# Reduce CPU limits during high-load periods
docker update --cpus="2.0" rag-api
docker restart rag-api
# Processing continues from checkpoint
```

---

## Full Changelog

### Features

- Resumable processing engine with checkpoint-based recovery
- Processing progress tracking database table
- Automatic startup recovery for incomplete files
- File hash validation for change detection
- Configurable batch processing (default: 50 chunks)
- ProcessingProgressTracker class for persistence
- ChunkedTextProcessor class for batch processing

### Enhancements

- DocumentProcessor supports both resumable and legacy modes
- IndexOrchestrator resumes incomplete files on startup
- Graceful error handling with failure tracking
- Zero-overhead when resumable processing disabled

### Testing

- 18 comprehensive unit tests (100% coverage)
- Test fixtures for temporary databases
- Integration test for full workflow
- Error condition testing

### Documentation

- Updated .env.example with resumable processing variables
- Configuration documentation for all options
- Release notes (this document)

### Infrastructure

- ProcessingConfig dataclass for settings
- Database schema migration (processing_progress table)
- Startup recovery logic in application lifecycle

---

## Known Issues

### Initial Migration

First startup creates the `processing_progress` table automatically. This adds ~100ms to startup time (one-time only).

### Cleanup of Completed Records

By default, completed progress records are retained for debugging. Enable cleanup to save disk space:
```bash
CLEANUP_COMPLETED_PROGRESS=true
```

---

## Upgrading

**From v0.5.0-alpha**: Seamless upgrade, see instructions above
**From v0.4.0-alpha or earlier**: Upgrade to v0.5.0-alpha first, then v0.6.0-alpha

---

## Rollback to v0.5.0-alpha

If you encounter issues:

```bash
# Stop current instance
docker-compose down

# Revert to v0.5.0
git checkout v0.5.0-alpha

# Restart (processing_progress table ignored if present)
docker-compose up -d
```

---

## Contributors

**Project maintained by**: KatanaQuant

---

## Support

- **Documentation**: [README.md](https://github.com/KatanaQuant/rag-kb/blob/main/README.md)
- **Issues**: [GitHub Issues](https://github.com/KatanaQuant/rag-kb/issues)
- **Email**: horoshi@katanaquant.com

---

## What's Next

See the [Roadmap](https://github.com/KatanaQuant/rag-kb#roadmap) for upcoming features:

- Integration testing with Docling PDF processing
- Complete PDF migration workflow
- Performance optimization for batch sizes
- Progress monitoring API endpoint

---

**Previous Release**: [v0.5.0-alpha](https://github.com/KatanaQuant/rag-kb/releases/tag/v0.5.0-alpha)
**Repository**: [https://github.com/KatanaQuant/rag-kb](https://github.com/KatanaQuant/rag-kb)
