# Troubleshooting Guide

This guide covers common issues and their solutions.

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

### Database Errors

**Symptom**: "Database is locked" or corruption errors

```bash
# Stop containers
docker-compose down

# Remove lock files
rm data/*.db-*

# If corrupted, remove and rebuild
rm data/rag.db
docker-compose up -d

# Database will be recreated and files reindexed
```

## Indexing Issues

### No Search Results

**Symptom**: Queries return empty results

**Check indexing:**
```bash
# View health
curl http://localhost:8000/health | jq

# If indexed_documents = 0:
ls -R knowledge_base/  # Verify files exist
docker-compose logs rag-api | grep -i error  # Check for errors

# Force reindex
curl -X POST http://localhost:8000/index \
  -H "Content-Type: application/json" \
  -d '{"force_reindex": true}'
```

### Files Not Being Indexed

**Symptom**: Health shows fewer documents than expected

**Common causes:**

1. **File type not supported**
```bash
# Check supported formats in logs
docker-compose logs rag-api | grep "Unsupported"
```

2. **File filtered out**
```bash
# Check file filter rules in api/ingestion/file_filter.py
# Common exclusions: .git/, node_modules/, __pycache__/, .env, etc.
```

3. **Extraction failed**
```bash
# Check for extraction errors
docker-compose logs rag-api | grep -i "error\|failed"
```

**Solution:**
```bash
# View detailed logs
docker-compose logs rag-api -f

# Check file permissions
ls -la knowledge_base/your-file.pdf

# Try reindexing specific file
curl -X POST "http://localhost:8000/indexing/priority/knowledge_base/your-file.pdf"
```

### Slow Indexing Performance

**Symptom**: Indexing takes very long

**CPU-only processing is slow by design.** For faster indexing:

**Option 1: Use faster embedding model (recommended for English content)**
```bash
# Edit .env
echo "MODEL_NAME=sentence-transformers/static-retrieval-mrl-en-v1" > .env

# Rebuild (requires reindexing)
docker-compose down
rm data/rag.db
docker-compose up --build -d
```

**Option 2: Reduce resource usage**
```bash
# Edit .env for smaller batches
echo "BATCH_SIZE=3" >> .env
echo "BATCH_DELAY=1.0" >> .env
docker-compose restart rag-api
```

**Option 3: Adjust resource limits**
```bash
# Increase for more CPU cores
echo "MAX_CPUS=4.0" >> .env
echo "MAX_MEMORY=8G" >> .env
docker-compose up --build -d
```

See [CONFIGURATION.md](CONFIGURATION.md#resource-limits) for details.

### Indexing Stuck

**Symptom**: `indexing_in_progress: true` but no progress

```bash
# Check queue status
curl http://localhost:8000/queue/jobs

# Check logs for errors
docker-compose logs rag-api --tail 50

# If stuck, restart
docker-compose restart rag-api
```

## Search Quality Issues

### Poor Search Quality

**1. Use specific queries:**
- Bad: "python"
- Good: "python async await error handling patterns"

**2. Increase results:**
```bash
curl -X POST http://localhost:8000/query \
  -d '{"text": "your query", "top_k": 10}'
```

**3. Try different embedding model** (edit `.env`):
```bash
# More accurate, slower
echo "MODEL_NAME=Snowflake/snowflake-arctic-embed-l-v2.0" > .env

# Rebuild
docker-compose down
rm data/rag.db
docker-compose up --build -d
```

### Wrong Results Returned

**Symptom**: Results don't match query intent

**Check 1: Use better queries**
```bash
# Instead of: "authentication"
# Try: "user authentication implementation with JWT tokens"
```

**Check 2: Adjust threshold**
```bash
# Only return high-confidence results
curl -X POST http://localhost:8000/query \
  -d '{"text": "your query", "threshold": 0.6}'
```

**Check 3: Verify indexed content**
```bash
# List documents
curl http://localhost:8000/documents

# Search for specific files
curl "http://localhost:8000/documents/search?pattern=*auth*"
```

## MCP Integration Issues

### MCP Not Working

**Symptom**: Claude Code can't access knowledge base

**Step 1: Verify RAG is running**
```bash
curl http://localhost:8000/health
```

**Step 2: Check MCP server status**
```bash
~/.vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude mcp list
# Should show: rag-kb - Connected
```

**Step 3: If "Failed to connect" - verify path**

After switching machines or moving the project, the MCP path may be outdated:

```bash
# Remove old configuration
~/.vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude mcp remove rag-kb

# Re-add with correct absolute path
~/.vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude mcp add \
  --transport stdio \
  --scope user \
  rag-kb \
  --env RAG_API_URL=http://localhost:8000 \
  -- node /absolute/path/to/rag-kb/mcp-server/index.js

# Verify
~/.vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude mcp list
```

**Step 4: Restart VSCode**
- `Ctrl+Shift+P` → "Developer: Reload Window"

**Step 5: Check VSCode logs**
- VSCode → Output → Select "MCP" from dropdown

### Node.js Version Error

**Symptom**: MCP server fails with version error

```bash
node --version  # Should be v14+

# Upgrade to v20 LTS (Ubuntu/Debian)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
```

### Claude Not Using Knowledge Base

**Symptom**: Claude answers from general knowledge instead of RAG

See [MCP_INTEGRATION.md](MCP_INTEGRATION.md) for custom instructions to prioritize RAG queries.

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

**Symptom**: Can't read/write files in knowledge_base/

```bash
# Fix permissions (Linux)
sudo chown -R $USER:$USER knowledge_base/ data/

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

## Configuration Issues

### Environment Variables Not Working

**Symptom**: Changes to .env don't take effect

```bash
# Rebuild container
docker-compose down
docker-compose up --build -d

# Verify environment
docker exec rag-api env | grep MODEL_NAME
```

### Model Download Fails

**Symptom**: "Failed to download model"

```bash
# Check disk space
df -h

# Check network connectivity
curl https://huggingface.co

# Try different model
echo "MODEL_NAME=sentence-transformers/all-MiniLM-L6-v2" > .env
docker-compose restart rag-api
```

## Performance Issues

### High CPU Usage

**Symptom**: CPU at 100% constantly

```bash
# Check what's running
docker stats rag-api

# Reduce concurrent workers
echo "EMBED_WORKERS=1" >> .env
echo "CHUNK_WORKERS=1" >> .env
docker-compose restart rag-api

# Lower resource limits
echo "MAX_CPUS=2.0" >> .env
docker-compose up --build -d
```

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

# Disable cache
echo "CACHE_ENABLED=false" >> .env
docker-compose restart rag-api
```

### Slow Query Performance

**Symptom**: Queries take too long

```bash
# Check database size
du -h data/rag.db

# Enable caching (if disabled)
echo "CACHE_ENABLED=true" >> .env
docker-compose restart rag-api

# Reduce top_k
curl -X POST http://localhost:8000/query \
  -d '{"text": "your query", "top_k": 3}'
```

## Getting Help

If you're still experiencing issues:

1. **Check logs**: `docker-compose logs rag-api --tail 100`
2. **Check health**: `curl http://localhost:8000/health`
3. **Check documentation**: See other docs in `docs/` directory
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
