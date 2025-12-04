# RAG-KB Roadmap

## Current State

**Latest Version**: v2.2.0-beta
**Status**: Production-ready

### What's Working

- Document indexing: PDF, EPUB, Markdown, Code (JS/TS/Python/Go/C#/Java)
- Modular 4-stage pipeline: Extract, Chunk, Embed, Rerank
- MCP integration for AI coding assistants
- Security scanning (ClamAV, YARA)
- 896 tests passing

### Current Stack

| Stage | Implementation |
|-------|----------------|
| Extraction | Docling |
| Chunking | HybridChunker |
| Embedding | Snowflake Arctic Embed L v2.0 |
| Vector Index | Vectorlite HNSW |
| Reranking | BGE-Reranker-Large (GPU recommended) |
| Query Features | Decomposition, Suggestions, Confidence Scores |

---

## Version History

| Version | Highlights |
|---------|-----------|
| **v2.2.0-beta** | Vectorlite HNSW, query decomposition, confidence scores |
| **v2.1.5-beta** | Breaking changes: kb/ rename, MCP stdio removed |
| **v1.9.1** | MCP HTTP transport, Docker optimization |
| **v1.7.11** | Batch encoding, Jupyter/Obsidian support |
| **v1.0.0** | Production release, async database |

---

## Next Release: v2.3.0

**Status**: Planning, awaiting GPU hardware

### Planned Features

| Feature | Description |
|---------|-------------|
| GPU Embedding | Higher quality embeddings (Qwen3-8B) |
| GPU Reranking | Accelerated relevance scoring (~20s → <1s) |
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

## Current Release (v2.2.0-beta)

| Feature | Description | Benchmark |
|---------|-------------|-----------|
| Vectorlite HNSW | Persistent vector index | ~10ms queries (was ~2s) |
| Query Decomposition | Break compound queries into sub-queries | +5.6% top score |
| Follow-up Suggestions | Return related queries with results | Based on result content |
| Confidence Scores | Expose reranker scores in API | `rerank_score` field |

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
