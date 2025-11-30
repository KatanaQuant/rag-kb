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

**Latest Release**: v1.9.1
**Development Phase**: v1.9.x complete, v2.0.0 planning complete, awaiting GPU hardware

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
- **MCP HTTP transport**: Direct connection to Docker container (recommended)
- **MCP stdio transport**: Node.js bridge (legacy, still supported)
- Chunking quality metrics (boundary coherence, retrieval accuracy)
- 759 tests passing (including 24 MCP HTTP tests)

---

## Version History

| Version | Highlights |
|---------|-----------|
| **v1.9.1** | MCP HTTP transport, Docker optimization (3.61GB), reindex endpoint, EPUB fix, 759 tests |
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
v1.9.1 (CURRENT)
    │
    ├── MCP HTTP transport (network access)
    ├── Docker optimization (3.61GB, -37%)
    ├── 759 tests passing
    │
    └── v2.0.0 - GPU Era (awaiting hardware)
        ├─ GPU infrastructure (CUDA/ROCm, vLLM/Triton)
        ├─ Embedding model upgrade (Qwen3-8B + BGE-Reranker)
        ├─ Video/audio processing (Whisper transcription)
        └─ True semantic chunking (embedding-based boundaries)
```

---

### v1.9.1 - MCP HTTP & Infrastructure [COMPLETE]

**Status**: Released (2025-11-30)

**Delivered**:
- **MCP HTTP transport**: Network-accessible `/mcp` endpoint, Claude Code E2E validated
- **Docker optimization**: 3.61GB image (down from 5.77GB, -37%), build time ~2-3s with cache
- **MCP documentation**: 5 setup guides (Claude Code, Cursor, Gemini, Amp, Network)
- **Reindex endpoint**: `POST /document/{path}/reindex` for force re-processing
- **EPUB pipeline fix**: EPUBs now bypass chunking entirely
- **Test coverage**: 759 tests (24 new MCP HTTP tests)
- **Documentation consolidation**: Public docs condensed, internal planning organized

**MCP Transport Recommendation**:
```bash
# HTTP (recommended) - Direct connection, no Node.js needed
claude mcp add --transport http --scope user rag-kb http://localhost:8000/mcp

# For remote servers
claude mcp add --transport http --scope user rag-kb http://SERVER_IP:8000/mcp
```

**stdio still supported** for backwards compatibility (deprecated, removed in v2.0)

**Known Limitations**: GIL contention limits CPU-only parallelism. GPU acceleration in v2.0.0 addresses this. See [KNOWN_ISSUES.md#1-gil-contention-with-multiple-embedding-workers](KNOWN_ISSUES.md#1-gil-contention-with-multiple-embedding-workers).

---

### v2.0.0 - GPU & Advanced Features [PLANNING]

**Status**: Planning complete, awaiting hardware delivery (RTX 3060 12GB)

**Core Features**:
- **GPU Infrastructure**: Ubuntu 24.04 + CUDA 12.x + vLLM/Triton
- **Embedding Upgrade**: Qwen3-8B (MTEB 70.58, +20% quality improvement)
- **Reranking**: BGE-Reranker-v2-m3 (+20-30% retrieval accuracy)
- **Semantic Chunking**: Embedding-based boundary detection (true semantic coherence)
- **Video/Audio**: Whisper Large-v3 transcription (12x realtime on RTX 3060)

**Hardware**:
- RTX 3060 12GB ordered (awaiting delivery)
- Perfect VRAM fit: Qwen3-8B (10GB) + BGE-Reranker (2GB) = 12GB
- All features supported with smart model swapping

**Implementation Phases**:
1. GPU server setup (Ubuntu, drivers, CUDA, Docker, vLLM)
2. Qwen3-8B embedding + full reindex
3. BGE-Reranker integration (two-stage retrieval)
4. True semantic chunking
5. Whisper audio/video transcription
6. Testing, benchmarking, documentation

For detailed roadmap, see [internal_planning/V2_PLANNING.md](../internal_planning/V2_PLANNING.md)

---

## IDE Integration

RAG-KB integrates with AI coding assistants via MCP (Model Context Protocol).

| Assistant | Config File | Setup Guide |
|-----------|-------------|-------------|
| **Claude Code** | `~/.claude.json` | [MCP_CLAUDE.md](MCP_CLAUDE.md) |
| **OpenAI Codex** | `~/.codex/config.toml` | [MCP_CODEX.md](MCP_CODEX.md) |
| **Google Gemini** | `~/.gemini/settings.json` | [MCP_GEMINI.md](MCP_GEMINI.md) |
| **Amp (Sourcegraph)** | `~/.config/amp/settings.json` | [MCP_AMP.md](MCP_AMP.md) |
| **Cursor** | `~/.cursor/mcp.json` | Same as Claude Code |

**MCP Tools Available**:
- `query_kb` - Semantic search across indexed documents
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

## Architecture Decisions

Key technical decisions are documented with full rationale in [internal_planning/ARCHITECTURE_DECISIONS.md](../internal_planning/ARCHITECTURE_DECISIONS.md):

- **Python 3.13 standard build** (not free-threading) - 40% penalty in 3.13, waiting for 3.14
- **Hybrid chunking** (single model, not dual) - Simpler architecture, no score fusion
- **v2.0.0 GPU strategy** - Hybrid CPU/GPU with graceful fallback
- **BatchEncoder for GIL mitigation** - 10-50x throughput improvement
- **Async database design** - API <100ms during indexing
- **3-stage concurrent pipeline** - Better parallelism and memory usage

---

## Contributing

Have ideas? Open an issue or PR.

**Contact**: horoshi@katanaquant.com
