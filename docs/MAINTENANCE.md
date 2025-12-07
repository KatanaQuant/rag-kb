# RAG Knowledge Base Maintenance Guide

This guide explains how to diagnose and fix document integrity issues.

## Self-Healing (Automatic)

RAG-KB automatically repairs common database issues at startup:

| Check | What It Does | Environment Variable |
|-------|-------------|---------------------|
| **Empty Documents** | Deletes document records with no chunks | `AUTO_SELF_HEAL=true` (default) |
| **Chunk Count Backfill** | Fills missing `total_chunks` values | `AUTO_SELF_HEAL=true` (default) |
| **Orphan Repair** | Re-queues files marked completed but missing from DB | `AUTO_REPAIR_ORPHANS=true` (default) |
| **Incomplete Resume** | Resumes interrupted file processing | Always on |

To disable automatic self-healing:
```bash
AUTO_SELF_HEAL=false docker-compose up -d
```

**Note**: Orphans created during initial indexing are automatically detected and repaired after indexing completes (added in v1.7.1).

---

## Quick Health Check

```bash
# Get integrity report
curl http://localhost:8000/documents/integrity | python3 -m json.tool

# Summary only
curl -s http://localhost:8000/documents/integrity | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f'Total: {d[\"total_documents\"]} | Complete: {d[\"complete\"]} | Incomplete: {d[\"incomplete\"]}')"
```

## Understanding Issue Types

### 1. `chunk_count_mismatch`

**What it means:** The `total_chunks` tracking value doesn't match `chunks_processed`.

