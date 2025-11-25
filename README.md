# RAG-KB

[![Latest Release](https://img.shields.io/github/v/release/KatanaQuant/rag-kb?include_prereleases)](https://github.com/KatanaQuant/rag-kb/releases)
[![Docker](https://img.shields.io/badge/docker-ready-blue)](https://github.com/KatanaQuant/rag-kb)
[![License](https://img.shields.io/badge/license-Public%20Domain-green)](https://github.com/KatanaQuant/rag-kb)

**Token-efficient semantic search for your personal knowledge base.** Query books, code, notes, and documents using natural language—runs 100% locally with no external APIs.

Built with FastAPI, sqlite-vec, and sentence-transformers.

**Current Version**: v1.0.0 - Production Ready (see [Releases](https://github.com/KatanaQuant/rag-kb/releases) for changelog)

---

## Features

- **Python 3.13**: Modern Python for 5-10% better performance and improved debugging (v0.14.0+)
- **Database Maintenance**: Duplicate detection and cleanup webhooks for database health (v0.14.0+)
- **Queue Duplicate Detection**: Prevents redundant file processing with smart tracking (v0.14.0+)
- **Structured Progress Logging**: Real-time progress tracking with timing, rates, and ETA across all pipeline stages (v0.13.0+)
- **Periodic Heartbeat**: Background updates every 60s for long-running operations (v0.13.0+)
- **Configurable Storage**: Choose your knowledge base location via KNOWLEDGE_BASE_PATH (v0.12.0+)
- **File Type Validation**: Magic byte verification prevents malicious files from being indexed (v0.12.0+)
- **Configuration Validation**: Validates all settings on startup with clear error messages (v0.12.0+)
- **Semantic Chunking**: Token-aware chunking with HybridChunker preserves paragraphs, sections, and tables
- **Advanced PDF Processing**: Docling integration with OCR support, table extraction, and layout preservation
- **AST-Based Code Chunking**: Intelligent code parsing for Python, Java, TypeScript, C#, JavaScript, Go and more
- **Jupyter Notebook Support**: Cell-aware chunking with AST parsing for 160+ programming languages
- **Obsidian Graph-RAG**: Full knowledge graph support for Obsidian vaults with bidirectional linking
- **Concurrent Processing Pipeline**: 4x throughput improvement with parallel embedding workers (v0.11.0+)
- **Priority Queue System**: HIGH/NORMAL priority levels for urgent files and data integrity operations
- **Operational Controls**: Pause/resume/clear queue, fast-track files, orphan repair via API
- **Resumable Processing**: Checkpoint-based processing resumes from last position after interruptions
- **Hybrid Search**: Combines vector similarity + keyword search for 10-30% better accuracy
- **Intelligent Caching**: LRU cache for instant repeat queries
- **Document Management API**: Delete documents with full cleanup, search by pattern
- **Clean Logging**: Silent skips, milestone-based progress (25/50/75/100%), reduced noise
- **Semantic Search**: Natural language queries across all your documents
- **100% Local**: No external APIs, complete privacy
- **Auto-Sync**: Automatically detects and indexes new/modified files in real-time
- **Multiple Formats**: PDF, EPUB, DOCX, Markdown, Code (Python/Java/TS/JS/C#/Go), Jupyter notebooks, Obsidian vaults
- **Token Efficient**: Returns only relevant chunks (~3-5K tokens vs 100K+ for full files)
- **Docker-Based**: Runs anywhere Docker runs
- **MCP Integration**: Built-in server for IDE integration
- **Portable**: Single SQLite database file - easy to backup and migrate
- **Production-Ready Architecture**: POODR refactoring (25+ focused classes, dependency injection, duck typing)

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
│  • 3-Stage Concurrent Pipeline (v0.11.0+)                    │
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
- **Node.js v14+** (for MCP server - optional)
- **Git**

### Get Running in 3 Steps

```bash
# 1. Clone and setup
git clone https://github.com/KatanaQuant/rag-kb.git
cd rag-kb
git checkout v1.0.0

# 2. Add your documents
mkdir -p knowledge_base/{books,notes,docs}
cp ~/Documents/*.pdf knowledge_base/books/
cp ~/projects/my-code ./knowledge_base/

# 3. Enable BuildKit and start the service (recommended for faster builds)
export DOCKER_BUILDKIT=1
docker-compose up --build -d

# Verify (wait ~30s for indexing)
curl http://localhost:8000/health
```

> **Tip**: Add `export DOCKER_BUILDKIT=1` to your `~/.bashrc` or `~/.zshrc` to enable BuildKit permanently for 60% faster rebuilds!

**For detailed setup instructions**, see [docs/QUICK_START.md](docs/QUICK_START.md)

### Performance Note

> **CPU-Only Build**: This project is optimized exclusively for CPU processing. No GPU required or supported.
>
> **Indexing Time**:
> - Small KB (10-50 docs): Minutes to hours
> - Medium KB (100-500 docs): Hours to overnight
> - Large KB (500+ docs): Days to weeks
>
> **Performance Tip**: For English-only content, use `sentence-transformers/static-retrieval-mrl-en-v1` model for 100-400x faster processing. See [docs/CONFIGURATION.md](docs/CONFIGURATION.md#embedding-models).

### Build Performance

> **Optimized Docker Builds** (v0.13.0+)
>
> The Dockerfile uses multiple optimizations for faster builds and smaller images:
>
> **1. BuildKit Cache Mounts** (60% faster rebuilds):
> ```bash
> # Enable BuildKit (recommended)
> export DOCKER_BUILDKIT=1
> docker-compose build
>
> # Or add to your shell profile for permanent use
> echo 'export DOCKER_BUILDKIT=1' >> ~/.bashrc  # or ~/.zshrc
> ```
>
> **2. Multi-Stage Build** (40-60% smaller images):
> - Separates build and runtime environments
> - Final image: ~2.0-2.5 GB (vs ~3.5 GB before)
> - Removes build tools (gcc, g++, make) from production
> - More secure runtime environment
>
> **Build Times**:
> - First build: 7-10 minutes
> - Rebuilds with BuildKit: 2-4 minutes (60% faster!)
> - Rebuilds without BuildKit: 7-10 minutes
>
> **Image Size**:
> - With multi-stage: ~2.0-2.5 GB
> - Without multi-stage: ~3.5 GB
>
> **Requirements**: Docker 18.09+ (most systems already have this)
>
> **Cache Management**: BuildKit caches take ~1-2GB disk space. To clear if needed:
> ```bash
> docker builder prune
> ```

---

## How to Update

### Updating to a New Version

Follow these steps to update your existing RAG-KB installation:

```bash
# 1. Navigate to your RAG-KB directory
cd /path/to/rag-kb

# 2. Stop the running containers
docker-compose down

# 3. Fetch latest changes
git fetch --tags

# 4. Checkout the desired version
git checkout v1.0.0

# 5. Rebuild Docker image (required for dependency/system updates)
docker-compose build --no-cache

# 6. Start the service
docker-compose up -d

# 7. Verify the update
curl http://localhost:8000/health
```

### Important Notes

**Data Persistence**: Your indexed documents and database are safe. They are stored in:
- `./data/rag.db` - Vector database (persists across updates)
- `./knowledge_base/` - Your documents (unchanged)

**When to Rebuild**:
- **Always rebuild** when updating to a new version (system dependencies may change)
- Use `--no-cache` flag to ensure clean build
- The rebuild takes 5-15 minutes depending on your system

**Configuration Changes**:
- Check the release notes for new configuration options
- Review `.env.example` for new settings
- Your existing `.env` file will be preserved

**Breaking Changes**:
- Minor version updates (v0.11.0 → v0.12.0) should have no breaking changes
- Always read the release notes before updating
- Major version updates (v0.x → v1.0) may require migration steps

**Developing Without Downtime**:
To test changes, upgrades, or new features while keeping your instance running for daily use across your network, see [Development Without Disrupting Your Running Instance](docs/DEVELOPMENT.md#development-without-disrupting-your-running-instance) in DEVELOPMENT.md

### Version Selection

**Latest Stable Release**:
```bash
git checkout $(git describe --tags --abbrev=0)
```

**Specific Version**:
```bash
git checkout v1.0.0
```

**Development Branch** (not recommended for production):
```bash
git checkout main
```

### Troubleshooting Updates

**Issue**: Containers won't start after update
```bash
# Force clean rebuild
docker-compose down
docker-compose build --no-cache --pull
docker-compose up -d
```

**Issue**: Port conflicts
```bash
# Check if port 8000 is in use
docker ps -a
# Update RAG_PORT in .env if needed
```

**Issue**: Permission errors
```bash
# Fix data directory permissions
sudo chown -R $USER:$USER ./data ./knowledge_base
```

For more troubleshooting, see [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)

---

## Usage

### Query Your Knowledge Base

**Via Command Line**:
```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"text": "your question here", "top_k": 5}'
```

**Via Python**:
```python
import requests

response = requests.post("http://localhost:8000/query", json={
    "text": "your question here",
    "top_k": 5
})
print(response.json())
```

**Via Claude Code (VSCode)**: See [docs/CLAUDE_CODE_INTEGRATION.md](docs/CLAUDE_CODE_INTEGRATION.md)

**For complete usage guide**, see [docs/USAGE.md](docs/USAGE.md)

---

## API Reference

### Core Endpoints

**POST /query** - Semantic search
```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"text": "your query", "top_k": 5}'
```

**GET /health** - System status
```bash
curl http://localhost:8000/health
```

**GET /documents** - List indexed documents
```bash
curl http://localhost:8000/documents
```

### Operational Controls (v0.11.0+)

**Queue Management**:
- `POST /indexing/pause` - Pause processing
- `POST /indexing/resume` - Resume processing
- `POST /indexing/clear` - Clear pending queue
- `GET /queue/jobs` - Monitor queue status

**Priority Processing**:
- `POST /indexing/priority/{path}` - Fast-track file
- `GET /indexing/status` - Check progress

**Maintenance** (v0.14.0+):
- `POST /maintenance/check-duplicates` - Detect duplicate chunks
- `POST /maintenance/cleanup-duplicates` - Remove duplicates
- `POST /repair-orphans` - Repair orphaned files
- `DELETE /document/{path}` - Remove document
- `POST /index` - Force reindex

**For complete API documentation with examples**, see [docs/OPERATIONAL_CONTROLS.md](docs/OPERATIONAL_CONTROLS.md)

---

## Documentation

Comprehensive guides for all aspects of RAG-KB:

### Getting Started
- **[QUICK_START.md](docs/QUICK_START.md)** - Get up and running in 5 minutes
- **[CLAUDE_CODE_INTEGRATION.md](docs/CLAUDE_CODE_INTEGRATION.md)** - Use with Claude Code in VSCode

### User Guides
- **[USAGE.md](docs/USAGE.md)** - Content ingestion, query methods, operational controls
- **[CONFIGURATION.md](docs/CONFIGURATION.md)** - Hardware requirements, embedding models, performance tuning
- **[TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)** - Common issues and solutions

### Advanced Topics
- **[OPERATIONAL_CONTROLS.md](docs/OPERATIONAL_CONTROLS.md)** - Complete API reference with queue management
- **[DEVELOPMENT.md](docs/DEVELOPMENT.md)** - Architecture, testing, developing without downtime
- **[OBSIDIAN_INTEGRATION.md](docs/OBSIDIAN_INTEGRATION.md)** - Obsidian vault ingestion
- **[CONTENT_SOURCES.md](docs/CONTENT_SOURCES.md)** - All supported content types
- **[WORKFLOW.md](docs/WORKFLOW.md)** - Code analysis workflows
- **[WHY_HYBRIDCHUNKER.md](docs/WHY_HYBRIDCHUNKER.md)** - Technical deep-dive on semantic chunking

### Project Information
- **[ROADMAP.md](docs/ROADMAP.md)** - Project roadmap and version history

---

## Roadmap

See [docs/ROADMAP.md](docs/ROADMAP.md) for detailed roadmap.

**Highlights for future releases**:
- Semantic chunking expansion to Markdown and TXT files
- Additional language support (Rust, C++, etc.)
- Advanced PDF parsing enhancements
- Query expansion and rewriting
- Streaming responses
- Multi-user support

---

## Credits

Built with:
- [FastAPI](https://fastapi.tiangolo.com/) - Web framework
- [sqlite-vec](https://github.com/asg017/sqlite-vec) - Vector search in SQLite
- [sentence-transformers](https://www.sbert.net/) - Embedding models
- [Docling](https://github.com/DS4SD/docling) - Document extraction
- [tree-sitter](https://tree-sitter.github.io/) - AST-based code parsing

---

## Support

- **Contact**: horoshi@katanaquant.com
- **Documentation**: See `docs/` directory for detailed guides
- **Issues**: Check [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) first
- **GitHub**: [KatanaQuant/rag-kb](https://github.com/KatanaQuant/rag-kb)

---

## License

Public Domain. See repository for details.
