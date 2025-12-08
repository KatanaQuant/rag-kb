# Troubleshooting Guide

This guide covers general issues that span multiple areas. For topic-specific troubleshooting, see:

- **Build/startup issues**: [QUICK_START.md](QUICK_START.md#troubleshooting)
- **Indexing/search issues**: [USAGE.md](USAGE.md#troubleshooting)
- **Configuration issues**: [CONFIGURATION.md](CONFIGURATION.md#troubleshooting-configuration-issues)
- **MCP integration issues**: [MCP.md](MCP.md#troubleshooting)
- **API/queue issues**: [API.md](API.md#troubleshooting)
- **Database integrity**: [MAINTENANCE.md](MAINTENANCE.md#troubleshooting)
- **Security scanning**: [SECURITY.md](SECURITY.md#troubleshooting)

---

## Service Issues

### Service Won't Start

**Symptom**: `docker-compose up` fails or exits immediately

**Check 1: Port Conflict**
```bash
# Check what's using port 8000
./get-port.sh

# Use different port
echo "RAG_PORT=8001" > .env
docker-compose up -d
```

**Check 2: Docker Resources**
```bash
# Check Docker status
docker info

# Restart Docker daemon (Linux)
sudo systemctl restart docker

# Restart Docker Desktop (macOS/Windows)
```

**Check 3: Container Logs**
```bash
docker-compose logs rag-api
```

Look for error messages indicating missing dependencies, configuration issues, or permission problems.

### Container Keeps Restarting

**Symptom**: Container status shows "Restarting"

```bash
# Check container status
docker-compose ps

# View logs
docker-compose logs rag-api --tail 100

# Common causes:
# - Out of memory (increase MAX_MEMORY in .env)
# - Missing dependencies (rebuild: docker-compose build --no-cache)
# - Configuration error (check .env and docker-compose.yml)
```

---

## Docker Issues

### Docker Out of Space

**Symptom**: "no space left on device"

```bash
# Clean up old containers and images
docker system prune -a

# Remove unused volumes
docker volume prune

# Check space
docker system df
```

### Permission Denied Errors

**Symptom**: Can't read/write files in kb/

```bash
# Fix permissions (Linux)
sudo chown -R $USER:$USER kb/ data/

# Or run with sudo (not recommended)
sudo docker-compose up -d
```

### Network Issues

**Symptom**: Can't access on localhost:8000

```bash
# Check if port is bound
netstat -tlnp | grep 8000

# Check Docker network
docker network ls
docker network inspect rag-kb_default

# Try different port
echo "RAG_PORT=8001" > .env
docker-compose up -d
```

---

## Search & Index Issues

### Search Returns No Results (or Wrong Results)

**Symptom**: Query returns no results or irrelevant results for content you know exists.

**Check 1: HNSW Index Health**
```bash
# Verify indexes are consistent
curl http://localhost:8000/api/maintenance/verify-integrity | jq

# Look for:
# - "healthy": true/false
# - HNSW vs chunks count match
# - FTS vs chunks count match
```

**Check 2: Document is Indexed**
```bash
# Search for the document
curl "http://localhost:8000/documents/search?pattern=*mybook*"

# Check if chunks exist
curl http://localhost:8000/documents/integrity | jq '.issues'
```

**Check 3: Orphan Embeddings**
```bash
# Check for orphans (chunks without documents)
curl http://localhost:8000/api/maintenance/verify-integrity | jq '.checks'

# Clean up orphans
curl -X POST http://localhost:8000/api/maintenance/cleanup-orphans \
  -H "Content-Type: application/json" \
  -d '{"dry_run": false}'
```

### HNSW Index Corruption

**Symptom**:
- Newly indexed documents don't appear in search
- `verify-integrity` shows HNSW count mismatch
- Logs show "HNSW write error"

**Cause**: Container restart during indexing, disk full, or concurrent write conflicts.

> **Note**: This was a common issue with SQLite + vectorlite (pre-v2.3.0). PostgreSQL + pgvector handles this automatically with ACID compliance.

**Fix: Rebuild HNSW Index**
```bash
# Preview rebuild
curl -X POST http://localhost:8000/api/maintenance/rebuild-hnsw \
  -H "Content-Type: application/json" \
  -d '{"dry_run": true}'

# Execute rebuild (fast - uses existing embeddings)
curl -X POST http://localhost:8000/api/maintenance/rebuild-hnsw \
  -H "Content-Type: application/json" \
  -d '{"dry_run": false}'
```

**Prevention**:
- Use `docker-compose stop` (graceful) not `docker-compose kill`
- Don't kill containers during active indexing
- Monitor disk space

For detailed HNSW postmortem, see [postmortem-hnsw-index-not-persisting.md](postmortem-hnsw-index-not-persisting.md).

### FTS/Keyword Search Not Working

**Symptom**: Exact word matches not found, BM25 scores always zero.

**Fix: Rebuild FTS Index**
```bash
# Preview rebuild
curl -X POST http://localhost:8000/api/maintenance/rebuild-fts \
  -H "Content-Type: application/json" \
  -d '{"dry_run": true}'

# Execute rebuild
curl -X POST http://localhost:8000/api/maintenance/rebuild-fts \
  -H "Content-Type: application/json" \
  -d '{"dry_run": false}'
```

### Both Vector and Keyword Search Broken

**Fix: Repair Both Indexes**
```bash
# Convenience endpoint that rebuilds HNSW + FTS together
curl -X POST http://localhost:8000/api/maintenance/repair-indexes \
  -H "Content-Type: application/json" \
  -d '{"dry_run": false}'
```

### Document Shows as Indexed but Not Searchable

**Symptom**: Document appears in `/documents` but queries don't find its content.

**Diagnose**:
```bash
# Check document integrity
curl "http://localhost:8000/documents/integrity/path/to/file.pdf"

# Look for: zero_chunks, missing_embeddings, chunk_count_mismatch
```

**Fix: Force Reindex**
```bash
# Reindex specific file
curl -X POST http://localhost:8000/api/maintenance/reindex-path \
  -H "Content-Type: application/json" \
  -d '{"path": "/app/kb/path/to/file.pdf", "dry_run": false}'

# Or reindex entire directory
curl -X POST http://localhost:8000/api/maintenance/reindex-path \
  -H "Content-Type: application/json" \
  -d '{"path": "/app/kb/books/", "dry_run": false}'
```

---

## Database Issues

### Database Issues (PostgreSQL)

**Symptom**: Connection refused or database errors

```bash
# Check PostgreSQL status
docker-compose logs postgres

# Restart PostgreSQL
docker-compose restart postgres

# If corrupted, restore from backup
docker exec -i rag-kb-postgres psql -U ragkb ragkb < ragkb_backup.sql
```

### Moving to a New Machine (Data Recovery)

**Symptom**: Need to transfer knowledge base to another machine or recover from data loss

**Solution**: Use the backup/restore scripts

```bash
# On original/source machine:
./scripts/backup_postgres.sh --compress
# Creates: data/ragkb_backup.sql.gz

# Transfer the backup file to new machine (via USB, scp, etc.)
scp data/ragkb_backup.sql.gz user@new-machine:/tmp/

# On new machine after fresh install:
# 1. Ensure PostgreSQL is running
docker-compose up -d postgres
sleep 10

# 2. Restore the backup
./scripts/restore_postgres.sh --merge

# 3. Start full stack
docker-compose up -d

# 4. Verify restore
curl http://localhost:8000/api/maintenance/verify-integrity | jq
```

For detailed multi-machine workflows, see [MAINTENANCE.md - Multi-Machine Workflow](MAINTENANCE.md#multi-machine-workflow).

### Database Issues (SQLite Legacy)

See [SQLITE_LEGACY.md](SQLITE_LEGACY.md) for SQLite-specific troubleshooting including:
- Database locked errors
- Lock file removal
- Database corruption recovery

For database integrity issues (orphans, missing chunks), see [MAINTENANCE.md](MAINTENANCE.md).

---

## Performance Issues

### High CPU Usage

**Symptom**: CPU at 100% constantly

```bash
# Check what's running
docker stats rag-api

# Reduce resource limits
echo "MAX_CPUS=2.0" >> .env
docker-compose up --build -d
```

See [CONFIGURATION.md](CONFIGURATION.md#resource-profiles) for tuning profiles.

### High Memory Usage

**Symptom**: System running out of RAM

```bash
# Check memory usage
docker stats rag-api

# Reduce memory limit
echo "MAX_MEMORY=2G" >> .env
docker-compose up --build -d

# Reduce batch size
echo "BATCH_SIZE=3" >> .env
docker-compose restart rag-api
```

---

## Getting Help

If you're still experiencing issues:

1. **Check logs**: `docker-compose logs rag-api --tail 100`
2. **Check health**: `curl http://localhost:8000/health`
3. **Check topic-specific docs**: See links at top of this page
4. **Contact support**: horoshi@katanaquant.com

### Providing Debug Information

When reporting issues, include:

```bash
# System info
uname -a
docker --version
docker-compose --version

# Service health
curl http://localhost:8000/health

# Recent logs
docker-compose logs rag-api --tail 50

# Configuration
cat .env
```
