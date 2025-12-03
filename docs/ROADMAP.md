# RAG-KB Roadmap

## Current State

**Latest Version**: v2.1.5-beta
**Status**: Production-ready

### What's Working

- Document indexing: PDF, EPUB, Markdown, Code (JS/TS/Python/Go/C#/Java)
- Modular 4-stage pipeline: Extract, Chunk, Embed, Rerank
- MCP integration for AI coding assistants
- Security scanning (ClamAV, YARA)
- 888 tests passing

### Current Stack

| Stage | Implementation |
|-------|----------------|
| Extraction | Docling |
| Chunking | HybridChunker |
| Embedding | Snowflake Arctic Embed L v2.0 |
| Reranking | BGE-Reranker-Large (CPU) |

---

## Version History

| Version | Highlights |
|---------|-----------|
| **v2.1.5-beta** | Breaking changes: kb/ rename, MCP stdio removed |
| **v1.9.1** | MCP HTTP transport, Docker optimization |
| **v1.7.11** | Batch encoding, Jupyter/Obsidian support |
| **v1.0.0** | Production release, async database |

---

## Next Release: v2.0.0

**Status**: Planning complete, awaiting GPU hardware

### Planned Features

| Feature | Description |
|---------|-------------|
| GPU Embedding | Higher quality embeddings (Qwen3-8B) |
| GPU Reranking | Accelerated relevance scoring |
| Semantic Chunking | Embedding-based chunk boundaries |
| Audio/Video | Whisper transcription |

---

## IDE Integration

RAG-KB integrates with AI assistants via MCP (Model Context Protocol).

| Assistant | Setup |
|-----------|-------|
| Claude Code | See [MCP.md](MCP.md) |
| OpenAI Codex | See [MCP.md](MCP.md) |
| Google Gemini | See [MCP.md](MCP.md) |
| Amp (Sourcegraph) | See [MCP.md](MCP.md) |

### MCP Tools

- `query_kb` - Semantic search
- `list_indexed_documents` - Browse indexed files
- `get_kb_stats` - Knowledge base statistics

---

## Feature Backlog

| Feature | Description |
|---------|-------------|
| Domain-Aware Chunking | Specialized chunkers for legal, medical |
| Web UI | Visual library, drag-drop upload |
| Multi-Language | Non-English document support |
| Remote Processing | Cloud GPU/TPU offloading |

---

## Contributing

Have ideas? Open an issue or PR.
