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
- [Feature Backlog](#feature-backlog)
- [Decision Log](#decision-log)
- [Contributing](#contributing)

---

## Current State

**Latest Release**: v1.6.2 (N+1 Query Fix)

**What's Working**:
- Production-ready document indexing (PDF, EPUB, Markdown, Code)
- Concurrent 3-stage pipeline (Chunk → Embed → Store)
- Async API (responsive during heavy indexing)
- Comprehensive security scanning (ClamAV, YARA, hash blacklist)
- 627 tests passing

---

## Version History

| Version | Highlights |
|---------|-----------|
| **v1.6.2** | Fix N+1 query in completeness API (1300x faster) |
| **v1.6.1** | Fix YARA is_valid logic bug |
| **v1.6.0** | Security REST API, non-blocking scan jobs, parallel scanning |
| **v1.5.0** | Advanced malware detection (ClamAV, YARA, hash blacklist) |
| **v1.4.0** | Quarantine system for dangerous files |
| **v1.3.0** | Rejection tracking, archive bomb detection |
| **v1.2.0** | File type validation, executable detection |
| **v1.0.0** | Production release, async database, 445 tests |
| **v0.16.0** | Async database migration (API <100ms during indexing) |
| **v0.15.0** | POODR refactoring (main.py 684→89 LOC) |
| **v0.14.0** | Python 3.13 upgrade |
| **v0.13.0** | Docker optimization, progress logging |
| **v0.11.0** | Concurrent pipeline, Go support |
| **v0.9.1** | Jupyter notebooks, Obsidian Graph-RAG |
| **v0.8.0** | Code RAG with AST chunking |

---

## Journey to v2.0.0

```
v1.6.2 (CURRENT)
    │
    ├── v1.7.x - Performance & Polish
    │   └── Chunking strategy improvements
    │
    ├── v1.8.x - Content Expansion
    │   └── Notion export, additional file formats
    │
    ├── v1.9.x - Pre-v2 Stabilization
    │   └── Docker Phase 2, API review, final polish
    │
    └── v2.0.0 - GPU & Advanced Features
        └── GPU support, embedding upgrade, video/audio, vision models
```

---

### v1.7.x - Performance & Polish

**Focus**: Performance optimizations and developer experience

#### Chunking Strategy Evaluation
- Semantic boundary detection via embedding similarity
- Variable-size chunks aligned to topic boundaries
- Requires profiling before GPU features
- See [internal_planning/CHUNKING_STRATEGY_EVALUATION.md](../internal_planning/CHUNKING_STRATEGY_EVALUATION.md)

---

### v1.8.x - Content Expansion

**Focus**: Additional content sources

#### Notion Export Support
- Notion workspace exports (ZIP with markdown/HTML/CSV)
- Preserve page links and hierarchy
- Database property extraction

#### Additional Format Support
- Evaluate user-requested formats
- Audio transcription prep (metadata, no GPU yet)

---

### v1.9.x - Pre-v2 Stabilization

**Focus**: Final polish before major version

#### Docker Build Optimization Phase 2
- Pre-built base image on ghcr.io (7-10 min → 3-5 min first build)
- Python wheels for heavy packages
- See [internal_planning/DOCKER_BUILD_OPTIMIZATION.md](../internal_planning/DOCKER_BUILD_OPTIMIZATION.md)

#### API Stability Review
- Review all endpoints before semantic versioning
- Document breaking changes for v2.0.0
- Deprecation warnings for removed features

---

### v2.0.0 - GPU & Advanced Features

**Focus**: Hardware acceleration and advanced capabilities

#### GPU Support Infrastructure
- CUDA/ROCm support for embedding generation
- 10-50x performance improvement for model inference
- See [internal_planning/HARDWARE_SETUP_GUIDE.md](../internal_planning/HARDWARE_SETUP_GUIDE.md)

#### Embedding Model Upgrade
- Upgrade to Qwen3-Embedding-8B (MTEB 70.58)
- BGE-Reranker-v2-m3 cross-encoder (+20-30% retrieval accuracy)
- Practical re-indexing (hours instead of weeks)
- See [internal_planning/EMBEDDING_MODEL_ANALYSIS.md](../internal_planning/EMBEDDING_MODEL_ANALYSIS.md)

#### Video/Audio Processing
- Automatic transcription (Whisper)
- Temporal chunking for timestamp-accurate results
- Podcast, lecture, meeting support

#### Local Vision Models
- Video frame analysis without external APIs
- Privacy, cost savings, no rate limits

---

## Feature Backlog

Lower priority items for future releases:

| Feature | Description |
|---------|-------------|
| Remote Processing | Offload to cloud GPU/TPU workers |
| Web UI | Visual library, drag-drop upload, tagging |
| Multi-Vector | Multiple embeddings per chunk for diversity |
| Advanced Metadata | Author extraction, LLM tagging, relationship mapping |
| Multi-Language | Non-English docs, language detection |

---

## Decision Log

### Why Python 3.13 Standard Build (Not Free-Threading)?

**Date**: 2025-01-24

**Decision**: Standard build (no free-threading, no JIT)

**Rationale**:
- Free-threading has 40% performance penalty in Python 3.13
- JIT is experimental with minimal gains for I/O-bound workloads
- Already using `EMBEDDING_WORKERS=8` for parallelism
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
