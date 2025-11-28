# Quick Start Guide

This guide will get you up and running with RAG-KB in under 5 minutes.

## Prerequisites

- **Docker** and **Docker Compose**
- **Node.js v14+** (for MCP server - optional)
- **Git**

## Step 0: Clone Repository

```bash
# Clone the repository
git clone https://github.com/KatanaQuant/rag-kb.git
cd rag-kb

# Checkout latest stable release
git checkout v1.7.11

# Optional: Change port if 8000 is in use
echo "RAG_PORT=8001" > .env

# Optional: Use faster model for English-only content (recommended)
echo "MODEL_NAME=sentence-transformers/static-retrieval-mrl-en-v1" >> .env
```

## Step 1: Add Content

The `knowledge_base/` directory is where you put your documents and code. It's **gitignored by default** to protect your personal/copyrighted content.

### Add Documents

```bash
# Create organization structure (optional)
mkdir -p knowledge_base/{books,notes,docs,papers}

# Add some content
cp ~/Documents/my-book.pdf knowledge_base/books/
cp ~/Documents/*.md knowledge_base/docs/
cp ~/notes/*.txt knowledge_base/notes/
```

### Add Codebases (v0.8.0+)

Same simple workflow - just drop repos into `knowledge_base/`:

```bash
cd knowledge_base
git clone https://github.com/anthropics/anthropic-sdk-python.git

# Or copy your own projects
cp -r ~/projects/my-trading-bot ./my-trading-bot
```

The system automatically:
- Routes `.py`, `.ts`, `.java`, `.cs`, `.go` files → AST-based chunking (respects function/class boundaries)
- Routes `.md`, `.pdf`, `.epub` files → Document extraction with Docling
- Skips `.git/`, `node_modules/`, `__pycache__/`, `.env` files, build artifacts, etc.

**Query Example**: "How does the SDK handle API retries?"
- Returns: `retry.py` implementation + README.md docs + related code

The service automatically indexes all supported files when it starts.

**Note:** Your content stays local and private - it's never committed to git.

## Step 2: Start the Service

### Recommended: Enable BuildKit for Faster Builds (v0.13.0+)

```bash
# Enable BuildKit for 60% faster rebuilds and 40% smaller images
export DOCKER_BUILDKIT=1

# Build and start
docker-compose up --build -d

# Wait ~30 seconds for indexing (longer for large knowledge bases)
# Check status
curl http://localhost:8000/health
```

**Make BuildKit Permanent** (recommended):
```bash
# Add to your shell profile for permanent use
echo 'export DOCKER_BUILDKIT=1' >> ~/.bashrc  # or ~/.zshrc
source ~/.bashrc
```

**Benefits**:
- First build: 7-10 minutes
- Rebuilds: 2-4 minutes (60% faster with cache)
- Image size: ~2.0-2.5 GB (40-60% smaller)

### Alternative: Standard Build

```bash
# Without BuildKit (slower, but still works)
docker-compose up --build -d
```

**Expected output:**
```json
{
  "status": "healthy",
  "indexed_documents": 15,
  "total_chunks": 1234,
  "model": "sentence-transformers/all-MiniLM-L6-v2"
}
```

## Step 3: Test a Query

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"text": "What is machine learning?", "top_k": 3}'
```

## Common Build Operations

### Rebuilding After Changes

When you update code or configuration:

```bash
# Stop the container
docker-compose down

# Rebuild with BuildKit
export DOCKER_BUILDKIT=1
docker-compose build

# Start the container
docker-compose up -d
```

**Quick rebuild (one-liner)**:
```bash
docker-compose down && export DOCKER_BUILDKIT=1 && docker-compose build && docker-compose up -d
```

### Clean Build (When Things Go Wrong)

Force a complete rebuild without cache:

```bash
docker-compose down
export DOCKER_BUILDKIT=1
docker-compose build --no-cache
docker-compose up -d
```

**Note**: `--no-cache` rebuilds all Docker layers but still uses BuildKit package caches (2-4 min vs 7-10 min).

### Cleaning Up Docker Resources

```bash
# Remove old unused images
docker image prune -f

# Check Docker disk usage
docker system df

# Clean BuildKit cache (if disk space is tight)
docker builder prune
```

### Check Image Size

```bash
# See your image size (should be ~2.0-2.5 GB with v0.13.0)
docker images | grep rag-api
```

---

## Next Steps

- **MCP Integration**: See [MCP_CLAUDE.md](MCP_CLAUDE.md), [MCP_CODEX.md](MCP_CODEX.md), or [MCP_GEMINI.md](MCP_GEMINI.md)
- **Usage Patterns**: See [USAGE.md](USAGE.md) for different query methods
- **Configuration**: See [CONFIGURATION.md](CONFIGURATION.md) for advanced settings
- **Troubleshooting**: See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) if you encounter issues

## Troubleshooting

### Build Fails

**Symptom**: `docker-compose build` fails

```bash
# Clean build (removes cached layers)
docker-compose build --no-cache

# If disk space issues
docker system prune -a
docker builder prune
```

### Service Won't Start

**Symptom**: Container exits immediately after starting

```bash
# Check logs for errors
docker-compose logs rag-api

# Common fixes:
# - Port conflict: echo "RAG_PORT=8001" > .env
# - Out of memory: echo "MAX_MEMORY=4G" > .env
# - Then restart: docker-compose up -d
```

### Model Download Fails

**Symptom**: "Failed to download model" or timeout errors

```bash
# Check disk space
df -h

# Check network connectivity
curl https://huggingface.co

# Try smaller model first
echo "MODEL_NAME=sentence-transformers/all-MiniLM-L6-v2" > .env
docker-compose restart rag-api
```

### Health Check Fails

**Symptom**: `curl http://localhost:8000/health` returns error or timeout

```bash
# Wait for startup (model loading takes time)
sleep 30
curl http://localhost:8000/health

# Check if container is running
docker-compose ps

# Check logs for startup errors
docker-compose logs rag-api --tail 50
```

For more issues, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

---

## Performance Notes

> **CPU-Only Build**: This project is optimized exclusively for CPU processing. No GPU required or supported. Large knowledge bases may take significant time to index:
>
> - **Small KB** (10-50 docs): Minutes to hours
> - **Medium KB** (100-500 docs): Hours to overnight
> - **Large KB** (500+ docs): Days to weeks
>
> **Performance Recommendation**: For English-only content, use `sentence-transformers/static-retrieval-mrl-en-v1` model for 100-400x faster processing with minimal quality trade-off. See [CONFIGURATION.md](CONFIGURATION.md#embedding-models) for details.
