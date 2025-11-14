# Migration Guide: v0.1.0-alpha → v0.2.0-alpha

**Release Date**: 2025-11-14
**Estimated Time**: 10-15 minutes (plus model download time)
**Difficulty**: Easy
**Status**: ✅ Tested and validated

---

## Overview

v0.2.0-alpha adds **multi-model embedding support** with a focus on **Snowflake Arctic Embed 2.0**, which provides significantly better retrieval quality across diverse domains.

### What's New

- ✨ **Arctic Embed 2.0-L** support (1024 dimensions, best quality)
- ✨ **Arctic Embed 2.0-M** support (768 dimensions, balanced)
- ⚙️ **Configurable model selection** via `.env` file
- 🎯 **Dynamic embedding dimensions** - automatically set based on model
- 📚 Support for **BGE** and **EmbeddingGemma** models from roadmap
- 🚀 **Docker optimization**: CPU-only PyTorch (~50% smaller images, 60% faster builds)
- 🔧 **Bug fixes**: PyTorch 2.5.1 compatibility with latest transformers

### Model Comparison

| Model | Dimensions | Quality | Speed | Use Case |
|-------|-----------|---------|-------|----------|
| all-MiniLM-L6-v2 (default) | 384 | Good | Fastest | Quick indexing, simple queries |
| Arctic Embed 2.0-M | 768 | Excellent | Moderate | Balanced quality/speed |
| Arctic Embed 2.0-L | 1024 | **Best** | Slower | Multi-domain KB, best retrieval |
| BGE-large-en-v1.5 | 1024 | Excellent | Moderate | Alternative high-quality option |

---

## Breaking Changes

⚠️ **Database Format Change**: Different embedding dimensions require re-indexing your knowledge base.

1. **Vector database must be rebuilt** when switching models
2. **Your documents stay safe** - only the vector embeddings change (documents in `knowledge_base/` are untouched)
3. **First-time model download** - Arctic Embed 2.0-L is ~1.2GB (one-time download)
4. **Docker image changes** - New CPU-only PyTorch (saves ~520MB, faster builds)

---

## Migration Steps

### Step 1: Backup Current Database

```bash
# Navigate to your rag-kb directory
cd /path/to/rag-kb

# Backup your existing database (IMPORTANT!)
cp data/knowledge_base.db data/knowledge_base.db.backup-v0.1.0

# Or create a full backup (recommended)
tar -czf rag-backup-v0.1.0-$(date +%Y%m%d).tar.gz data/ knowledge_base/
```

**Note**: Your documents in `knowledge_base/` are not affected - they never change. We're only backing up the vector database.

### Step 2: Update Code

```bash
# Stop the current service
docker-compose down

# Update to v0.2.0-alpha
git fetch origin
git checkout v0.2.0-alpha

# Or if you're on main branch
git pull origin main
```

### Step 3: Configure Model (Optional)

By default, v0.2.0 still uses `all-MiniLM-L6-v2`. To use Arctic Embed 2.0:

```bash
# Create .env file if it doesn't exist
cp .env.example .env

# Edit .env and uncomment your preferred model
vim .env
```

**Example `.env` configuration for Arctic Embed 2.0-L:**
```bash
# Uncomment this line for best quality:
MODEL_NAME=Snowflake/snowflake-arctic-embed-l-v2.0
```

**Available models:**
```bash
# Default (fastest, good quality)
MODEL_NAME=sentence-transformers/all-MiniLM-L6-v2

# Arctic Embed 2.0 (best for multi-domain)
MODEL_NAME=Snowflake/snowflake-arctic-embed-l-v2.0  # 1024 dim, best
MODEL_NAME=Snowflake/snowflake-arctic-embed-m-v2.0  # 768 dim, balanced

# BGE models (excellent alternative)
MODEL_NAME=BAAI/bge-large-en-v1.5  # 1024 dim
MODEL_NAME=BAAI/bge-base-en-v1.5   # 768 dim
```

