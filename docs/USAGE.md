# Usage Guide

This guide covers different ways to use RAG-KB for querying your knowledge base.

## Content Ingestion

The RAG service automatically indexes files in `kb/` on startup. Supported formats are detected and processed accordingly.

### Supported Formats

**PDF & DOCX** (Docling + HybridChunker):
- **PDF** (`.pdf`): Docling 2.9.0 extraction with RapidOCR, table detection, and HybridChunker for token-aware semantic chunking
- **DOCX** (`.docx`): Docling 2.9.0 extraction with HybridChunker for token-aware semantic chunking

**Code Files** (AST-based Chunking):
- **Python** (`.py`): Function and class-level chunking
- **Java** (`.java`): Method and class-level chunking
- **TypeScript/JavaScript** (`.ts`, `.tsx`, `.js`, `.jsx`): Function and class-level chunking
- **C#** (`.cs`): Method and class-level chunking
- **Go** (`.go`): Function and method-level chunking

**Markdown** (HybridChunker):
- **Markdown** (`.md`, `.markdown`): Token-aware semantic chunking with paragraph/section boundary preservation

**Specialized Formats**:
- **EPUB** (`.epub`): E-book extraction with chapter preservation
- **Jupyter Notebooks** (`.ipynb`): Cell-aware chunking with AST parsing for 160+ languages
- **Obsidian Vaults**: Full knowledge graph support with bidirectional linking

**Why HybridChunker?** PDF/DOCX get advanced structure-aware chunking that preserves document semantics (tables, code blocks, sections) while filling chunks closer to the embedding model's token capacity (512 tokens). This provides 4x better token utilization and 40% fewer chunks compared to fixed-size chunking. See [WHY_HYBRIDCHUNKER.md](WHY_HYBRIDCHUNKER.md) for technical details.

### Simple Workflow

```bash
# 1. Add files
cp ~/Downloads/book.pdf kb/books/

# 2. Restart to index (or wait for auto-sync)
docker-compose restart rag-api

# 3. Verify (wait ~30s for indexing)
curl http://localhost:8000/health
```

### Auto-Sync

The system automatically watches for new and modified files in `kb/` and indexes them without requiring a restart. Changes are detected in real-time with smart debouncing.

