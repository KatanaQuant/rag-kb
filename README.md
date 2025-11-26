# RAG-KB

[![Latest Release](https://img.shields.io/github/v/release/KatanaQuant/rag-kb?include_prereleases)](https://github.com/KatanaQuant/rag-kb/releases)
[![Docker](https://img.shields.io/badge/docker-ready-blue)](https://github.com/KatanaQuant/rag-kb)
[![License](https://img.shields.io/badge/license-Public%20Domain-green)](https://github.com/KatanaQuant/rag-kb)

**Personal knowledge base with semantic search.** Index books, code, and notes—query with natural language. 100% local.

**Current Version**: v1.6.0 ([Changelog](docs/RELEASES/))

---

## Features

- **Semantic Search** - Natural language queries across all documents
- **Multi-Format** - PDF, EPUB, Markdown, Code (Python/Java/TS/Go/C#), Jupyter, Obsidian
- **Security Scanning** - ClamAV, YARA, hash blacklist (auto-quarantine)
- **Concurrent Pipeline** - 4x throughput with parallel processing
- **MCP Integration** - Use with Claude Code in VSCode
- **100% Local** - No external APIs, complete privacy

See [docs/USAGE.md](docs/USAGE.md) for full feature details.

---

## Quick Start

```bash
# Clone and start
git clone https://github.com/KatanaQuant/rag-kb.git
cd rag-kb && git checkout v1.6.0

# Add your content
cp ~/Documents/*.pdf knowledge_base/books/

# Build and run
export DOCKER_BUILDKIT=1
docker-compose up --build -d

# Verify
curl http://localhost:8000/health
```

See [docs/QUICK_START.md](docs/QUICK_START.md) for detailed setup.

---

## Usage

```bash
# Query
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"text": "your question", "top_k": 5}'

# Health check
curl http://localhost:8000/health

# List documents
curl http://localhost:8000/documents
```

See [docs/USAGE.md](docs/USAGE.md) for all query methods.

---

## Documentation

| Guide | Description |
|-------|-------------|
| [QUICK_START.md](docs/QUICK_START.md) | Get running in 5 minutes |
| [USAGE.md](docs/USAGE.md) | Query methods, content ingestion |
| [API.md](docs/API.md) | Complete API reference |
| [CONFIGURATION.md](docs/CONFIGURATION.md) | Settings, models, performance |
| [MCP_INTEGRATION.md](docs/MCP_INTEGRATION.md) | Claude Code / VSCode setup |
| [SECURITY.md](docs/SECURITY.md) | Malware detection setup |
| [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Common issues |
| [DEVELOPMENT.md](docs/DEVELOPMENT.md) | Architecture, testing |
| [ROADMAP.md](docs/ROADMAP.md) | Project roadmap |
| [RELEASES/](docs/RELEASES/) | Version history |

---

## Architecture

```
VSCode/IDE → MCP Server (Node.js) → RAG API (FastAPI/Docker) → SQLite + vec0
                                            ↓
                                    knowledge_base/
```

1. **Ingestion**: Files → Extract → Chunk → Embed → Store
2. **Query**: Question → Embed → Vector Search → Results

---

## Updating

```bash
docker-compose down
git fetch --tags && git checkout v1.6.0
docker-compose build --no-cache
docker-compose up -d
```

Your data (`data/rag.db`, `knowledge_base/`) persists across updates.

---

## Support

- **Contact**: horoshi@katanaquant.com
- **GitHub**: [KatanaQuant/rag-kb](https://github.com/KatanaQuant/rag-kb)

---

## License

Public Domain
