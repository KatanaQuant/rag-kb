# Scripts Directory (Deprecated)

These scripts are **deprecated** as of v2.3.0. All maintenance operations are now available via REST API endpoints.

## Use the API Instead

| Script | API Endpoint | Method |
|--------|--------------|--------|
| `cleanup_orphans.py` | `/api/maintenance/cleanup-orphans` | POST |
| `rebuild_hnsw_index.py` | `/api/maintenance/rebuild-hnsw` | POST |
| `rebuild_fts.py` | `/api/maintenance/rebuild-fts` | POST |
| `verify_integrity.py` | `/api/maintenance/verify-integrity` | GET |
| `partial_rebuild.py` | `/api/maintenance/partial-rebuild` | POST |
| `rebuild_embeddings.py` | `/api/maintenance/rebuild-embeddings` | POST |

## Example API Usage

```bash
# Verify integrity
curl http://localhost:8000/api/maintenance/verify-integrity

# Cleanup orphans (dry run)
curl -X POST http://localhost:8000/api/maintenance/cleanup-orphans \
  -H "Content-Type: application/json" \
  -d '{"dry_run": true}'

# Cleanup orphans (execute)
curl -X POST http://localhost:8000/api/maintenance/cleanup-orphans \
  -H "Content-Type: application/json" \
  -d '{"dry_run": false}'
```

## Why Deprecated?

1. **PostgreSQL migration** - Scripts were written for SQLite + vectorlite. PostgreSQL manages indexes automatically.
2. **API abstraction** - API endpoints use `OperationsFactory` for database-agnostic operations.
3. **Better UX** - API provides structured JSON responses and proper error handling.

## Scripts NOT Deprecated

- `migrate_to_postgres.py` - One-time admin migration tool
- `diagnostics/three_way_search.py` - Developer debugging tool