See [CONFIGURATION.md](CONFIGURATION.md#auto-sync-configuration) for auto-sync settings.

## Query Methods

### Via Claude Code (Recommended)

Ask Claude questions naturally in VSCode. Claude automatically decides when to query your knowledge base.

See [MCP.md](MCP.md) for setup instructions.

### Via Command Line

```bash
# Basic query
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"text": "docker networking best practices", "top_k": 5}'

# With confidence threshold
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"text": "python decorators", "top_k": 3, "threshold": 0.7}'
```

### Via Python

```python
import requests

def query_kb(question, top_k=5):
    response = requests.post("http://localhost:8000/query", json={
        "text": question,
        "top_k": top_k
    })
    return response.json()

# Use it
results = query_kb("How do I optimize database queries?")
for result in results['results']:
    print(f"Source: {result['source']} (score: {result['score']:.3f})")
    print(result['content'])
```

### Shell Alias

Add to `~/.bashrc`:
```bash
kb() {
    curl -s -X POST http://localhost:8000/query \
      -H "Content-Type: application/json" \
      -d "{\"text\": \"$1\", \"top_k\": 3}" \
      | jq -r '.results[] | "\(.source) (\(.score))\n\(.content)\n---"'
}
```

Usage: `kb "react hooks patterns"`

## Query Tips

### 1. Use specific queries

- Bad: "python"
- Good: "python async await error handling patterns"

### 2. Increase results for broader searches

```bash
curl -X POST http://localhost:8000/query \
  -d '{"text": "your query", "top_k": 10}'
```

### 3. Use confidence threshold

```bash
curl -X POST http://localhost:8000/query \
  -d '{"text": "your query", "threshold": 0.5}'
```

This filters out results with similarity scores below 0.5.

## Operational Controls (v0.11.0+)

### Queue Management

Pause, resume, or clear the indexing queue:

```bash
# Pause indexing
curl -X POST http://localhost:8000/indexing/pause

# Resume indexing
curl -X POST http://localhost:8000/indexing/resume

# Clear pending queue
curl -X POST http://localhost:8000/indexing/clear

# Monitor queue status
curl http://localhost:8000/queue/jobs
```

### Priority Processing

Fast-track specific files:

```bash
# Add file to high-priority queue
curl -X POST "http://localhost:8000/indexing/priority/kb/important.pdf"

# Check indexing status
curl http://localhost:8000/indexing/status
```

### Maintenance

```bash
# Repair orphaned files
curl -X POST http://localhost:8000/api/maintenance/reindex-orphaned-files

# Delete specific document
curl -X DELETE "http://localhost:8000/document/kb/old-file.pdf"

# Force reindex all files
curl -X POST http://localhost:8000/index \
  -H "Content-Type: application/json" \
  -d '{"force_reindex": true}'
```

**For complete API documentation with examples**, see [API.md](API.md)

## Document Management

### List Documents

```bash
# List all indexed documents
curl http://localhost:8000/documents

# Search documents by pattern
curl "http://localhost:8000/documents/search?pattern=*.pdf"
```

### Check System Health

```bash
curl http://localhost:8000/health
```

Example response:
```json
{
  "status": "healthy",
  "indexed_documents": 1588,
  "total_chunks": 36466,
  "model": "Snowflake/snowflake-arctic-embed-l-v2.0",
  "indexing_in_progress": false
}
```

## Advanced Usage

### Network Access

To access RAG-KB from other devices on your network, edit `docker-compose.yml`:

```yaml
ports:
  - "0.0.0.0:8000:8000"  # Listen on all interfaces
```

Access via: `http://YOUR_LOCAL_IP:8000`

**Security Warning**: This exposes your knowledge base to your entire network.

### Backup Strategy

**Automated backups (cron):**
```bash
# Add to crontab
0 2 * * * tar -czf ~/backups/rag-$(date +\%Y\%m\%d).tar.gz /path/to/rag-kb/data/ /path/to/rag-kb/kb/
```

**Manual backup:**
```bash
# Full backup
tar -czf rag-backup-$(date +%Y%m%d).tar.gz data/ kb/

# Database only
cp data/rag.db ~/backups/kb-$(date +%Y%m%d).db
```

### Migration Between Machines

Transfer database and files (no re-indexing needed):

```bash
# On Machine A
cd rag-kb
tar -czf rag-migration.tar.gz kb/ data/ docker-compose.yml .env api/ mcp-server/ *.sh
scp rag-migration.tar.gz user@machine-b:~/

# On Machine B
tar -xzf rag-migration.tar.gz
cd rag-kb
docker-compose up -d
curl http://localhost:8000/health
```

## Troubleshooting

### No Search Results

**Symptom**: Queries return empty results

```bash
# Check indexing status
curl http://localhost:8000/health | jq

# If indexed_documents = 0:
ls -R kb/  # Verify files exist
docker-compose logs rag-api | grep -i error  # Check for errors

# Force reindex
curl -X POST http://localhost:8000/index \
  -H "Content-Type: application/json" \
  -d '{"force_reindex": true}'
```

### Files Not Being Indexed

**Symptom**: Health shows fewer documents than expected

**Common causes**:

1. **File type not supported**
   ```bash
   docker-compose logs rag-api | grep "Unsupported"
   ```

2. **File filtered out** (check `api/ingestion/file_filter.py`)
   - Common exclusions: `.git/`, `node_modules/`, `__pycache__/`, `.env`

3. **Extraction failed**
   ```bash
   docker-compose logs rag-api | grep -i "error\|failed"
   ```

**Fix**: Try priority indexing a specific file:
```bash
curl -X POST "http://localhost:8000/indexing/priority/kb/your-file.pdf"
```

### Slow Indexing

**Symptom**: Indexing takes very long

CPU-only processing is slow by design. Options:

1. **Use faster model** (English-only):
   ```bash
   echo "MODEL_NAME=sentence-transformers/static-retrieval-mrl-en-v1" > .env
   docker-compose down && rm data/rag.db && docker-compose up --build -d
   ```

2. **Reduce batch size** (less memory, slower):
   ```bash
   echo "BATCH_SIZE=3" >> .env
   docker-compose restart rag-api
   ```

See [CONFIGURATION.md](CONFIGURATION.md#resource-profiles) for tuning.

### Poor Search Quality

**Tips for better results**:

1. **Use specific queries**:
   - Bad: "python"
   - Good: "python async await error handling patterns"

2. **Increase result count**:
   ```bash
   curl -X POST http://localhost:8000/query \
     -d '{"text": "your query", "top_k": 10}'
   ```

3. **Adjust threshold** (filter low-confidence results):
   ```bash
   curl -X POST http://localhost:8000/query \
     -d '{"text": "your query", "threshold": 0.5}'
   ```

### Indexing Stuck

**Symptom**: `indexing_in_progress: true` but no progress

```bash
# Check queue status
curl http://localhost:8000/queue/jobs

# Check for errors
docker-compose logs rag-api --tail 50

# Restart if stuck
docker-compose restart rag-api
```

For more issues, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

---

## Next Steps

- **Configuration**: See [CONFIGURATION.md](CONFIGURATION.md) for advanced settings
- **Development**: See [DEVELOPMENT.md](DEVELOPMENT.md) for testing and development
- **Troubleshooting**: See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for general issues
- **API Reference**: See [API.md](API.md) for complete API docs