**Common causes:**
- Historical data from before v1.1.0 (tracking wasn't implemented)
- Process interrupted mid-indexing

**How to fix:**
```bash
# Run the backfill migration (dry-run first)
docker-compose exec rag-api python3 migrations/backfill_chunk_counts.py --dry-run

# Apply the migration
docker-compose exec rag-api python3 migrations/backfill_chunk_counts.py
```

### 2. `zero_chunks`

**What it means:** Document was processed but produced no chunks.

**Common causes:**
- Empty or near-empty files (legitimate)
- Files that failed extraction silently
- Unsupported content that slipped through

**How to diagnose:**
```bash
# Check file size and content
docker-compose exec rag-api python3 -c "
import os
# Replace with your file path
fp = '/app/kb/example.md'
print(f'Size: {os.path.getsize(fp)} bytes')
with open(fp) as f:
    print(f'Content preview: {f.read(200)}')"
```

**How to fix:**
```bash
# Re-index specific file
curl -X POST "http://localhost:8000/document/kb/example.md/reindex"

# Or delete and re-add
curl -X DELETE "http://localhost:8000/document/kb/example.md"
# Then trigger indexing
curl -X POST "http://localhost:8000/index"
```

### 3. `processing_incomplete`

**What it means:** No progress record exists, or processing failed/is in progress.

**Common causes:**
- Document added directly to DB without going through pipeline
- Process crashed during indexing
- File was deleted mid-processing

**How to diagnose:**
```bash
# Check processing_progress table
docker-compose exec rag-api python3 -c "
import sqlite3
conn = sqlite3.connect('/app/data/rag.db')
cur = conn.execute('''
    SELECT file_path, status, error_message
    FROM processing_progress
    WHERE status != \"completed\"
''')
for row in cur.fetchall():
    print(f'{row[0].split(\"/\")[-1]}: {row[1]} - {row[2] or \"no error\"}')"
```

**How to fix:**
```bash
# For failed documents - force re-index
curl -X POST "http://localhost:8000/document/kb/example.pdf/reindex"
```

### 4. `missing_embeddings` (ERROR severity)

**What it means:** Document record exists but has no chunks in the database.

**Common causes:**
- Orphan document record (metadata saved, chunks never created)
- Chunks were deleted but document record remains
- Embedding generation crashed

**How to fix:**
```bash
# Delete the orphan document record and re-index
curl -X DELETE "http://localhost:8000/document/kb/orphan.pdf"
curl -X POST "http://localhost:8000/index"
```

## Migrations

### v1.1.0 Migration: Backfill Chunk Counts

If upgrading from pre-v1.1.0, run this migration to fix historical tracking data:

```bash
# Always dry-run first
docker-compose exec rag-api python3 migrations/backfill_chunk_counts.py --dry-run

# Apply if satisfied
docker-compose exec rag-api python3 migrations/backfill_chunk_counts.py
```

**What it does:**
- Finds documents where `total_chunks=0` but actual chunks exist in DB
- Sets both `total_chunks` and `chunks_processed` to the actual chunk count
- Reports documents with zero chunks that need manual review

## Bulk Operations

### Re-index All Incomplete Documents

```python
# Run inside container
import requests

# Get incomplete documents
resp = requests.get('http://localhost:8000/documents/integrity')
data = resp.json()

for issue in data['issues']:
    if issue['issue'] in ('zero_chunks', 'processing_incomplete'):
        path = issue['file_path']
        print(f'Re-indexing: {path}')
        requests.post(f'http://localhost:8000/documents/reindex?path={path}&force=true')
```

### Clean Up Orphan Records

```python
# Run inside container
import sqlite3

conn = sqlite3.connect('/app/data/rag.db')

# Find orphan document records (no chunks)
orphans = conn.execute('''
    SELECT d.id, d.file_path
    FROM documents d
    WHERE NOT EXISTS (SELECT 1 FROM chunks c WHERE c.document_id = d.id)
''').fetchall()

print(f'Found {len(orphans)} orphan documents')

# Delete orphan records
for doc_id, file_path in orphans:
    conn.execute('DELETE FROM documents WHERE id = ?', (doc_id,))
    conn.execute('DELETE FROM processing_progress WHERE file_path = ?', (file_path,))

conn.commit()
```

## Maintenance REST API

All maintenance operations are available via REST API. Use `dry_run: true` to preview changes before executing.

### Quick Reference

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/maintenance/verify-integrity` | GET | Check database consistency |
| `/api/maintenance/cleanup-orphans` | POST | Remove orphan chunks/embeddings |
| `/api/maintenance/rebuild-hnsw` | POST | Rebuild HNSW vector index |
| `/api/maintenance/rebuild-fts` | POST | Rebuild FTS keyword index |
| `/api/maintenance/repair-indexes` | POST | Rebuild both HNSW + FTS |
| `/api/maintenance/reindex-path` | POST | Re-index specific file/directory |
| `/api/maintenance/rebuild-embeddings` | POST | Full re-embed all documents |
| `/api/maintenance/partial-rebuild` | POST | Re-embed chunks by ID range |

### Verify Database Integrity

```bash
# Check overall health
curl http://localhost:8000/api/maintenance/verify-integrity | jq
```

Returns:
```json
{
  "healthy": true,
  "issues": [],
  "checks": [
    {"name": "Referential Integrity", "passed": true, "details": "..."},
    {"name": "HNSW Index Consistency", "passed": true, "details": "..."},
    {"name": "FTS Index Consistency", "passed": true, "details": "..."}
  ],
  "table_counts": {"documents": 1636, "chunks": 51544, "vec_chunks": 51544}
}
```

### Clean Up Orphans

```bash
# Preview what would be deleted
curl -X POST http://localhost:8000/api/maintenance/cleanup-orphans \
  -H "Content-Type: application/json" \
  -d '{"dry_run": true}'

# Execute cleanup
curl -X POST http://localhost:8000/api/maintenance/cleanup-orphans \
  -H "Content-Type: application/json" \
  -d '{"dry_run": false}'
```

### Rebuild HNSW Index (Critical for Recovery)

Use this after HNSW index corruption or write errors. See [HNSW Index Issues](#hnsw-index-issues) below.

```bash
# Preview
curl -X POST http://localhost:8000/api/maintenance/rebuild-hnsw \
  -H "Content-Type: application/json" \
  -d '{"dry_run": true}'

# Execute (rebuilds from existing embeddings, no re-embedding)
curl -X POST http://localhost:8000/api/maintenance/rebuild-hnsw \
  -H "Content-Type: application/json" \
  -d '{"dry_run": false}'
```

### Repair Both Indexes

Convenience endpoint that runs HNSW + FTS rebuild together:

```bash
curl -X POST http://localhost:8000/api/maintenance/repair-indexes \
  -H "Content-Type: application/json" \
  -d '{"dry_run": false}'
```

### Re-index Specific Files

```bash
# Re-index a single file
curl -X POST http://localhost:8000/api/maintenance/reindex-path \
  -H "Content-Type: application/json" \
  -d '{"path": "/app/kb/documents/report.pdf", "dry_run": false}'

# Re-index entire directory
curl -X POST http://localhost:8000/api/maintenance/reindex-path \
  -H "Content-Type: application/json" \
  -d '{"path": "/app/kb/golang/", "dry_run": false}'
```

### Legacy Endpoints

These older endpoints are still available:

```bash
# Delete empty document records
curl -X POST http://localhost:8000/api/maintenance/delete-empty-documents \
  -H "Content-Type: application/json" \
  -d '{"dry_run": true}'

# Backfill chunk counts
curl -X POST http://localhost:8000/api/maintenance/backfill-chunk-counts \
  -H "Content-Type: application/json" \
  -d '{"dry_run": true}'

# Reindex failed/incomplete documents
curl -X POST http://localhost:8000/api/maintenance/reindex-failed-documents \
  -H "Content-Type: application/json" \
  -d '{"dry_run": true}'
```

See [API.md](API.md#system-maintenance) for full endpoint documentation.

---

## HNSW Index Issues

The HNSW vector index can become corrupted or inconsistent. This section covers diagnosis and recovery.

### Symptoms

- Search returns no results for queries that should match
- Newly indexed documents don't appear in search
- `verify-integrity` shows HNSW/chunks count mismatch
- Logs show "HNSW write error" or similar

### Causes

1. **Container restart during indexing** - HNSW only persists on connection close
2. **Disk full during write** - Partial index file
3. **Concurrent write conflicts** - Multiple processes writing

### Recovery Procedure

```bash
# 1. Check integrity
curl http://localhost:8000/api/maintenance/verify-integrity | jq '.checks'

# 2. If HNSW count doesn't match chunks, rebuild:
curl -X POST http://localhost:8000/api/maintenance/rebuild-hnsw \
  -H "Content-Type: application/json" \
  -d '{"dry_run": false}'

# 3. Verify fix
curl http://localhost:8000/api/maintenance/verify-integrity | jq '.healthy'
```

### Prevention

- Don't kill containers during active indexing
- Monitor disk space
- Use `docker-compose stop` (graceful) instead of `docker-compose kill`

For the full postmortem on the HNSW persistence issue, see [postmortem-hnsw-index-not-persisting.md](postmortem-hnsw-index-not-persisting.md).

---

## Monitoring

### Automated Health Check

Add to your monitoring/cron:

```bash
#!/bin/bash
# health_check.sh

RESULT=$(curl -s http://localhost:8000/documents/integrity)
INCOMPLETE=$(echo $RESULT | python3 -c "import sys,json; print(json.load(sys.stdin)['incomplete'])")

if [ "$INCOMPLETE" -gt 0 ]; then
    echo "WARNING: $INCOMPLETE incomplete documents detected"
    # Send alert, log, etc.
fi
```

## Troubleshooting

### "Why is my document showing as incomplete?"

1. Check the specific document:
   ```bash
   curl "http://localhost:8000/documents/integrity/app/kb/myfile.pdf"
   ```

2. Look at the issue type and follow the relevant section above.

### "Integrity check is slow"

The check queries all documents. For large knowledge bases:
- Consider caching the result
- Run checks during off-peak hours
- Use the single-document endpoint for spot checks

### "Migration didn't fix all documents"

Documents with `zero_chunks` after migration genuinely have no chunks in the database.
They need re-indexing, not just tracking fixes.
