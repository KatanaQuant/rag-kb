# API Reference

Complete guide to managing and monitoring your RAG-KB instance via API endpoints.

**Version**: v1.10.1

---

## Table of Contents

- [Automatic Processing](#automatic-processing)
- [Queue Management](#queue-management)
- [Priority Processing](#priority-processing)
- [Document Management](#document-management)
- [Security Scanning](#security-scanning)
- [System Maintenance](#system-maintenance)
- [Monitoring](#monitoring)
- [MCP Protocol](#mcp-protocol)

---

## Automatic Processing

RAG-KB automatically handles most operations. You typically don't need to call APIs manually.

### What Happens Automatically

| Event | Automatic Action |
|-------|------------------|
| **API startup** | Index all new/modified files in `kb/` |
| **File added/modified** | File watcher queues it for indexing (2s debounce) |
| **File added during indexing** | Queued with NORMAL priority, processed in order |
| **Crash recovery** | Incomplete files resumed on next startup |
| **Orphan detection** | Files with missing embeddings auto-repaired on startup |

### Startup Sequence

On every API startup, the system automatically:

1. **Validates configuration** - Checks paths, model, database
2. **Starts file watcher** - Monitors `kb/` for changes
3. **Sanitization stage**:
   - Resumes incomplete files (from previous crash)
   - Detects and repairs orphaned files (HIGH priority)
4. **Initial indexing** - Queues all new/modified files (NORMAL priority)

### File Watcher

The file watcher monitors `kb/` recursively and automatically queues files for indexing.

**Supported file types**: `.pdf`, `.md`, `.docx`, `.epub`, `.py`, `.java`, `.ts`, `.tsx`, `.js`, `.jsx`, `.cs`, `.go`, `.ipynb`

**Debounce**: 2 seconds (configurable via `WATCHER_DEBOUNCE_SECONDS`)

**Excluded paths**: `problematic/`, `original/`, temp files

### Security Scanning

Security checks run automatically during file validation (before indexing):
- ClamAV virus scanning (if enabled)
- YARA pattern matching (if enabled)
- Hash blacklist checking (if enabled)

**NOT automatic**: Retroactive scanning of already-indexed files. Use `POST /api/security/scan` to scan existing files.

### Integrity Checks

The system has multiple layers of integrity checks:

| Check | When | What It Detects | Action |
|-------|------|-----------------|--------|
| **Orphan detection** | Startup | Files marked "completed" but missing from documents table | Auto-reindex (HIGH priority) |
| **Incomplete resume** | Startup | Files with status != "completed" | Auto-reindex (HIGH priority) |
| **Self-healing** | Startup | Empty documents, missing chunk counts | Auto-delete/backfill |
| **Integrity check** | On-demand | Zero chunks, missing progress, chunk count mismatch | Manual via API |
| **Orphan chunks** | On-demand | Chunks without parent documents | Manual cleanup via API |

**Automatic (on startup)**:
- Orphaned files: `processing_progress.status = 'completed'` but no `documents` entry → queued for reindex
- Incomplete files: `processing_progress.status != 'completed'` → queued for reindex
- Non-existent files: File in DB but deleted from disk → cleaned from DB
- **Self-healing** (controlled by `AUTO_SELF_HEAL=true`):
  - Empty documents: Document records with 0 chunks → deleted
  - Missing chunk counts: Historical documents without tracking → backfilled

**Manual (via API)**:
```bash
# Check for issues (non-destructive)
curl http://localhost:8000/documents/integrity

# Fix specific issue types
curl -X POST http://localhost:8000/api/maintenance/reindex-failed-documents
curl -X POST http://localhost:8000/api/maintenance/delete-empty-documents
curl -X POST http://localhost:8000/api/maintenance/backfill-chunk-counts
```

### When to Use Manual APIs

Most users never need manual API calls. Use them for:

- **Priority processing**: Jump queue with `/indexing/priority/{file}`
- **Force reindex**: Reindex unchanged file with `?force=true`
- **Retroactive security scans**: Scan already-indexed files with `/api/security/scan`
- **Troubleshooting**: Pause queue, repair orphans, check status

---

## Queue Management

Control background indexing with pause/resume/clear operations.

### Pause Indexing

Stop processing new files. Files currently being processed will complete.

**Endpoint**: `POST /indexing/pause`

```bash
curl -X POST http://localhost:8000/indexing/pause
```

**Response**:
```json
{
  "status": "success",
  "message": "Indexing paused",
  "queue_size": 42
}
```

**Use Cases**:
- System maintenance or backup
- Preventing resource usage during peak hours
- Testing or debugging

---

### Resume Indexing

Resume processing files from the queue.

**Endpoint**: `POST /indexing/resume`

```bash
curl -X POST http://localhost:8000/indexing/resume
```

**Response**:
```json
{
  "status": "success",
  "message": "Indexing resumed",
  "queue_size": 42
}
```

---

### Clear Queue

Remove all pending files from the queue. **Warning**: This cannot be undone.

**Endpoint**: `POST /indexing/clear`

```bash
curl -X POST http://localhost:8000/indexing/clear
```

**Response**:
```json
{
  "status": "success",
  "message": "Indexing queue cleared",
  "queue_size": 0
}
```

**Use Cases**:
- Accidentally queued wrong directory
- Need to restart with fresh queue
- Clearing stuck/problematic files

---

### Monitor Queue Status

Get current queue and pipeline status.

**Endpoint**: `GET /queue/jobs`

```bash
curl http://localhost:8000/queue/jobs
```

**Response**:
```json
{
  "input_queue_size": 150,
  "paused": false,
  "worker_running": true,
  "queue_sizes": {
    "chunk": 5,
    "embed": 10,
    "store": 2
  },
  "active_jobs": {
    "chunk": "large-book.pdf",
    "embed": ["doc1.md", "doc2.md", "doc3.md"],
    "store": "code-file.py"
  },
  "workers_running": {
    "chunk": true,
    "embed": true,
    "store": true,
    "security_scan": false
  },
  "security_scan": null
}
```

**Fields Explained**:
- `input_queue_size`: Files waiting to be processed
- `paused`: Whether queue is paused
- `queue_sizes`: Files in each pipeline stage
  - `chunk`: Waiting for text extraction & chunking
  - `embed`: Waiting for embedding generation
  - `store`: Waiting to be stored in database
- `active_jobs`: Files currently being processed
- `workers_running`: Status of each pipeline worker (including security_scan)
- `security_scan`: Active security scan status (null if no scan running)

---

### Check Indexing Status

Get high-level indexing progress.

**Endpoint**: `GET /indexing/status`

```bash
curl http://localhost:8000/indexing/status
```

**Response**:
```json
{
  "indexing_in_progress": true,
  "queue_size": 42,
  "paused": false
}
```

---

## Priority Processing

Fast-track specific files to the front of the queue.

### Add High-Priority File

**Endpoint**: `POST /indexing/priority/{file_path}`

**Parameters**:
- `file_path`: Path relative to kb/ directory
- `force`: (optional, default: false) Reindex even if already indexed

**Example**:
```bash
# Add with high priority
curl -X POST "http://localhost:8000/indexing/priority/books/urgent-document.pdf"

# Force reindex with high priority
curl -X POST "http://localhost:8000/indexing/priority/books/urgent-document.pdf?force=true"
```

**Response**:
```json
{
  "status": "success",
  "message": "File added to queue with HIGH priority",
  "file_path": "books/urgent-document.pdf"
}
```

**Use Cases**:
- Just added critical document that needs immediate indexing
- Testing specific file without waiting for queue
- Reindexing updated file quickly

---

## Document Management

### List All Documents

Get all indexed documents with metadata.

**Endpoint**: `GET /documents`

```bash
curl http://localhost:8000/documents
```

**Response**:
```json
{
  "total_documents": 1576,
  "documents": [
    {
      "file_path": "books/machine-learning.pdf",
      "indexed_at": "2025-11-21T10:30:00",
      "chunk_count": 234
    },
    {
      "file_path": "notes/trading-strategies.md",
      "indexed_at": "2025-11-21T09:15:00",
      "chunk_count": 42
    }
  ]
}
```

---

### Search Documents by Pattern

Find documents matching a pattern.

**Endpoint**: `GET /documents/search?pattern={pattern}`

**Example**:
```bash
# Search for all PDFs
curl "http://localhost:8000/documents/search?pattern=*.pdf"

# Search in specific directory
curl "http://localhost:8000/documents/search?pattern=books/*.md"
```

**Response**:
```json
{
  "total_results": 42,
  "documents": [...]
}
```

---

### Get Document Info

Get metadata for a specific document.

**Endpoint**: `GET /document/{filename}`

**Example**:
```bash
curl "http://localhost:8000/document/mybook.pdf"
```

**Response**:
```json
{
  "file_path": "books/mybook.pdf",
  "indexed_at": "2025-11-21T10:30:00",
  "chunk_count": 234,
  "file_hash": "abc123..."
}
```

---

### Delete Document

Remove document and all its chunks from the index.

**Endpoint**: `DELETE /document/{file_path}`

**Path format**: Use the container path (e.g., `/app/kb/...`) and URL-encode it.

**Example** (simple path):
```bash
curl -X DELETE "http://localhost:8000/document/%2Fapp%2Fkb%2Fbooks%2Fold-notes.pdf"
```

**Example** (path with spaces - requires URL encoding):
```bash
# Use docker exec to avoid local Python version issues
encoded=$(docker exec rag-api python3 -c "import urllib.parse; print(urllib.parse.quote('/app/kb/My Book - Author.pdf', safe=''))")
curl -X DELETE "http://localhost:8000/document/$encoded"
```

**Response**:
```json
{
  "status": "success",
  "file_path": "/app/kb/books/old-notes.pdf",
  "found": true,
  "document_id": 123,
  "chunks_deleted": 42,
  "document_deleted": true
}
```

**Note**: This only removes from the index, not from the file system.

---

### Reindex Document

Delete and re-queue a document for processing. Combines delete + priority queue operations.

**Endpoint**: `POST /document/{file_path}/reindex`

**Example**:
```bash
curl -X POST "http://localhost:8000/document/books/mybook.pdf/reindex"
```

**Response**:
```json
{
  "status": "success",
  "file_path": "/app/kb/books/mybook.pdf",
  "action": "reindex",
  "deletion": {
    "deleted": true,
    "chunks_deleted": 234
  },
  "queued": true,
  "priority": "HIGH",
  "queue_size": 1
}
```

**Use Cases**:
- Force re-processing after pipeline changes
- Re-index after manual file edits
- E2E testing (validates full pipeline)

---

### Check Document Integrity

Get integrity status for all documents.

**Endpoint**: `GET /documents/integrity`

```bash
curl http://localhost:8000/documents/integrity
```

**Response**:
```json
{
  "total_documents": 1576,
  "complete": 1570,
  "incomplete": 6,
  "issues": [
    {
      "file_path": "/app/kb/broken.pdf",
      "issue_type": "zero_chunks",
      "details": "Document has 0 chunks"
    }
  ]
}
```

**Check single document**:
```bash
curl "http://localhost:8000/documents/integrity/books/mybook.pdf"
```

---

## Security Scanning

Scan files for malware using ClamAV, YARA rules, and hash blacklists.

### Start Security Scan

Scan all files in knowledge_base for security threats. Runs in background with parallel workers (8x faster than sequential).

**Endpoint**: `POST /api/security/scan`

```bash
curl -X POST http://localhost:8000/api/security/scan
```

**Response**:
```json
{
  "job_id": "8dc87920",
  "status": "pending",
  "message": "Security scan started"
}
```

---

### Get Scan Status

Check progress and results of a security scan.

**Endpoint**: `GET /api/security/scan/{job_id}`

```bash
curl http://localhost:8000/api/security/scan/8dc87920
```

**Response (in progress)**:
```json
{
  "job_id": "8dc87920",
  "status": "running",
  "progress": 1500,
  "total_files": 2871,
  "result": null,
  "message": "Scanning: 1500/2871 files (52%)"
}
```

**Response (completed)**:
```json
{
  "job_id": "8dc87920",
  "status": "completed",
  "progress": 2871,
  "total_files": 2871,
  "result": {
    "total_files": 2871,
    "clean_files": 2865,
    "critical_count": 0,
    "warning_count": 6,
    "critical_findings": [],
    "warning_findings": [
      {
        "file_path": "/app/kb/notes/empty.md",
        "filename": "empty.md",
        "severity": "WARNING",
        "reason": "File is empty"
      }
    ]
  },
  "message": "Scan complete"
}
```

---

### Scan Single File

Immediately scan a specific file for security threats. Returns results synchronously (no job ID).

**Endpoint**: `POST /api/security/scan/file`

```bash
# Scan a specific file
curl -X POST "http://localhost:8000/api/security/scan/file?file_path=test.pdf"

# URL encode paths with spaces
curl -X POST "http://localhost:8000/api/security/scan/file?file_path=My%20Book.pdf"
```

**Parameters**:
- `file_path` (required): Path relative to knowledge base root

**Response (clean file)**:
```json
{
  "file_path": "golang/The Little Go Book - Karl Seguin.pdf",
  "file_type": "pdf",
  "status": "clean",
  "threats_found": 0,
  "scan_time_ms": 29
}
```

**Response (threat detected)**:
```json
{
  "file_path": "eicar.md",
  "file_type": "malware",
  "status": "threat_detected",
  "threats_found": 1,
  "threats": [
    {
      "severity": "critical",
      "rule_name": "Win.Test.EICAR_HDB-1",
      "description": "ClamAV signature match: Win.Test.EICAR_HDB-1",
      "context": ""
    }
  ],
  "scan_time_ms": 9
}
```

**Use cases**:
- Test individual files for malware
- Validate files before manual indexing
- Quick security check on suspicious files

---

### List All Scan Jobs

**Endpoint**: `GET /api/security/scan`

```bash
curl http://localhost:8000/api/security/scan
```

---

### Get Rejected Files

List all files that failed security validation.

**Endpoint**: `GET /api/security/rejected`

```bash
curl http://localhost:8000/api/security/rejected
```

**Response**:
```json
{
  "total": 2,
  "rejected_files": [
    {
      "file_path": "malicious.exe",
      "reason": "Executable file rejected",
      "rejected_at": "2025-11-26T10:00:00",
      "severity": "CRITICAL"
    }
  ]
}
```

---

### Quarantine Management

Dangerous files are automatically quarantined.

**List Quarantined Files**:
```bash
curl http://localhost:8000/api/security/quarantine
```

**Restore File from Quarantine**:
```bash
curl -X POST http://localhost:8000/api/security/quarantine/restore \
  -H "Content-Type: application/json" \
  -d '{"filename": "suspicious.pdf.REJECTED", "force": false}'
```

**Purge Old Quarantined Files** (default: 30 days):
```bash
curl -X POST http://localhost:8000/api/security/quarantine/purge \
  -H "Content-Type: application/json" \
  -d '{"older_than_days": 30, "dry_run": false}'
```

---

### Cache Management

Security scan results are cached by file hash. Clear cache to force re-scanning.

**Get Cache Stats**:
```bash
curl http://localhost:8000/api/security/cache/stats
```

**Clear Cache**:
```bash
curl -X DELETE http://localhost:8000/api/security/cache
```

---

## System Maintenance

### Reindex Orphaned Files

Reindex files that were processed but never fully indexed (marked "completed" but missing from documents table).

**Endpoint**: `POST /api/maintenance/reindex-orphaned-files`

```bash
curl -X POST http://localhost:8000/api/maintenance/reindex-orphaned-files
```

**Response**:
```json
{
  "status": "success",
  "orphans_found": 3,
  "orphans_queued": 3,
  "message": "Queued 3 orphaned files for reindexing with HIGH priority"
}
```

**What are orphaned files?**
- Files marked "completed" in progress tracking but missing from documents table
- Typically caused by crashes during embedding/storage
- Auto-detected on startup, but can be triggered manually

**When to use**:
- After system crash or forced shutdown
- Inconsistent search results
- Database integrity check

---

### Force Reindex All

Reindex entire knowledge base.

**Endpoint**: `POST /index`

**Parameters**:
- `force_reindex`: (default: false) If true, reindex all files

**Example**:
```bash
# Reindex only new/modified files
curl -X POST http://localhost:8000/index \
  -H "Content-Type: application/json" \
  -d '{"force_reindex": false}'

# Force reindex everything
curl -X POST http://localhost:8000/index \
  -H "Content-Type: application/json" \
  -d '{"force_reindex": true}'
```

**Response**:
```json
{
  "status": "success",
  "files_indexed": 150,
  "chunks_created": 3456
}
```

**Warning**: Force reindex is slow and resource-intensive. Only use when necessary.

---

### Backfill Chunk Counts

Backfill missing chunk counts for historical documents indexed before chunk tracking was added.

**Endpoint**: `POST /api/maintenance/backfill-chunk-counts`

```bash
curl -X POST http://localhost:8000/api/maintenance/backfill-chunk-counts
```

**Response**:
```json
{
  "documents_checked": 150,
  "documents_updated": 5,
  "dry_run": false,
  "message": "Updated 5 documents"
}
```

**Dry run** (preview without changes):
```bash
curl -X POST http://localhost:8000/api/maintenance/backfill-chunk-counts \
  -H "Content-Type: application/json" \
  -d '{"dry_run": true}'
```

---

### Delete Empty Documents

Delete document records that have no chunks (empty documents from interrupted processing).

**Endpoint**: `POST /api/maintenance/delete-empty-documents`

```bash
curl -X POST http://localhost:8000/api/maintenance/delete-empty-documents
```

**Response**:
```json
{
  "orphans_found": 5,
  "orphans_deleted": 5,
  "dry_run": false,
  "orphans": [...],
  "message": "Deleted 5 orphan documents"
}
```

**Dry run** (preview without changes):
```bash
curl -X POST http://localhost:8000/api/maintenance/delete-empty-documents \
  -H "Content-Type: application/json" \
  -d '{"dry_run": true}'
```

---

### Reindex Failed Documents

Queue all documents with integrity issues (zero chunks, missing embeddings, incomplete processing) for re-indexing with HIGH priority. Returns immediately - check `/indexing/status` for progress.

**Endpoint**: `POST /api/maintenance/reindex-failed-documents`

```bash
curl -X POST http://localhost:8000/api/maintenance/reindex-failed-documents
```

**Response**:
```json
{
  "documents_found": 10,
  "documents_queued": 10,
  "dry_run": false,
  "documents": [...],
  "message": "Queued 10 documents for reindexing with HIGH priority"
}
```

**Filter by issue type**:
```bash
curl -X POST http://localhost:8000/api/maintenance/reindex-failed-documents \
  -H "Content-Type: application/json" \
  -d '{"issue_types": ["zero_chunks", "processing_incomplete"]}'
```

**Dry run** (preview without queueing):
```bash
curl -X POST http://localhost:8000/api/maintenance/reindex-failed-documents \
  -H "Content-Type: application/json" \
  -d '{"dry_run": true}'
```

---

### Find Duplicate Chunks

Find duplicate chunks in the database (within and across documents).

**Endpoint**: `GET /api/maintenance/find-duplicate-chunks`

```bash
curl http://localhost:8000/api/maintenance/find-duplicate-chunks
```

**Response**:
```json
{
  "status": "success",
  "total_documents": 1500,
  "total_chunks": 35000,
  "within_document_duplicates": {
    "count": 5,
    "total_duplicate_chunks": 12,
    "impact": "These are usually problematic and should be cleaned"
  },
  "cross_document_duplicates": {
    "count": 3,
    "top_10": [...],
    "impact": "May be intentional (shared content like headers, footers)"
  },
  "recommendation": "Run /api/maintenance/delete-duplicate-chunks to remove within-document duplicates"
}
```

---

### Delete Duplicate Chunks

Delete duplicate chunks within documents (keeps first occurrence, removes rest).

**Endpoint**: `POST /api/maintenance/delete-duplicate-chunks`

```bash
curl -X POST http://localhost:8000/api/maintenance/delete-duplicate-chunks
```

**Response**:
```json
{
  "status": "success",
  "duplicates_found": 5,
  "chunks_deleted": 12,
  "final_chunk_count": 34988,
  "message": "Successfully removed 12 duplicate chunks from 5 documents"
}
```

---

## Monitoring

### Health Check

Get system health and statistics.

**Endpoint**: `GET /health`

```bash
curl http://localhost:8000/health
```

**Response**:
```json
{
  "status": "healthy",
  "indexed_documents": 1576,
  "total_chunks": 36396,
  "model": "Snowflake/snowflake-arctic-embed-l-v2.0",
  "indexing_in_progress": false
}
```

**Use Cases**:
- Monitoring scripts
- Docker health checks
- System status dashboards

---

### Query Knowledge Base

Semantic search across indexed documents.

**Endpoint**: `POST /query`

**Request**:
```json
{
  "text": "How do I optimize database queries?",
  "top_k": 5,
  "threshold": 0.5
}
```

**Parameters**:
- `text`: Search query (required)
- `top_k`: Number of results to return (default: 5)
- `threshold`: Minimum similarity score (default: 0.0, range: 0.0-1.0)

**Example**:
```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{
    "text": "python async patterns",
    "top_k": 3,
    "threshold": 0.7
  }'
```

**Response**:
```json
{
  "query": "python async patterns",
  "total_results": 3,
  "results": [
    {
      "content": "AsyncIO provides cooperative multitasking...",
      "source": "books/python-cookbook.pdf",
      "page": 142,
      "score": 0.89
    },
    {
      "content": "Event loops are the core of async programming...",
      "source": "notes/async-guide.md",
      "page": 1,
      "score": 0.82
    },
    {
      "content": "Async context managers using __aenter__...",
      "source": "code/examples/async_patterns.py",
      "page": 1,
      "score": 0.75
    }
  ]
}
```

---

## Common Workflows

### Workflow 1: Adding Urgent Document

```bash
# 1. Pause queue to prevent interference
curl -X POST http://localhost:8000/indexing/pause

# 2. Add file with high priority
curl -X POST "http://localhost:8000/indexing/priority/urgent-doc.pdf?force=true"

# 3. Resume queue
curl -X POST http://localhost:8000/indexing/resume

# 4. Monitor progress
curl http://localhost:8000/queue/jobs
```

---

### Workflow 2: System Maintenance

```bash
# 1. Pause indexing
curl -X POST http://localhost:8000/indexing/pause

# 2. Clear pending queue
curl -X POST http://localhost:8000/indexing/clear

# 3. Repair any orphaned files
curl -X POST http://localhost:8000/api/maintenance/reindex-orphaned-files

# 4. Resume normal operation
curl -X POST http://localhost:8000/indexing/resume
```

---

### Workflow 3: Batch Queue Management

```bash
# 1. Check current queue status
curl http://localhost:8000/queue/jobs | jq '.input_queue_size'

# 2. If queue is too large, pause
curl -X POST http://localhost:8000/indexing/pause

# 3. Prioritize specific files
curl -X POST "http://localhost:8000/indexing/priority/important1.pdf"
curl -X POST "http://localhost:8000/indexing/priority/important2.pdf"

# 4. Resume processing
curl -X POST http://localhost:8000/indexing/resume
```

---

## Error Handling

All endpoints return standard HTTP status codes:

- `200 OK`: Success
- `400 Bad Request`: Invalid parameters
- `404 Not Found`: Document/file not found
- `500 Internal Server Error`: Server error

**Error Response Format**:
```json
{
  "detail": "Error message describing what went wrong"
}
```

---

## Rate Limiting

**Current Implementation**: No rate limiting

For production deployments with public API access, consider adding:
- Nginx rate limiting
- API gateway (Kong, Tyk)
- Application-level rate limiting

---

## Security Considerations

**Default Setup**: No authentication

The API is designed for local/private network use. For public access:

1. **Add Authentication**: Implement API keys or OAuth
2. **Use HTTPS**: Reverse proxy with SSL/TLS
3. **Network Isolation**: Firewall rules, VPN, or private network
4. **Read-Only Mode**: Disable write endpoints for public queries

---

## Performance Tips

### Monitoring Queue Health

```bash
# Watch queue in real-time
watch -n 2 'curl -s http://localhost:8000/queue/jobs | jq'

# Check if workers are stuck
curl http://localhost:8000/queue/jobs | jq '.workers_running'
```

### Optimizing Throughput

1. **Use default worker settings** (`.env`):
   ```bash
   CHUNK_WORKERS=2          # Default (more workers don't help - GIL)
   EMBEDDING_WORKERS=2      # Default (more workers don't help - GIL)
   EMBEDDING_BATCH_SIZE=32  # Batch encoding provides 10-50x speedup
   ```
   Note: Increasing worker counts does not improve performance due to Python GIL contention.

2. **Monitor pipeline bottlenecks**:
   ```bash
   curl http://localhost:8000/queue/jobs | jq '.queue_sizes'
   ```
   - Large `chunk` queue: Slow extraction (CPU-bound, OCR)
   - Large `embed` queue: Normal - batch encoding processes in batches
   - Large `store` queue: Database I/O issue

3. **Batch operations**:
   - Use `pause` → process priority files → `resume`
   - Clear queue before bulk imports
   - Schedule large indexing during off-hours

---

## Troubleshooting

### Queue Not Processing

```bash
# Check if paused
curl http://localhost:8000/indexing/status

# Check worker status
curl http://localhost:8000/queue/jobs | jq '.workers_running'

# Resume if paused
curl -X POST http://localhost:8000/indexing/resume
```

### Files Stuck in Queue

```bash
# Check active jobs
curl http://localhost:8000/queue/jobs | jq '.active_jobs'

# If same file stuck for >10 minutes, restart API
docker-compose restart rag-api
```

### Inconsistent Search Results

```bash
# Check document integrity
curl http://localhost:8000/documents/integrity

# Repair orphaned files
curl -X POST http://localhost:8000/api/maintenance/reindex-orphaned-files

# Reindex any failed documents
curl -X POST http://localhost:8000/api/maintenance/reindex-failed-documents

# Check health
curl http://localhost:8000/health
```

---

## MCP Protocol

The API exposes an MCP (Model Context Protocol) endpoint for AI tool integration.

### MCP Info

Get MCP server capabilities.

**Endpoint**: `GET /mcp`

```bash
curl http://localhost:8000/mcp
```

**Response**:
```json
{
  "name": "rag-kb-http",
  "version": "1.0.0",
  "protocol": "MCP Streamable HTTP",
  "transport": "HTTP + SSE",
  "authentication": "none (local network only)",
  "tools": ["query_kb", "list_indexed_documents", "get_kb_stats"],
  "endpoint": "/mcp"
}
```

### MCP JSON-RPC

Send JSON-RPC 2.0 requests for AI tool calls.

**Endpoint**: `POST /mcp`

**Supported Methods**:
- `initialize`: Initialize MCP session
- `tools/list`: List available tools
- `tools/call`: Call a tool (query_kb, list_indexed_documents, get_kb_stats)

**Example**:
```bash
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "query_kb",
      "arguments": {"query": "python async patterns", "top_k": 5}
    }
  }'
```

For SSE streaming responses, include `text/event-stream` in the Accept header.

---

## See Also

- [README.md](../README.md) - Main documentation
- [ROADMAP.md](ROADMAP.md) - Planned features
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Common issues
