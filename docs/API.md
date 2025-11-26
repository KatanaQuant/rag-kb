# API Reference

Complete guide to managing and monitoring your RAG-KB instance via API endpoints.

**Version**: v1.6.0+

---

## Table of Contents

- [Queue Management](#queue-management)
- [Priority Processing](#priority-processing)
- [Document Management](#document-management)
- [System Maintenance](#system-maintenance)
- [Monitoring](#monitoring)

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
    "store": true
  }
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
- `workers_running`: Status of each pipeline worker

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
- `file_path`: Path relative to knowledge_base/ directory
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

**Example**:
```bash
curl -X DELETE "http://localhost:8000/document/books/old-notes.pdf"
```

**Response**:
```json
{
  "status": "success",
  "message": "Document deleted",
  "chunks_deleted": 42
}
```

**Note**: This only removes from the index, not from the file system.

---

## System Maintenance

### Repair Orphaned Files

Detect and repair files that were processed but not fully indexed.

**Endpoint**: `POST /repair-orphans`

```bash
curl -X POST http://localhost:8000/repair-orphans
```

**Response**:
```json
{
  "status": "success",
  "orphans_found": 3,
  "message": "Orphaned files queued for reindexing"
}
```

**What are orphans?**
- Files that started processing but failed during embedding/storage
- Files with incomplete chunks in the database
- Typically caused by crashes or interruptions

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
curl -X POST http://localhost:8000/repair-orphans

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

1. **Adjust worker count** (`.env`):
   ```bash
   CHUNK_WORKERS=1       # Keep at 1 (bottleneck is extraction)
   EMBED_WORKERS=6       # Increase for more parallel embedding
   ```

2. **Monitor pipeline bottlenecks**:
   ```bash
   curl http://localhost:8000/queue/jobs | jq '.queue_sizes'
   ```
   - Large `chunk` queue: Slow extraction (CPU-bound)
   - Large `embed` queue: Need more EMBED_WORKERS
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
# Repair orphaned files
curl -X POST http://localhost:8000/repair-orphans

# Check health
curl http://localhost:8000/health
```

---

## See Also

- [README.md](../README.md) - Main documentation
- [ROADMAP.md](ROADMAP.md) - Planned features
- [KNOWN_ISSUES.md](KNOWN_ISSUES.md) - Known bugs and workarounds