### Step 4: Remove Old Database

⚠️ **Only do this after backing up in Step 1!**

```bash
# Remove old database (it's incompatible with new model dimensions)
rm data/knowledge_base.db
```

### Step 5: Rebuild & Reindex

```bash
# Rebuild Docker image with new code
docker-compose up --build -d

# Monitor the reindexing process
docker-compose logs -f rag-api
```

**What to expect:**

**Build phase (~2-4 minutes):**
- ✅ CPU-only PyTorch download (~185MB, not 706MB CUDA!)
- ✅ Python dependencies installation
- ✅ Docker image creation (~1GB final size)

**Startup phase (~2-5 minutes, first time only):**
- Model download: Arctic Embed 2.0-L (~1.2GB, cached for future use)
- Model loading: ~30 seconds
- Database initialization

**Indexing phase (depends on content size):**
- PDFs: ~5-10 pages/second (slower than MiniLM, but higher quality)
- Text/Markdown: ~50-100KB/second
- Progress logged for each file: "Processing: filename.pdf"
- Completion message: "RAG system ready!"

**Total time estimate:**
- Small KB (100 docs): ~10-15 minutes
- Medium KB (500 docs): ~30-45 minutes
- Large KB (1000+ docs): 1-2 hours

### Step 6: Verify Migration

```bash
# Check health endpoint
curl http://localhost:8000/health

# Expected response includes your new model:
# {
#   "status": "healthy",
#   "indexed_documents": 15,
#   "total_chunks": 1234,
#   "model": "Snowflake/snowflake-arctic-embed-l-v2.0"
# }

# Test a query
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"text": "your test query", "top_k": 3}'
```

### Step 7: Update MCP Server (if using Claude Code)

If you're using the MCP integration:

```bash
# Restart VSCode or reload window
# Then activate MCP server:
# Command Palette (Ctrl+Shift+P) → "MCP: List Servers"
```

The MCP server will automatically detect the new model.

---

## Rollback Instructions

If you encounter issues or prefer the old model:

### Option 1: Revert to v0.1.0

```bash
# Stop service
docker-compose down

# Restore backup
cp data/knowledge_base.db.backup-v0.1.0 data/knowledge_base.db

# Revert to previous version
git checkout v0.1.0-alpha

# Restart
docker-compose up -d
```

### Option 2: Switch Back to Old Model (v0.2.0)

```bash
# Stop service
docker-compose down

# Edit .env to use old model
echo "MODEL_NAME=sentence-transformers/all-MiniLM-L6-v2" > .env

# Restore backup database
cp data/knowledge_base.db.backup-v0.1.0 data/knowledge_base.db

# Restart (no rebuild needed)
docker-compose up -d
```

---

## Performance Comparison

