# RAG-KB

[![Latest Release](https://img.shields.io/github/v/release/KatanaQuant/rag-kb?include_prereleases)](https://github.com/KatanaQuant/rag-kb/releases)
[![Docker](https://img.shields.io/badge/docker-ready-blue)](https://github.com/KatanaQuant/rag-kb)
[![License](https://img.shields.io/badge/license-Public%20Domain-green)](https://github.com/KatanaQuant/rag-kb)

**Token-efficient semantic search for your personal knowledge base.** Query books, code, notes, and documents using natural language—runs 100% locally with no external APIs.

Built with FastAPI, sqlite-vec, and sentence-transformers.

**Current Version**: v0.2.0-alpha (see [Releases](https://github.com/KatanaQuant/rag-kb/releases) for changelog)

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [VSCode/Claude Code Integration](#vscodeclaude-code-integration)
- [Content Ingestion](#content-ingestion)
- [Usage](#usage)
- [Development & Testing](#development--testing)
- [Troubleshooting](#troubleshooting)
- [Advanced Configuration](#advanced-configuration)
- [Roadmap](#roadmap)

---

## Features

- **Semantic Search**: Natural language queries across all your documents
- **100% Local**: No external APIs, complete privacy
- **Auto-Sync**: Automatically detects and indexes new/modified files in real-time
- **Multiple Formats**: PDF, Markdown, TXT, DOCX, Obsidian vaults, code repositories
- **Token Efficient**: Returns only relevant chunks (~3-5K tokens vs 100K+ for full files)
- **Docker-Based**: Runs anywhere Docker runs
- **MCP Integration**: Built-in server for Claude Code/VSCode
- **Portable**: Single SQLite database file - easy to backup and migrate

---

## Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────┐
│                    Claude Code / VSCode                      │
└──────────────────────────┬──────────────────────────────────┘
                           │ MCP Protocol
                           ↓
┌─────────────────────────────────────────────────────────────┐
│                  MCP Server (Node.js)                        │
│  • query_knowledge_base  • list_documents  • get_stats       │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP API
                           ↓
┌─────────────────────────────────────────────────────────────┐
│                   RAG API (FastAPI/Docker)                   │
│  • Text Extraction  • Chunking  • Vector Embeddings          │
│  • Semantic Search  • SQLite + vec0                          │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ↓
┌─────────────────────────────────────────────────────────────┐
│              Knowledge Base (File System)                    │
│  knowledge_base/          data/                              │
│  ├── books/              └── knowledge_base.db               │
│  ├── code/                                                   │
│  ├── obsidian/                                               │
│  └── notes/                                                  │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **Ingestion**: Files → Text Extraction → Chunking → Embedding → SQLite
2. **Query**: Question → Embedding → Vector Search → Top Results → Response
3. **MCP**: Claude queries via MCP → API processes → Results returned

---

## Quick Start

### Prerequisites

- **Docker** and **Docker Compose**
- **Node.js v14+** (for MCP server)
- **Git**

### Step 0: Clone Repository

```bash
# Clone the repository
git clone https://github.com/KatanaQuant/rag-kb.git
cd rag-kb

# Checkout latest stable release (recommended)
git checkout v0.2.0-alpha

# Or stay on main for latest features (may have bugs)
# git checkout main

# Optional: Change port if 8000 is in use
echo "RAG_PORT=8001" > .env

# Optional: Use advanced embedding model (requires re-indexing, see below)
# echo "MODEL_NAME=Snowflake/snowflake-arctic-embed-l-v2.0" >> .env
```

> **Upgrading from v0.1.0?** See [docs/MIGRATION_v0.1_to_v0.2.md](docs/MIGRATION_v0.1_to_v0.2.md)

### Step 1: Add Content

The `knowledge_base/` directory is where you put your documents. It's **gitignored by default** to protect your personal/copyrighted content.

Create subdirectories and add your files:

```bash
# Create organization structure (optional)
mkdir -p knowledge_base/{books,notes,code,papers}

# Add some content
cp ~/Documents/my-book.pdf knowledge_base/books/
cp ~/notes/*.txt knowledge_base/notes/
```

The service automatically indexes all supported files (PDF, TXT, DOCX, MD) when it starts.

**Note:** Your content stays local and private - it's never committed to git.

**Other formats** (Obsidian vaults, code repositories, etc.) are supported via custom workflows - see [Advanced Workflows](#advanced-workflows) below.

### Step 2: Start the Service

```bash
# Build and start
docker-compose up --build -d

# Wait ~30 seconds for indexing
# Check status
curl http://localhost:8000/health
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

### Step 3: Test a Query

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"text": "What is machine learning?", "top_k": 3}'
```

---

## VSCode/Claude Code Integration

Use your knowledge base directly in VSCode with Claude Code extension.

**Note:** Currently tested with VSCode. Other IDE examples available on request.

### Setup (One-Time)

**1. Ensure RAG service is running:**
```bash
docker-compose up -d
curl http://localhost:8000/health
```

**2. Add MCP server globally:**
```bash
~/.vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude mcp add \
  --transport stdio \
  --scope user \
  rag-kb \
  --env RAG_API_URL=http://localhost:8000 \
  -- node /absolute/path/to/rag-kb/mcp-server/index.js
```

**3. Enable for projects:**

Edit `~/.claude.json` to enable for specific projects:
```json
{
  "projects": {
    "/path/to/your/project": {
      "enabledMcpjsonServers": ["rag-kb"]
    }
  }
}
```

Or use Claude Code UI to approve when prompted.

**4. Reload VSCode:**
- `Ctrl+Shift+P` → "Developer: Reload Window"

### Verify Connection

```bash
~/.vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude mcp list
# Should show: rag-kb - ✓ Connected
```

### Using in Claude Code

Claude automatically queries your knowledge base when relevant:

```
You: "What does the law of active management say?"

Claude: [Calls query_knowledge_base MCP tool]
Based on your indexed books, the law of active management states...
```

---

## Content Ingestion

The RAG service automatically indexes files in `knowledge_base/` on startup. Supported formats are detected and processed accordingly.

### Supported Formats

**Direct Ingestion** (automatic):
- **PDF**: `.pdf` files
- **Text**: `.txt`, `.md` files
- **Documents**: `.docx` files

**Pre-processed Ingestion** (requires export scripts):
- **Code repositories**: Use export scripts
- **Obsidian vaults**: Use `ingest-obsidian.sh`

### Simple Workflow

```bash
# 1. Add files
cp ~/Downloads/book.pdf knowledge_base/books/

# 2. Restart to index
docker-compose restart rag-api

# 3. Verify (wait ~30s for indexing)
curl http://localhost:8000/health
```

### Advanced Workflows

#### Obsidian Vault

```bash
# Simple ingestion (preserves wiki links, callouts, tags)
./ingest-obsidian.sh ~/Documents/MyVault vault-name

# Restart to index
docker-compose restart rag-api
```

See [docs/OBSIDIAN_INTEGRATION.md](docs/OBSIDIAN_INTEGRATION.md) for details.

#### Code Repositories

Export code to Markdown for better semantic chunking:

```bash
# Simple export
./export-codebase-simple.sh /path/to/project > knowledge_base/code/project.md

# With directory tree
./export-codebase.sh /path/to/project > knowledge_base/code/project-full.md

# For analysis (with description)
./export-for-analysis.sh /path/to/project "API server" > knowledge_base/code/api.md

# Restart to index
docker-compose restart rag-api
```

**Why pre-process code?**
- Better semantic chunking (functions stay together)
- Preserves file structure and context
- Removes noise (binaries, dependencies)

See [docs/CONTENT_SOURCES.md](docs/CONTENT_SOURCES.md) for more formats (Notion, Jupyter, Slack, etc).

---

## Usage

### Via Claude Code (Recommended)

Just ask questions naturally. Claude automatically decides when to query your knowledge base.

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

---

## Development & Testing

### Architecture

The codebase is organized into focused, testable modules:

**[api/ingestion.py](api/ingestion.py)** - Document processing pipeline
- Format extractors (PDF, DOCX, Markdown, Text)
- Text chunking with configurable overlap
- Vector storage and retrieval

**[api/main.py](api/main.py)** - FastAPI application
- Model loading and embedding generation
- Document indexing orchestration
- Semantic search execution

**[api/config.py](api/config.py)** - Centralized configuration
- Type-safe dataclasses for all settings
- No magic numbers

### Running Tests

```bash
# Install dependencies
pip install pytest pytest-cov

# Run all tests
cd api
python -m pytest tests/ -v

# With coverage
python -m pytest tests/ --cov=. --cov-report=term-missing
```

**Test structure:**
```
api/tests/
├── conftest.py              # Pytest configuration
├── test_config.py           # Configuration tests
├── test_ingestion.py        # Document processing tests
└── test_main.py             # API component tests
```

### Development Workflow

```bash
# 1. Make changes to api/ files
# 2. Run tests
python -m pytest tests/ -v

# 3. Rebuild and test
docker-compose up --build -d
curl http://localhost:8000/health
```

---

## Troubleshooting

### Service Won't Start

**Port conflict:**
```bash
# Check what's using port 8000
./get-port.sh

# Use different port
echo "RAG_PORT=8001" > .env
docker-compose up -d
```

### No Search Results

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

### Poor Search Quality

**1. Use specific queries:**
- ❌ "python"
- ✅ "python async await error handling patterns"

**2. Increase results:**
```bash
curl -X POST http://localhost:8000/query \
  -d '{"text": "your query", "top_k": 10}'
```

**3. Try different embedding model** (edit `docker-compose.yml`):
```yaml
environment:
  - MODEL_NAME=all-mpnet-base-v2  # More accurate, slower
```

### MCP Not Working

**1. Verify RAG is running:**
```bash
curl http://localhost:8000/health
```

**2. Check MCP server:**
```bash
~/.vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude mcp list
# Should show: rag-kb - ✓ Connected
```

**3. Restart VSCode:**
- `Ctrl+Shift+P` → "Developer: Reload Window"

**4. Check VSCode logs:**
- VSCode → Output → Select "MCP" from dropdown

### Node.js Version Error

```bash
node --version  # Should be v14+

# Upgrade to v20 LTS (Ubuntu/Debian)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
```

---

## Advanced Configuration

### Auto-Sync Configuration

The system automatically watches for new and modified files in `knowledge_base/` and indexes them without requiring a restart. This happens in real-time with smart debouncing to handle bulk operations efficiently.

**How it works**:
- File watcher monitors `knowledge_base/` directory recursively
- Changes are collected for 10 seconds (debounce period) to batch operations
- After quiet period, all changes are indexed together
- Handles text editor save patterns, git operations, and bulk file copies gracefully

**Configuration** (via `.env`):
```bash
WATCH_ENABLED=true                  # Enable/disable auto-sync (default: true)
WATCH_DEBOUNCE_SECONDS=10.0         # Wait time after last change (default: 10.0)
WATCH_BATCH_SIZE=50                 # Max files per batch (default: 50)
```

**Use cases**:
- **Real-time**: Drop PDFs into `knowledge_base/books/` → indexed automatically
- **Git operations**: `git pull` new code → changes detected and indexed
- **Obsidian sync**: Notes update → immediately searchable
- **Bulk imports**: Copy 100 files → batched into efficient indexing

**To disable auto-sync** (e.g., for manual control):
```bash
echo "WATCH_ENABLED=false" >> .env
docker-compose restart rag-api
```

### Migration Between Machines

**Transfer database and files** (no re-indexing needed):

```bash
# On Machine A
cd rag-kb
tar -czf rag-migration.tar.gz knowledge_base/ data/ docker-compose.yml .env api/ mcp-server/ *.sh
scp rag-migration.tar.gz user@machine-b:~/

# On Machine B
tar -xzf rag-migration.tar.gz
cd rag-kb
docker-compose up -d
curl http://localhost:8000/health
```

### Embedding Models

v0.2.0+ supports multiple embedding models for different quality/speed trade-offs.

**Available Models:**

| Model | Dimensions | Quality | Speed | Use Case |
|-------|-----------|---------|-------|----------|
| all-MiniLM-L6-v2 (default) | 384 | Good | Fastest | Quick indexing, simple queries |
| **Arctic Embed 2.0-L** | 1024 | **Best** | Slower | Multi-domain KB, best retrieval |
| Arctic Embed 2.0-M | 768 | Excellent | Moderate | Balanced quality/speed |
| BGE-large-en-v1.5 | 1024 | Excellent | Moderate | Alternative high-quality option |
| BGE-base-en-v1.5 | 768 | Very Good | Fast | Lightweight high-quality |

**To use Arctic Embed 2.0-L (recommended for multi-domain knowledge bases):**

```bash
# Create/edit .env file
echo "MODEL_NAME=Snowflake/snowflake-arctic-embed-l-v2.0" > .env

# Rebuild with new model (requires re-indexing)
docker-compose down
rm data/knowledge_base.db
docker-compose up --build -d
```

**Performance Notes:**

- **Arctic Embed 2.0-L**: +45% better retrieval on MTEB benchmarks, ideal for diverse content (code + books + notes)
- **MiniLM-L6-v2**: Fastest option, good for single-domain or quick prototyping
- **Model download**: Arctic models are ~1.2GB (one-time download, cached thereafter)
- **Re-indexing required**: Different dimensions = incompatible database format

See [Migration Guide](docs/MIGRATION_v0.1_to_v0.2.md) for detailed model comparison and upgrade instructions.

### Chunking Configuration

Edit `api/config.py`:
```python
CHUNK_SIZE = 1000      # Characters per chunk
CHUNK_OVERLAP = 200    # Overlap between chunks
```

**Guidelines:**
- Smaller chunks (500-800): Better precision, more chunks
- Larger chunks (1500-2000): Better context, fewer chunks
- More overlap (300-400): Better continuity, more storage

### Backup Strategy

**Automated backups (cron):**
```bash
# Add to crontab
0 2 * * * tar -czf ~/backups/rag-$(date +\%Y\%m\%d).tar.gz /path/to/rag-kb/data/ /path/to/rag-kb/knowledge_base/
```

**Manual backup:**
```bash
# Full backup
tar -czf rag-backup-$(date +%Y%m%d).tar.gz data/ knowledge_base/

# Database only
cp data/knowledge_base.db ~/backups/kb-$(date +%Y%m%d).db
```

### Network Access

Edit `docker-compose.yml` to access from other devices:
```yaml
ports:
  - "0.0.0.0:8000:8000"  # Listen on all interfaces
```

Access via: `http://YOUR_LOCAL_IP:8000`

⚠️ **Security**: This exposes your knowledge base to your entire network.

### Performance Stats

**Expected performance:**

| Database Size | Docs | Chunks | Query Time | Storage |
|--------------|------|--------|-----------|---------|
| Small | <50 | <5k | <50ms | <20MB |
| Medium | 50-500 | 5k-50k | <100ms | 20-200MB |
| Large | 500-1000 | 50k-100k | <500ms | 200MB-1GB |

**Check stats:**
```bash
du -h data/knowledge_base.db
curl http://localhost:8000/health | jq
```

---

## API Reference

### POST /query

**Request:**
```json
{
  "text": "your search query",
  "top_k": 5,           // Number of results (default: 5)
  "threshold": 0.5      // Minimum score (optional)
}
```

**Response:**
```json
{
  "query": "your search query",
  "total_results": 5,
  "results": [
    {
      "content": "Relevant text chunk...",
      "source": "book-name.pdf",
      "page": 42,
      "score": 0.87
    }
  ]
}
```

### GET /health

```json
{
  "status": "healthy",
  "indexed_documents": 15,
  "total_chunks": 1234,
  "model": "sentence-transformers/all-MiniLM-L6-v2"
}
```

### POST /index

Force re-indexing:
```json
{
  "force_reindex": false  // true = re-index all
}
```

### GET /documents

Lists all indexed documents with metadata.

---

## Documentation

- **[OBSIDIAN_INTEGRATION.md](docs/OBSIDIAN_INTEGRATION.md)** - Obsidian vault ingestion
- **[CONTENT_SOURCES.md](docs/CONTENT_SOURCES.md)** - All supported content types
- **[WORKFLOW.md](docs/WORKFLOW.md)** - Code analysis workflows

---

## Roadmap

Future improvements under consideration:

**Advanced Embedding Models:**
- [Snowflake Arctic Embed 2](https://ollama.com/library/snowflake-arctic-embed2) - State-of-the-art retrieval quality
- [Google EmbeddingGemma](https://huggingface.co/google/embeddinggemma-300m) - More powerful embeddings
- [BGE/GTE models](https://huggingface.co/BAAI) - Latest generation embeddings

**Query Improvements:**
- Hybrid search (vector + keyword)
- Query expansion and rewriting
- Contextual chunk retrieval

**Integrations:**
- Additional IDE support (beyond VSCode)
- API authentication
- Multi-user support
- Cloud deployment guides

**Performance:**
- GPU acceleration for embeddings
- Streaming responses
- Incremental indexing
- Query caching

Contributions and suggestions welcome!

---

## Credits

Built with:
- [FastAPI](https://fastapi.tiangolo.com/) - Web framework
- [sqlite-vec](https://github.com/asg017/sqlite-vec) - Vector search in SQLite
- [sentence-transformers](https://www.sbert.net/) - Embedding models

---

## Support

- **Contact**: horoshi@katanaquant.com
- **Docs**: See `docs/` directory for detailed guides
- **Questions**: Check [Troubleshooting](#troubleshooting) first
