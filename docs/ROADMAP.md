# RAG-KB Roadmap

This document outlines the journey from v1.x to v2.0.0 and beyond.

## Table of Contents

- [Current State](#current-state)
- [Version History](#version-history)
- [Journey to v2.0.0](#journey-to-v200)
  - [v1.7.x - Performance & Polish](#v17x---performance--polish)
  - [v1.8.x - Content Expansion](#v18x---content-expansion)
  - [v1.9.x - Pre-v2 Stabilization](#v19x---pre-v2-stabilization)
  - [v2.0.0 - GPU & Advanced Features](#v200---gpu--advanced-features)
- [IDE Integration](#ide-integration)
- [Feature Backlog](#feature-backlog)
- [Decision Log](#decision-log)
- [Contributing](#contributing)

---

## Current State

**Latest Release**: v1.7.11

**What's Working**:
- Production-ready document indexing (PDF, EPUB, Markdown, Code)
- Concurrent 3-stage pipeline (Chunk -> Embed -> Store)
- Batch encoding for 10-50x embedding throughput
- Pre-stage skip check (efficient queue management)
- Async API (responsive during heavy indexing)
- Comprehensive security scanning (ClamAV, YARA, hash blacklist)
- Self-healing startup (auto-repair database issues)
- REST API for security/maintenance operations
- Clean architecture: `pipeline/` (background) + `operations/` (API)
- Single-file security scan endpoint
- MCP integration for Claude, Codex, and Gemini
- Chunking quality metrics (boundary coherence, retrieval accuracy)
- 735 tests passing

---

## Version History

| Version | Highlights |
|---------|-----------|
| **v1.7.11** | Batch encoding, pipeline fixes, Jupyter/Obsidian chunking, JS/TSX support, quality metrics |
| **v1.6.7** | Security bug fix (validation_action config), single-file scan endpoint |
| **v1.0.0** | Production release, async database, security scanning |
| **v0.16.0** | Async database migration (API <100ms during indexing) |
| **v0.15.0** | POODR refactoring (main.py 684→89 LOC) |
| **v0.13.0** | Docker optimization, progress logging |
| **v0.11.0** | Concurrent pipeline, Go support |

---

## Journey to v2.0.0

```
v1.7.11 (CURRENT) - Production-ready, CPU-optimized
    │
    ├── v1.8.x - Infrastructure & Tooling
    │   ├─ Docker build optimization (BuildKit, pre-built base images)
    │   ├─ MCP network deployment (remote access)
    │   └─ Performance profiling and metrics
    │
    ├── v1.9.x - Pre-v2 Stabilization (optional)
    │   ├─ Production hardening
    │   ├─ Bug fixes and polish
    │   └─ Documentation updates
    │
    └── v2.0.0 - GPU Era
        ├─ GPU infrastructure (CUDA/ROCm, vLLM/Triton)
        ├─ Embedding model upgrade (Qwen3-8B + BGE-Reranker)
        ├─ Video/audio processing (Whisper transcription)
        └─ True semantic chunking (embedding-based boundaries)
```

---

### v1.8.x - Infrastructure & Tooling

**Focus**: Developer experience and deployment optimization

#### Docker Build Optimization
- BuildKit cache mounts (60% faster rebuilds)
- Pre-built base image on ghcr.io (80-95% faster first builds)
- Multi-stage Dockerfile (40-60% smaller images)
- See [internal_planning/PERFORMANCE_OPTIMIZATION.md](../internal_planning/PERFORMANCE_OPTIMIZATION.md)

#### MCP Network Deployment
- Network-accessible MCP server (not just stdio)
- OAuth 2.1 authentication
- Streamable HTTP transport (replacing deprecated SSE)
- mcp-remote bridge for stdio→HTTP conversion
- See [internal_planning/MCP_NETWORK_DEPLOYMENT.md](../internal_planning/MCP_NETWORK_DEPLOYMENT.md)

**Known Limitations**: GIL contention limits multi-worker parallelism on CPU. True parallel embedding requires GPU (v2.0.0) or Go workers. See [KNOWN_ISSUES.md#1-gil-contention-with-multiple-embedding-workers](KNOWN_ISSUES.md#1-gil-contention-with-multiple-embedding-workers).

---

### v1.9.x - Pre-v2 Stabilization (Optional)

**Focus**: Polish and production readiness

- Production bug fixes
- Performance profiling and optimization
- Documentation improvements
- Test coverage expansion
- May be skipped if v1.8.x is stable enough

---

### v2.0.0 - GPU & Advanced Features

**Focus**: Hardware acceleration and advanced capabilities

#### GPU Support Infrastructure
- CUDA/ROCm support for embedding generation
- 10-50x performance improvement for model inference
- Hardware selection, OS setup, vLLM/Triton deployment
- See [internal_planning/GPU_INFRASTRUCTURE.md](../internal_planning/GPU_INFRASTRUCTURE.md)

#### Embedding Model Upgrade
- Upgrade to Qwen3-Embedding-8B (MTEB 70.58)
- BGE-Reranker-v2-m3 cross-encoder (+20-30% retrieval accuracy)
- Practical re-indexing (hours instead of weeks)
- See [internal_planning/GPU_INFRASTRUCTURE.md](../internal_planning/GPU_INFRASTRUCTURE.md)

#### Embedding-Based Semantic Chunking
Current "semantic" chunking is paragraph/structure-aware but not truly semantic. True semantic chunking would:
- Split documents into atomic units (sentences/paragraphs)
- Compute embeddings for each unit
- Measure cosine similarity between consecutive units
- Start new chunk when similarity drops below threshold (semantic boundary)

This produces chunks where content within each chunk is semantically coherent, improving retrieval accuracy.
Requires GPU for acceptable performance (embedding each unit is expensive on CPU).

#### Video/Audio Processing
- Automatic transcription (Whisper)
- Temporal chunking for timestamp-accurate results
- Podcast, lecture, meeting support

#### Local Vision Models
- Video frame analysis without external APIs
- Privacy, cost savings, no rate limits

---

## IDE Integration

RAG-KB integrates with AI coding assistants via MCP (Model Context Protocol).

| Assistant | Config File | Setup Guide |
|-----------|-------------|-------------|
| **Claude Code** | `~/.claude.json` | [MCP_CLAUDE.md](MCP_CLAUDE.md) |
| **OpenAI Codex** | `~/.codex/config.toml` | [MCP_CODEX.md](MCP_CODEX.md) |
| **Google Gemini** | `~/.gemini/settings.json` | [MCP_GEMINI.md](MCP_GEMINI.md) |
| **Cursor** | `~/.cursor/mcp.json` | Same as Claude Code |

**MCP Tools Available**:
- `query_knowledge_base` - Semantic search across indexed documents
- `list_indexed_documents` - Browse indexed files
- `get_kb_stats` - Knowledge base statistics

### Other IDE/LLM Integrations

| Tool | Protocol | Integration Path |
|------|----------|------------------|
| **Continue.dev** | MCP | Similar to Claude config |
| **Cody (Sourcegraph)** | Custom | REST API wrapper |
| **GitHub Copilot** | None | Not directly integrable |
| **Ollama** | REST | Direct API calls |
| **LM Studio** | OpenAI-compat | Function calling wrapper |

---

## Feature Backlog

Lower priority items for future releases:

| Feature | Description |
|---------|-------------|
| Processing Webhooks | Pause/resume processing of specific files via webhook |
| Remote Processing | Offload to cloud GPU/TPU workers |
| Web UI | Visual library, drag-drop upload, tagging |
| Multi-Vector | Multiple embeddings per chunk for diversity |
| Advanced Metadata | Author extraction, LLM tagging, relationship mapping |
| Multi-Language | Non-English docs, language detection |
| **Universal MCP Adapter** | Wrapper for non-MCP LLM tools (REST→MCP bridge) |

---

## Decision Log

### Why Python 3.13 Standard Build (Not Free-Threading)?

**Date**: 2025-01-24

**Decision**: Standard build (no free-threading, no JIT)

**Rationale**:
- Free-threading has 40% performance penalty in Python 3.13
- JIT is experimental with minimal gains for I/O-bound workloads
- Already using `EMBEDDING_WORKERS=2` for parallelism
- Wait for Python 3.14 (penalty drops to 5-10%)

**Gains**: 5-10% general performance from Python 3.13 optimizations

---

### Why Hybrid Index for Code RAG?

**Decision**: Single model + hybrid chunking (not dual models)

**Rationale**:
- One model, one vector store, one search interface
- No score fusion complexity
- Modern models handle code + text well
- Chunking quality > embedding model choice

---

## Contributing

Have ideas? Open an issue or PR.

**Contact**: horoshi@katanaquant.com