Based on multi-domain benchmarks (see [roadmap research](../README.md#roadmap)):

### Arctic Embed 2.0-L vs MiniLM-L6-v2

**Quality Improvements:**
- **+45% better** on MTEB Retrieval benchmark
- **+40% better** on CLEF (multi-domain evaluation)
- Significantly better handling of technical jargon and diverse content types

**Trade-offs:**
- **Indexing**: ~2-3x slower (still fast: 5-10 pages/sec for PDFs)
- **Query time**: Minimal difference (embeddings are pre-computed)
- **Storage**: ~2.7x larger vectors (1024 vs 384 dimensions)
- **Model size**: 1.2GB vs 80MB download

### When to Use Each Model

**Use MiniLM-L6-v2 if:**
- You have a single-domain knowledge base (e.g., just code or just books)
- Fast indexing is critical
- Storage space is limited
- Simple queries work well enough

**Use Arctic Embed 2.0-L if:**
- You have a multi-domain knowledge base (code + books + notes)
- Retrieval quality is most important
- You query across different technical domains
- You want state-of-the-art performance

---

## FAQ

### Q: Do I need to re-add my documents?

**A:** No! Your documents in `knowledge_base/` stay exactly where they are. Only the vector database (embeddings) needs to be rebuilt.

### Q: How long does reindexing take?

**A:** Depends on your content size:
- Small (100 PDFs): ~5-10 minutes
- Medium (500 PDFs): ~30-45 minutes
- Large (1000+ PDFs): 1-2 hours

The process runs automatically on container startup.

### Q: Will my queries break during migration?

**A:** Yes, the API will be unavailable during reindexing. Plan for a brief maintenance window.

### Q: Can I use multiple models simultaneously?

**A:** Not currently. Each deployment uses one model. You can run multiple instances on different ports if needed.

### Q: What if my model isn't in MODEL_DIMENSIONS?

**A:** The system defaults to 384 dimensions. You can manually add your model to `api/config.py:MODEL_DIMENSIONS`.

### Q: Is Arctic Embed 2.0 significantly better?

**A:** For multi-domain knowledge bases, **yes**. It excels when you have diverse content (trading code + books + documentation) versus a single domain.

### Q: Can I test the new model without losing my current setup?

**A:** Yes! Keep your current instance running, clone the repo to a different directory, and test there:

```bash
# Clone to new directory
git clone https://github.com/KatanaQuant/rag-kb.git rag-kb-test
cd rag-kb-test
git checkout v0.2.0-alpha

# Use different port
echo "RAG_PORT=8001" > .env
echo "MODEL_NAME=Snowflake/snowflake-arctic-embed-l-v2.0" >> .env

# Copy your knowledge base
cp -r ../rag-kb/knowledge_base/* knowledge_base/

# Start on port 8001
docker-compose up -d

# Test queries on port 8001
curl http://localhost:8001/health
```

---

## Troubleshooting

### Model Download Fails

**Issue**: "Failed to download Snowflake/snowflake-arctic-embed-l-v2.0"

**Solution**:
```bash
# Check internet connection
# Check HuggingFace is accessible
curl https://huggingface.co

# Try with increased timeout
docker-compose down
docker-compose up --build -d
```

### Out of Disk Space

**Issue**: Docker build fails with "no space left on device"

**Solution**:
```bash
# Arctic Embed 2.0-L requires ~1.2GB
# Check available space
df -h

# Clean up Docker
docker system prune -a

# Or use smaller model
echo "MODEL_NAME=Snowflake/snowflake-arctic-embed-m-v2.0" > .env
```

### Reindexing Takes Too Long

**Issue**: Indexing has been running for hours

**Solution**:
```bash
# Check logs for progress
docker-compose logs -f rag-api

# Each file should log "Processing: filename.pdf"
# If stuck, restart:
docker-compose restart rag-api
```

### Query Results Different

**Issue**: "My queries return different results after migration"

**Expected**: Yes! Arctic Embed 2.0 has different semantic understanding. Results should be **more relevant** for multi-domain queries.

**Test**:
```bash
# Try a cross-domain query
curl -X POST http://localhost:8000/query \
  -d '{"text": "volatility in financial markets", "top_k": 5}'

# Should now better distinguish finance vs chemistry vs general usage
```

---

## Support

- **Issues**: https://github.com/KatanaQuant/rag-kb/issues
- **Email**: horoshi@katanaquant.com
- **Migration Problems**: Open an issue with:
  - Migration step that failed
  - Error logs (`docker-compose logs rag-api`)
  - Your `.env` configuration

---

## Next Steps

After successful migration:

1. **Test query quality** - Compare results with your backup instance
2. **Monitor performance** - Check indexing speed and query latency
3. **Adjust if needed** - Switch to Arctic-M or BGE if L is too slow
4. **Remove backup** - After confirming everything works:
   ```bash
   rm data/knowledge_base.db.backup-v0.1.0
   ```

---

**Version**: v0.2.0-alpha
**Last Updated**: 2025-11-14
**Tested With**: Docker 24.x, docker-compose 2.x
