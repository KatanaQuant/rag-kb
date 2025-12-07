# RAG-KB Roadmap

## Current State

**Latest Version**: v2.2.4-beta
**Status**: Production-ready

### What's Working

- Document indexing: PDF, EPUB, Markdown, Code (JS/TS/Python/Go/C#/Java)
- Modular 4-stage pipeline: Extract, Chunk, Embed, Rerank
- MCP integration for AI coding assistants
- Security scanning (ClamAV, YARA)
- 92.3% search accuracy with 120x faster queries
- Self-healing database with maintenance API

### Current Stack

| Stage | Implementation |
|-------|----------------|
| Extraction | Docling |
| Chunking | HybridChunker |
| Embedding | Snowflake Arctic Embed L v2.0 |
| Vector Index | Vectorlite HNSW (ef=150) |
| Reranking | BGE-Reranker-Large (GPU recommended) |
| Query Features | Decomposition, Suggestions, Confidence Scores |

---

## Version History

| Version | Highlights |
|---------|-----------|
| **v2.2.4-beta** | All HNSW bugs fixed, 92.3% accuracy, maintenance API |
| **v2.2.0-beta** | Vectorlite HNSW (deprecated - critical bugs) |
| **v2.1.5-beta** | Breaking changes: kb/ rename, MCP stdio removed |
| **v1.9.1** | MCP HTTP transport, Docker optimization |
| **v1.7.11** | Batch encoding, Jupyter/Obsidian support |
| **v1.0.0** | Production release, async database |

> **Note**: v2.2.0-beta, v2.2.1, v2.2.2 are deprecated due to critical HNSW bugs. See [postmortem](postmortem-vectorlite-hnsw-complete.md).

---

## Current Release (v2.2.4-beta)

| Feature | Description | Benchmark |
|---------|-------------|-----------|
| Vectorlite HNSW | Persistent vector index with ef=150 | 92.3% accuracy, ~553ms queries |
| Maintenance API | 8 endpoints for database health | Verify, rebuild, repair |
| Query Decomposition | Break compound queries into sub-queries | +5.6% top score |
| Follow-up Suggestions | Return related queries with results | Based on result content |
| Confidence Scores | Expose reranker scores in API | `rerank_score` field |
| Thread-safe Storage | Unified VectorStore with RLock | No corruption under load |

---

## Next Release: v2.3.0

**Status**: Planning, awaiting GPU hardware

### pgvector Migration

Migrate from vectorlite to pgvector for production-grade durability:

| Feature | vectorlite | pgvector |
|---------|-----------|----------|
| ACID compliance | None | Full PostgreSQL |
| WAL/durability | None | Yes |
| Crash recovery | Manual rebuild | Automatic |
| Migration effort | - | Low (SQL similar) |

Current limitation: vectorlite lacks WAL, up to 5 min data loss on crash.

### GPU Acceleration (when hardware available)

| Feature | Current | With GPU |
|---------|---------|----------|
| Reranking | ~38s (disabled) | ~1-2s |
| Embeddings | Snowflake Arctic | Qwen3-8B (higher quality) |
| Chunking | Fixed-size | Semantic (embedding-based) |
| Media | Text only | Audio/video (Whisper) |

### Corpus Segmentation

- Auto-detect content type at ingest (books, blogs, code, notes)
- Query filtering by content type
- Weighted scoring (boost books, reduce blogs)

---

## Feature Backlog

### Contextual Embeddings

Per [Anthropic research](https://www.anthropic.com/news/contextual-retrieval), prepending context before embedding yields +35% accuracy improvement. Requires full re-indexing.

### v1.10.x Backport

Backport v2.2.4-beta improvements to v1.9.x for users who can't migrate:
- rank_bm25 (probabilistic keyword scoring)
- Title boosting
- RRF k=20 tuning

Expected improvement: 84.6% → ~88-92% accuracy.

### Other

| Feature | Description |
|---------|-------------|
| Domain-Aware Chunking | Specialized chunkers for legal, medical |
| Web UI | Visual library, drag-drop upload |
| Multi-Language | Non-English document support |
| Remote Processing | Cloud GPU/TPU offloading |

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

## Contributing

Have ideas? Open an issue or PR.
