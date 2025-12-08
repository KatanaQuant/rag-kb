# SQLite Backend (Legacy)

This document covers SQLite + vectorlite configuration for users who need to run without PostgreSQL.

> **Note**: As of v2.3.0-beta, PostgreSQL + pgvector is the default and recommended backend. SQLite is maintained for development/testing and users who cannot run PostgreSQL.

---

## When to Use SQLite

| Use Case | Recommended Backend |
|----------|-------------------|
| Production | PostgreSQL |
| Development | SQLite or PostgreSQL |
| CI/CD testing | SQLite |
| Single-file deployment | SQLite |
| No Docker/containers | SQLite |

---

## Configuration

### Enable SQLite Backend

```bash
# In .env or environment
DATABASE_URL=sqlite:///app/data/rag.db
```

The system auto-detects the backend from DATABASE_URL prefix.

### Required Dependencies

SQLite backend requires `vectorlite-py`:

```bash
pip install vectorlite-py
```

**Note**: vectorlite has limited ARM64 support. PostgreSQL is recommended for Mac Docker users.

---

## File Locations

| File | Purpose |
|------|---------|
| `data/rag.db` | SQLite database (documents, chunks, progress) |
| `data/vec_chunks.idx` | HNSW vector index file (~4KB per 1000 vectors) |

---

## Backup & Restore

### Backup

```bash
# Full backup (database + HNSW index)
cp data/rag.db data/rag.db.backup
cp data/vec_chunks.idx data/vec_chunks.idx.backup

# Or compress
tar -czf rag-backup-$(date +%Y%m%d).tar.gz data/rag.db data/vec_chunks.idx
```

### Restore

```bash
# Stop containers first
docker-compose down

# Restore files
cp data/rag.db.backup data/rag.db
cp data/vec_chunks.idx.backup data/vec_chunks.idx

# Restart
docker-compose up -d
```

---

## Database Operations

### Check Database

```bash
# Inside container
docker-compose exec rag-api python3 -c "
import sqlite3
conn = sqlite3.connect('/app/data/rag.db')
print('Documents:', conn.execute('SELECT COUNT(*) FROM documents').fetchone()[0])
print('Chunks:', conn.execute('SELECT COUNT(*) FROM chunks').fetchone()[0])
"
```

### Query Processing Progress

```python
# Check incomplete files
import sqlite3
conn = sqlite3.connect('/app/data/rag.db')
cur = conn.execute('''
    SELECT file_path, status, error_message
    FROM processing_progress
    WHERE status != "completed"
''')
for row in cur.fetchall():
    print(f'{row[0].split("/")[-1]}: {row[1]} - {row[2] or "no error"}')
```

### Clean Up Orphans (Manual)

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

---

## Troubleshooting

### Database Locked

**Symptom**: "Database is locked" errors

```bash
# Stop containers
docker-compose down

# Remove lock files
rm data/*.db-*

# Restart
docker-compose up -d
```

### Database Corruption

**Symptom**: Corruption errors or inconsistent results

```bash
# Stop containers
docker-compose down

# Remove and rebuild database
rm data/rag.db data/vec_chunks.idx

docker-compose up -d

# Database will be recreated and files reindexed
```

### HNSW Index Corruption

**Symptom**: Search returns no results despite chunks in database

vectorlite only persists the HNSW index when the connection closes. Container crashes during indexing can corrupt the index.

**Fix: Rebuild HNSW Index**

```bash
# Use the maintenance API
curl -X POST http://localhost:8000/api/maintenance/rebuild-hnsw \
  -H "Content-Type: application/json" \
  -d '{"dry_run": false}'
```

Or manually:

```bash
# Stop containers
docker-compose down

# Delete corrupted index (will be rebuilt on startup)
rm data/vec_chunks.idx

# Restart - index rebuilds from embeddings
docker-compose up -d
```

### vectorlite Import Error

**Symptom**: `no such module: vectorlite`

```bash
# Ensure vectorlite is installed
pip install vectorlite-py

# Check platform - ARM64 may have issues
python -c "import vectorlite; print('OK')"
```

---

## Migration to PostgreSQL

If you want to migrate from SQLite to PostgreSQL:

```bash
# 1. Pause indexing first!
curl -X POST http://localhost:8000/indexing/pause

# 2. Wait for current operations to complete
curl http://localhost:8000/queue/jobs | jq '.active_jobs'

# 3. Stop containers
docker-compose down

# 4. Install migration dependencies
pip install vectorlite-py psycopg2-binary

# 5. Run migration
python scripts/migrate_to_postgres.py

# 6. Update DATABASE_URL to PostgreSQL
# 7. Restart with PostgreSQL
docker-compose up -d
```

See [DATABASE_BACKENDS.md](DATABASE_BACKENDS.md) for full migration guide.

---

## Maintenance Scripts (SQLite-specific)

These scripts work directly with SQLite files:

| Script | Purpose |
|--------|---------|
| `scripts/cleanup_orphans.py` | Remove orphan chunks |
| `scripts/rebuild_hnsw_index.py` | Rebuild HNSW from embeddings |
| `scripts/rebuild_fts.py` | Rebuild FTS5 index |
| `scripts/verify_integrity.py` | Check database consistency |
| `scripts/partial_rebuild.py` | Re-embed specific ID range |
| `scripts/rebuild_embeddings.py` | Full re-embed all chunks |

> **Note**: These scripts are deprecated. Use the REST API `/api/maintenance/*` endpoints instead, which work with both SQLite and PostgreSQL.

---

## Known Limitations

| Limitation | Impact | Workaround |
|------------|--------|------------|
| No WAL | Data loss on crash | Use PostgreSQL |
| Non-atomic writes | Index corruption possible | Graceful shutdown only |
| ARM64 support | Limited | Use PostgreSQL |
| Concurrent writes | File-level locking | Single writer pattern |
| Large datasets | Performance degrades >100k chunks | Use PostgreSQL |

---

## See Also

- [DATABASE_BACKENDS.md](DATABASE_BACKENDS.md) - Full backend comparison
- [MAINTENANCE.md](MAINTENANCE.md) - Maintenance procedures (PostgreSQL-focused)
- [postmortem-vectorlite-hnsw-complete.md](postmortem-vectorlite-hnsw-complete.md) - Historical issues with vectorlite
