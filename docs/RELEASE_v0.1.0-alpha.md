## 🎉 First Public Release

This is the initial public release of **rag-kb** (RAG Knowledge Base) - a local-first, privacy-focused semantic search system for your personal knowledge base.

## Features

- **Semantic Search**: Natural language queries across your documents
- 🔒 **Privacy First**: 100% local operation, no cloud dependencies
- 📚 **Multi-Format Support**: PDF, Markdown, TXT, DOCX, Obsidian vaults, code
- 🐳 **Docker Deployment**: Consistent environment, easy setup
- 🔌 **Claude Code Integration**: MCP server for seamless workflow
- ⚡ **Fast Indexing**: ~10-20 pages/sec for PDFs, ~100KB/sec for text
- **Well Tested**: 33+ unit tests, ~95% code quality compliance

## Technical Stack

- **Backend**: FastAPI (Python)
- **Database**: SQLite with sqlite-vec extension
- **Embeddings**: sentence-transformers/all-MiniLM-L6-v2 (384 dimensions)
- **Deployment**: Docker + Docker Compose
- **Integration**: MCP server for Claude Code (Node.js)

## Quick Start

```bash
git clone https://github.com/KatanaQuant/rag-kb.git
cd rag-kb
docker-compose up -d
```

See [README.md](https://github.com/KatanaQuant/rag-kb/blob/main/README.md) for full setup instructions.

## Known Issues

- Manual MCP server startup required after VSCode restart (workaround documented)
- No real-time indexing - requires container restart for new documents

## What's Next

See the [Roadmap](https://github.com/KatanaQuant/rag-kb#roadmap) for upcoming features including:
- Advanced embedding models (Arctic Embed 2, EmbeddingGemma, BGE)
- Hybrid search (vector + keyword)
- GPU acceleration
- Additional IDE support

## Status

**Early Alpha**: This is an early development release. Breaking changes expected in future releases.

## Support

- **Issues**: https://github.com/KatanaQuant/rag-kb/issues
- **Email**: horoshi@katanaquant.com
