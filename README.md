# RAG-KB

[![Latest Release](https://img.shields.io/github/v/release/KatanaQuant/rag-kb?include_prereleases)](https://github.com/KatanaQuant/rag-kb/releases)
[![Docker](https://img.shields.io/badge/docker-ready-blue)](https://github.com/KatanaQuant/rag-kb)
[![License](https://img.shields.io/badge/license-Public%20Domain-green)](https://github.com/KatanaQuant/rag-kb)

**Token-efficient semantic search for your personal knowledge base.** Query books, code, notes, and documents using natural language—runs 100% locally with no external APIs.

Built with FastAPI, sqlite-vec, and sentence-transformers.

**Current Version**: v0.7.0-alpha (see [Releases](https://github.com/KatanaQuant/rag-kb/releases) for changelog)

> **CPU-Only Build**: This project is optimized exclusively for CPU processing. No GPU required or supported. Large knowledge bases may take significant time to index:
>
> - **Small KB** (10-50 docs): Minutes to hours
> - **Medium KB** (100-500 docs): Hours to overnight
> - **Large KB** (500+ docs): Days to weeks
>
> **Performance Recommendation**: For English-only content, use `sentence-transformers/static-retrieval-mrl-en-v1` model for 100-400x faster processing with minimal quality trade-off. See [Embedding Models](#embedding-models) section.

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Claude Code Integration (VSCode)](#claude-code-integration-vscode)
- [Content Ingestion](#content-ingestion)
- [Usage](#usage)
- [Development & Testing](#development--testing)
- [Troubleshooting](#troubleshooting)
- [Advanced Configuration](#advanced-configuration)
- [Roadmap](#roadmap)

---

## Features

- **Semantic Chunking**: Token-aware chunking with HybridChunker preserves paragraphs, sections, and tables
- **Advanced PDF Processing**: Docling integration with OCR support, table extraction, and layout preservation
- **Resumable Processing**: Checkpoint-based processing resumes from last position after interruptions
- **Hybrid Search**: Combines vector similarity + keyword search for 10-30% better accuracy
- **Intelligent Caching**: LRU cache for instant repeat queries
- **Semantic Search**: Natural language queries across all your documents
- **100% Local**: No external APIs, complete privacy
- **Auto-Sync**: Automatically detects and indexes new/modified files in real-time
- **Multiple Formats**: PDF, DOCX (Docling + HybridChunker), Markdown, TXT (semantic chunking)
- **Token Efficient**: Returns only relevant chunks (~3-5K tokens vs 100K+ for full files)
- **Docker-Based**: Runs anywhere Docker runs
- **MCP Integration**: Built-in server for IDE integration
- **Portable**: Single SQLite database file - easy to backup and migrate

---

## Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────┐
│                         VSCode / IDE                         │
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
│  ├── books/              └── rag.db               │
│  ├── docs/                                                   │
│  └── notes/                                                  │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **Ingestion**: Files → Text Extraction → Chunking → Embedding → SQLite
2. **Query**: Question → Embedding → Vector Search → Top Results → Response
3. **MCP**: IDE queries via MCP → API processes → Results returned

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

# Checkout latest stable release
git checkout v0.5.0-alpha

# Optional: Change port if 8000 is in use
echo "RAG_PORT=8001" > .env

# Optional: Use faster model for English-only content (recommended)
echo "MODEL_NAME=sentence-transformers/static-retrieval-mrl-en-v1" >> .env
```

### Step 1: Add Content

The `knowledge_base/` directory is where you put your documents. It's **gitignored by default** to protect your personal/copyrighted content.

Create subdirectories and add your files:

```bash
# Create organization structure (optional)
mkdir -p knowledge_base/{books,notes,docs,papers}

# Add some content
cp ~/Documents/my-book.pdf knowledge_base/books/
cp ~/Documents/*.md knowledge_base/docs/
cp ~/notes/*.txt knowledge_base/notes/
```

The service automatically indexes all supported files when it starts.

**Note:** Your content stays local and private - it's never committed to git.

### Step 2: Start the Service

```bash
# Build and start
docker-compose up --build -d

# Wait ~30 seconds for indexing (longer for large knowledge bases)
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

## Claude Code Integration (VSCode)

Use your knowledge base directly with Claude Code in VSCode via MCP (Model Context Protocol).

**Note:** This integration requires the Claude Code extension for VSCode. The MCP server allows Claude to query your indexed documents automatically.

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

Or use the UI to approve when prompted.

**4. Reload VSCode:**
- `Ctrl+Shift+P` → "Developer: Reload Window"

### Verify Connection

```bash
~/.vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude mcp list
# Should show: rag-kb - Connected
```

### Using Claude Code with Your Knowledge Base

Claude can automatically query your knowledge base when relevant. However, by default, Claude may rely on its training data instead of querying your indexed documents. To ensure your knowledge base is used as the primary source:

**Method 1: Custom Instructions (Recommended)**

Create a custom instructions file to tell Claude to always check your RAG knowledge base first:

```bash
# Create .claude directory if it doesn't exist
mkdir -p .claude

# Create custom instructions file
cat > .claude/claude.md << 'EOF'
# Project Instructions

## Knowledge Base Priority

**CHECK THIS FIRST** for technical questions, APIs, frameworks, algorithms, or domain-specific knowledge. Search the personal knowledge base (books, notes, documentation) for relevant information using the MCP RAG tool. This is your PRIMARY source - always use it BEFORE relying on general knowledge.

When answering questions:
1. **Always query the MCP RAG knowledge base first** using `mcp__rag-kb__query_knowledge_base`
2. Use specific, detailed queries to find relevant chunks
3. Cite sources from the knowledge base when available
4. Only fallback to general knowledge if RAG returns no relevant results (score < 0.3)

## Example Workflow

User asks: "How does the authentication system work?"

1. Query RAG: `mcp__rag-kb__query_knowledge_base` with query "authentication system implementation"
2. Review returned chunks and provide answer based on indexed documentation
3. If no relevant chunks found, then use general knowledge with disclaimer

EOF
```

**Method 2: Explicit Prompts**

When asking questions, explicitly request RAG usage:

```
"Check the knowledge base for information about [topic]"
"Search indexed documents for [query]"
"What does my documentation say about [topic]?"
```

**Method 3: Agent Configuration**

For custom agents, include RAG priority in agent instructions:

```markdown
# .claude/agents.md

## research-agent

Always prioritize the MCP RAG knowledge base over general knowledge.

Before answering any technical question:
1. Query `mcp__rag-kb__query_knowledge_base` first
2. Only use general knowledge if RAG score < 0.3
```

**Verification**

To verify Claude is using your knowledge base:
- Look for MCP tool usage in the conversation (tool calls will show RAG queries)
- Ask Claude to cite sources - RAG results include file names
- Use specific queries that only your indexed documents would know

**Common Pitfall**

AI assistants are trained to be helpful and may answer from general knowledge even when RAG has better information. Always emphasize "check the knowledge base first" in your prompts or custom instructions.

---

## Content Ingestion

The RAG service automatically indexes files in `knowledge_base/` on startup. Supported formats are detected and processed accordingly.

### Supported Formats

**PDF & DOCX** (Docling + HybridChunker):
- **PDF** (`.pdf`): Docling 2.9.0 extraction with RapidOCR, table detection, and HybridChunker for token-aware semantic chunking
- **DOCX** (`.docx`): Docling 2.9.0 extraction with HybridChunker for token-aware semantic chunking

**Markdown & Text** (Semantic Chunking):
- **Markdown** (`.md`, `.markdown`): Semantic chunking with paragraph/section boundary preservation
- **Text** (`.txt`): Semantic chunking with natural boundary detection

**Why HybridChunker?** PDF/DOCX get advanced structure-aware chunking that preserves document semantics (tables, code blocks, sections) while filling chunks closer to the embedding model's token capacity (512 tokens). This provides 4x better token utilization and 40% fewer chunks compared to fixed-size chunking. See [docs/WHY_HYBRIDCHUNKER.md](docs/WHY_HYBRIDCHUNKER.md) for technical details.

### Simple Workflow

```bash
# 1. Add files
cp ~/Downloads/book.pdf knowledge_base/books/

# 2. Restart to index
docker-compose restart rag-api

# 3. Verify (wait ~30s for indexing)
curl http://localhost:8000/health
```

---

## Usage

### Via Claude Code (Recommended)

Ask Claude questions naturally in VSCode. Claude automatically decides when to query your knowledge base.

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
- Semantic chunking with HybridChunker (token-aware, document-aware boundaries) or fixed-size chunking with configurable overlap
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

### Testing New Models (Without Disrupting Production)

The test instance infrastructure allows safe experimentation on port 8001 while production runs on port 8000.

**Quick Test Workflow:**

```bash
# 1. Prepare clean test environment
./test-docling-instance.sh nuke  # Remove old test data (prompts for confirmation)

# 2. Add sample documents
cp knowledge_base/some-file.md knowledge_base_test/
# Or create fresh test content

# 3. Start test instance with new model
MODEL_NAME=sentence-transformers/static-retrieval-mrl-en-v1 ./test-docling-instance.sh start

# 4. Check health and stats
./test-docling-instance.sh health

# 5. Test queries
./test-docling-instance.sh query "your test question"

# 6. Compare with production
./test-docling-instance.sh compare

# 7. Monitor resource usage
docker stats rag-api-test --no-stream

# 8. Stop when done
./test-docling-instance.sh stop
```

**Test Instance Commands:**

```bash
./test-docling-instance.sh start    # Start on port 8001
./test-docling-instance.sh stop     # Stop test instance
./test-docling-instance.sh logs     # View logs
./test-docling-instance.sh health   # Check health status
./test-docling-instance.sh query "text"  # Run test query
./test-docling-instance.sh reindex  # Force reindex
./test-docling-instance.sh clean    # Remove test DB (keeps KB files)
./test-docling-instance.sh nuke     # Remove ALL test data
./test-docling-instance.sh compare  # Compare prod vs test
```

### Model Migration Workflow (Zero-Downtime)

Migrate to a new embedding model without disrupting the running production instance.

**Step-by-Step Migration:**

```bash
# 1. Test new model first (see above)
MODEL_NAME=sentence-transformers/static-retrieval-mrl-en-v1 ./test-docling-instance.sh start
./test-docling-instance.sh query "test queries..."
# Verify quality meets requirements

# 2. Backup production database
cp data/rag.db data/rag.db.backup-$(date +%Y%m%d)

# 3. Update production configuration
echo "MODEL_NAME=sentence-transformers/static-retrieval-mrl-en-v1" > .env

# 4. Rebuild production with new model
docker-compose down
rm data/rag.db  # New model requires fresh index
docker-compose up --build -d

# 5. Monitor indexing progress
docker-compose logs -f rag-api | grep -E "Indexed|chunks"

# 6. Verify health
curl http://localhost:8000/health | jq

# 7. Test queries
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"text": "test query", "top_k": 3}' | jq

# 8. Check resource usage
docker stats rag-api --no-stream
```

**Rollback if needed:**

```bash
# Stop new model
docker-compose down

# Restore backup
mv data/rag.db.backup-YYYYMMDD data/rag.db

# Revert configuration
git checkout .env  # Or manually set old MODEL_NAME

# Restart with old model
docker-compose up -d
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
- Bad: "python"
- Good: "python async await error handling patterns"

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
# Should show: rag-kb - Connected
```

**3. If shows "Failed to connect" - verify path is correct:**

After switching machines or moving the project, the MCP path may be outdated:

```bash
# Remove old configuration
~/.vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude mcp remove rag-kb

# Re-add with correct absolute path (replace with your actual path)
~/.vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude mcp add \
  --transport stdio \
  --scope user \
  rag-kb \
  --env RAG_API_URL=http://localhost:8000 \
  -- node /media/veracrypt1/CODE/rag-kb/mcp-server/index.js

# Verify connection
~/.vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude mcp list
```

**4. Restart VSCode:**
- `Ctrl+Shift+P` → "Developer: Reload Window"

**5. Check VSCode logs:**
- VSCode → Output → Select "MCP" from dropdown

### Node.js Version Error

```bash
node --version  # Should be v14+

# Upgrade to v20 LTS (Ubuntu/Debian)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
```

### Slow Indexing Performance

**CPU-only processing is slow by design.** For faster indexing:

**Option 1: Use faster embedding model (recommended for English content)**
```bash
# Edit .env
echo "MODEL_NAME=sentence-transformers/static-retrieval-mrl-en-v1" > .env

# Rebuild
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
- See [Resource Limits](#resource-limits-recommended) section

---

## Advanced Configuration

### Hardware Requirements

**CPU-Only (Production-Ready):**
- RAM: 4-8GB minimum (16GB recommended for large KB)
- CPU: 2+ cores (4+ recommended)
- Storage: 500MB + (2x knowledge base size)
- Processing: 10-500 docs/hour depending on format and model choice

**Recommended Setup:**
- 8-16 CPU cores for faster parallel processing
- 16GB RAM for comfortable large knowledge base indexing
- SSD storage for faster database I/O

**Note:** This project is CPU-only by design. No GPU support is planned.

### Configuration via .env

RAG-KB uses a two-tier configuration approach:

1. **docker-compose.yml**: Provides sensible defaults for all settings
2. **.env file**: Optional overrides for customization (you only specify what you want to change)

**How it works:**
- Docker Compose automatically loads `.env` from the project root
- Any variable in `.env` overrides the corresponding default in `docker-compose.yml`
- If `.env` doesn't exist or a variable is missing, the default is used

**Example .env file:**
```bash
# Only override what you need to change
MODEL_NAME=Snowflake/snowflake-arctic-embed-l-v2.0
RAG_PORT=8001
MAX_MEMORY=8G
```

All other settings (batch size, cache config, chunking, etc.) will use the defaults from `docker-compose.yml`.

**See `.env.example` for all available options with documentation.**

### Resource Limits (Recommended)

To prevent system overload during large indexing operations, RAG-KB includes resource caps:

**Configuration** (via `.env`):
```bash
MAX_CPUS=2.0          # Max CPU cores (default: 2.0)
MAX_MEMORY=4G         # Max memory usage (default: 4G)
BATCH_SIZE=5          # Files per batch (default: 5)
BATCH_DELAY=0.5       # Delay between batches in seconds (default: 0.5)
```

**How it works**:
- Docker resource limits prevent container from exceeding CPU/memory caps
- Batch processing adds delays every N files to prevent resource spikes
- Ideal for laptops and devices with limited resources

**Adjust for your system**:
```bash
# Low-end device (2GB RAM, 2 cores)
echo "MAX_MEMORY=2G" >> .env
echo "MAX_CPUS=1.0" >> .env
echo "BATCH_SIZE=3" >> .env

# High-end device (16GB RAM, 8 cores)
echo "MAX_MEMORY=8G" >> .env
echo "MAX_CPUS=4.0" >> .env
echo "BATCH_SIZE=10" >> .env
echo "BATCH_DELAY=0.1" >> .env

# Rebuild
docker-compose up --build -d
```

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
- **Updates**: Modify existing files → changes detected and reindexed
- **Bulk imports**: Copy 100 files → batched into efficient indexing

**To disable auto-sync** (e.g., for manual control):
```bash
echo "WATCH_ENABLED=false" >> .env
docker-compose restart rag-api
```

### Hybrid Search Configuration

The system uses **Reciprocal Rank Fusion (RRF)** to combine vector similarity search with FTS5 keyword search, providing 10-30% better accuracy for technical queries.

**How it works**:
- Vector search finds semantically similar content
- Keyword search (FTS5) finds exact term matches
- RRF algorithm merges and ranks results
- Automatic fallback to vector-only if keyword search fails

**Benefits**:
- Better recall for technical terms, acronyms, and specific terminology
- Improved precision when query contains both concepts and keywords
- Robust to varying query styles (natural language vs. keyword-based)

Hybrid search is **enabled by default** with no configuration needed. It automatically activates when both vector and keyword indexes are available.

**To disable hybrid search** (fallback to vector-only):
```python
# In api/main.py, modify QueryExecutor._search():
use_hybrid=False  # Change from True to False
```

### Query Caching Configuration

LRU (Least Recently Used) cache for query results, providing instant responses for repeat queries.

**Configuration** (via `.env`):
```bash
CACHE_ENABLED=true                  # Enable/disable caching (default: true)
CACHE_MAX_SIZE=100                  # Maximum cached queries (default: 100)
```

**How it works**:
- First query: Normal search (vector + keyword fusion)
- Repeat query: Instant cache hit (0ms latency)
- Cache eviction: Least recently used entries removed when full
- Cache keys: Based on query text, top_k, and threshold

**Benefits**:
- ~1000x faster for repeat queries
- Reduced embedding computation
- Lower memory usage vs. full result caching

**Use cases**:
- Development/debugging: Repeated test queries
- Multi-user scenarios: Common questions cached
- Interactive exploration: Refining queries with same base text

**To increase cache size** (e.g., for high-traffic scenarios):
```bash
echo "CACHE_MAX_SIZE=500" >> .env
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

v0.2.0+ supports multiple embedding models for different quality/speed/resource trade-offs.

**Available Models:**

| Model | Dimensions | Memory | MTEB Score | Speed | Use Case |
|-------|-----------|--------|------------|-------|----------|
| all-MiniLM-L6-v2 | 384 | ~80MB | Good | Very Fast | Quick prototyping, simple queries |
| **static-retrieval-mrl-en-v1** | 1024 | **~400MB** | ~87% of mpnet | **100-400x faster** | **CPU-optimized, English-only, recommended** |
| Arctic Embed 2.0-M | 768 | ~450MB | 55.4 (Retrieval) | Very Fast | Balanced quality/speed |
| Arctic Embed 2.0-L | 1024 | ~1.2GB | **55.6 (Retrieval)** | Fast | Best retrieval quality, multilingual |
| BGE-base-en-v1.5 | 768 | ~450MB | Very Good | Fast | Lightweight alternative |
| BGE-large-en-v1.5 | 1024 | ~1.3GB | 64.2 (Avg) / 54.3 (Retrieval) | Medium | Alternative high-quality option |

**Recommended Configurations:**

**CPU-Optimized (Recommended for v0.4):**
```bash
# 66% less memory, 100-400x faster, English-only, 13% quality trade-off
MODEL_NAME=sentence-transformers/static-retrieval-mrl-en-v1
```

**Production (Multilingual):**
```bash
# Best retrieval quality, multilingual, slower processing
MODEL_NAME=Snowflake/snowflake-arctic-embed-l-v2.0
```

**To change models:**

```bash
# Create/edit .env file
echo "MODEL_NAME=sentence-transformers/static-retrieval-mrl-en-v1" > .env

# Rebuild with new model (requires re-indexing)
docker-compose down
rm data/rag.db
docker-compose up --build -d
```

**Model Tradeoffs:**

| Factor | static-retrieval-mrl (Recommended) | Arctic 2.0-L |
|--------|-----------------------------------|--------------|
| **Quality** | Good (~87% of mpnet) | Excellent (55.6 MTEB Retrieval) |
| **Speed** | 100-400x faster | Fast |
| **Memory** | 400MB (66% less) | 1.2GB |
| **Multilingual** | English only | Yes (100+ languages) |
| **Use Case** | CPU builds, English content | Multilingual, GPU builds |

**Performance Notes:**

- **static-retrieval-mrl**: Static embeddings (no neural network inference), extreme speed, minimal memory, ideal for CPU-only deployments
- **Arctic Embed 2.0-L**: Best-in-class retrieval (55.6 MTEB), multilingual support, ideal for diverse content with GPU acceleration
- **Model download**: Models download once and are cached thereafter
- **Re-indexing required**: Different dimensions = incompatible database format

For model testing and migration workflows, see [Development & Testing](#development--testing).

### Chunking Configuration

**HybridChunker (PDF/DOCX - Recommended):**

The system uses HybridChunker for PDF and DOCX files, providing token-aware semantic chunking that preserves document structure while maximizing embedding model capacity utilization.

**Configuration** (via `.env`):
```bash
SEMANTIC_CHUNKING=true        # Enable HybridChunker (default: true)
CHUNK_MAX_TOKENS=512          # Match embedding model capacity (default: 512)
USE_DOCLING=true              # Required for HybridChunker (default: true)
```

**Why HybridChunker?**
- **4x better token utilization**: Fills chunks closer to 512-token embedding capacity (vs ~79 tokens with fixed-size)
- **40% fewer chunks**: More efficient storage and faster retrieval
- **Preserves semantics**: Keeps tables, code blocks, paragraphs, and sections intact
- **Better retrieval quality**: Complete concepts improve relevance scores by 10-15%

**Real-world example** (272-page technical book):
- HybridChunker: 372 chunks averaging 324 tokens each
- Fixed-size: ~1,623 chunks averaging 79 tokens each
- Result: Same content, 77% fewer chunks, 4x better token usage

**Markdown/Text Chunking:**

For Markdown and text files, the system uses semantic chunking with boundary detection:
```python
# Edit api/config.py for fallback chunking behavior
CHUNK_SIZE = 1000      # Characters per chunk
CHUNK_OVERLAP = 200    # Overlap between chunks
```

**For detailed technical explanation**, see [docs/WHY_HYBRIDCHUNKER.md](docs/WHY_HYBRIDCHUNKER.md)

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
cp data/rag.db ~/backups/kb-$(date +%Y%m%d).db
```

### Network Access

Edit `docker-compose.yml` to access from other devices:
```yaml
ports:
  - "0.0.0.0:8000:8000"  # Listen on all interfaces
```

Access via: `http://YOUR_LOCAL_IP:8000`

**Security**: This exposes your knowledge base to your entire network.

### Performance Stats

**Expected performance:**

| Database Size | Docs | Chunks | Query Time | Storage |
|--------------|------|--------|-----------|---------|
| Small | <50 | <5k | <50ms | <20MB |
| Medium | 50-500 | 5k-50k | <100ms | 20-200MB |
| Large | 500-1000 | 50k-100k | <500ms | 200MB-1GB |

**Check stats:**
```bash
du -h data/rag.db
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

**Semantic Chunking Expansion:**
- Extend HybridChunker support to Markdown and TXT files
- Custom conversion pipelines for code repositories (preserve function/class boundaries)
- Obsidian vault integration (preserve wiki links, backlinks, and note structure)
- Jupyter notebook support (preserve code cells and markdown cells separately)

**Document Ingestion:**
- Advanced PDF parsing enhancements (PyMuPDF4LLM, Marker-PDF integration)

**Embedding Models:**
- Google Gemma2 - High performance, low cost alternative
- BGE/GTE models - Latest generation embeddings
- Improved CPU-optimized models

**Performance & Resource Management:**
- Streaming responses
- Distributed processing
- Advanced CPU optimization

**Query Improvements:**
- Query expansion and rewriting
- Contextual chunk retrieval
- Better ranking algorithms

**Integrations:**
- Additional IDE support (beyond VSCode)
- API authentication
- Multi-user support
- Cloud deployment guides

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
