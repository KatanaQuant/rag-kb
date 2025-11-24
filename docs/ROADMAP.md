# RAG-KB Roadmap

This document outlines planned features and improvements for the RAG Knowledge Base system.

## Table of Contents

- [Current Version](#current-version-v0130-alpha)
- [Path to v1.0.0 Stable Release](#path-to-v100-stable-release)
  - [Roadmap Overview](#roadmap-overview)
  - [Critical Blockers for v1.0.0](#critical-blockers-for-v100)
  - [What's NOT Required for v1.0.0](#whats-not-required-for-v100)
- [Planned Features](#planned-features)
  - [High Priority (No GPU Required)](#high-priority-no-gpu-required)
    - [1. Notion Export Support](#1-notion-export-support)
    - [2. Document Security & Malware Scanning](#2-document-security--malware-scanning)
    - [3. Advanced Docker Build Optimization (Phase 2)](#3-advanced-docker-build-optimization-phase-2)
  - [Medium Priority](#medium-priority)
    - [4. Python 3.13 Upgrade [COMPLETED]](#4-python-313-upgrade-completed-in-v0140-alpha)
    - [5. Post-Migration Dependency Updates](#5-post-migration-dependency-updates)
  - [GPU-Accelerated Features](#gpu-accelerated-features)
    - [6. GPU Support Infrastructure](#6-gpu-support-infrastructure)
    - [7. Embedding Model Upgrade & Reranking](#7-embedding-model-upgrade--reranking)
    - [8. Video/Audio Processing Support](#8-videoaudio-processing-support)
    - [9. Local Vision Models](#9-local-vision-models)
  - [Medium-Low Priority](#medium-low-priority)
    - [10. Remote Processing Server Support](#10-remote-processing-server-support)
    - [11. Web UI for Knowledge Base Management](#11-web-ui-for-knowledge-base-management)
    - [12. Multi-Vector Representations & Incremental Updates](#12-multi-vector-representations--incremental-updates)
    - [13. Async Database Migration](#13-async-database-migration)
    - [14. Chunking Strategy Evaluation & Improvement](#14-chunking-strategy-evaluation--improvement)
  - [Low Priority / Future](#low-priority--future)
    - [15. Advanced Metadata Extraction](#15-advanced-metadata-extraction)
    - [16. Multi-Language Support](#16-multi-language-support)
- [Completed Features](#completed-features)
  - [v0.14.0-alpha](#v0140-alpha)
  - [v0.13.0-alpha](#v0130-alpha)
  - [v0.12.0-alpha](#v0120-alpha)
  - [v0.11.0-alpha](#v0110-alpha)
  - [v0.9.1-alpha](#v091-alpha)
  - [v0.8.0-alpha](#v080-alpha)
  - [v0.7.0-alpha](#v070-alpha)
  - [v0.6.0-alpha](#v060-alpha)
  - [v0.5.0-alpha](#v050-alpha)
- [Decision Log](#decision-log)
  - [Why Python 3.13 Standard Build (Not Free-Threading)?](#why-python-313-standard-build-not-free-threading)
  - [Why Option C (Hybrid Index) for Code RAG?](#why-option-c-hybrid-index-for-code-rag)
- [Contributing](#contributing)

---

## Current Version: v0.14.0-alpha

**Status**: Production-ready with Python 3.13 upgrade, database maintenance tools, and improved reliability

---

## Path to v1.0.0 Stable Release

RAG-KB is approximately **70-80% ready** for a stable v1.0.0 release. The core system is production-ready with solid architecture, but a few critical issues need resolution before removing the alpha tag.

### Roadmap Overview

```
v0.14.0-alpha (CURRENT)
    └─ Python 3.13 upgrade, database maintenance, queue duplicate detection

v0.15.0-alpha (Next - 4-8 weeks)
    └─ Fix API blocking during indexing (async database migration)

v0.16.0-beta (Feature Freeze - 6-10 weeks)
    └─ Comprehensive testing, API stability review, documentation polish

v1.0.0 (Stable Release - 2-4 weeks after beta)
    └─ Production-ready, semantic versioning begins
```

### Critical Blockers for v1.0.0

1. **Async Database Migration** - Fix API endpoints blocking 10+ seconds during indexing ([KNOWN_ISSUES.md #5](KNOWN_ISSUES.md))
2. **Comprehensive Test Coverage** - Fix skipped tests, add integration test suite (>80% coverage)
3. **API Stability Review** - Review all endpoints before committing to semantic versioning

### What's NOT Required for v1.0.0

These features will be added in v1.x.x releases after stable launch:
- GPU support (v1.1.0+)
- Video/audio transcription (v1.2.0+)
- Web UI (v1.3.0+)
- Python 3.13 upgrade (v1.4.0+)
- Notion export, ClamAV scanning, advanced optimizations

**Estimated Timeline**: 3-6 months to v1.0.0 stable

**Details**: See [internal_planning/V1_RELEASE_PLAN.md](../internal_planning/V1_RELEASE_PLAN.md) for comprehensive release plan

---

## Planned Features

### High Priority (No GPU Required)

#### 1. Notion Export Support

**Target**: v0.15.0-alpha

Support for Notion workspace exports (ZIP files with markdown, HTML, CSV) to enable indexing of Notion pages, databases, and hierarchies. Preserves page links and metadata.

---

#### 2. Document Security & Malware Scanning

**Target**: v0.15.0-alpha

ClamAV integration for scanning documents before indexing. Protects against malware in PDFs, ebooks, and documents from untrusted sources. Phase 1 (file type validation) completed in v0.12.0-alpha.

---

#### 3. Advanced Docker Build Optimization (Phase 2)

**Target**: v0.15.0-alpha or v0.16.0-alpha

Further Docker optimizations beyond v0.13.0 improvements:

**Current State (v0.13.0)**:
- ** BuildKit cache mounts (60% faster rebuilds)
- ** Multi-stage build (40-60% smaller images)
- ** .dockerignore optimization

**Future Improvements**:
- **Pre-built Base Image**: Push `rag-kb-base` image to ghcr.io with system packages pre-installed
  - First builds: 7-10 min → 3-5 min (80-95% faster)
  - Users skip apt-get entirely
  - Requires: GitHub Container Registry, base image maintenance

- **Python Wheels**: Pre-compile heavy packages (torch, sentence-transformers, docling)
  - Reduces pip install time by 20-30%
  - Store in GitHub Releases

**Combined Result** (Phase 1 + Phase 2):
- First build: 3-4 min (vs 7-10 min originally)
- Rebuilds: 1-2 min (vs 2-4 min currently)
- Final image: 1.5-2.0 GB

**See**: [internal_planning/DOCKER_BUILD_OPTIMIZATION.md](../internal_planning/DOCKER_BUILD_OPTIMIZATION.md)

---


### Medium Priority

#### 4. ~~Python 3.13 Upgrade~~ [COMPLETED in v0.14.0-alpha]

~~**Target**: v0.16.0-alpha~~

**Status**: ✓ **COMPLETED** - Upgraded to Python 3.13.9 with standard build (no free-threading/JIT)

**Completed**: v0.14.0-alpha (2025-01-24)

**What was done:**
- Upgraded from Python 3.11 → Python 3.13.9
- PyTorch 2.5.1 → 2.9.1+cpu (stability + memory leak fixes)
- torchvision 0.20.1 → 0.24.1+cpu
- All automatic Python 3.13 optimizations enabled (5-10% performance improvement)

**What was NOT enabled (intentional):**
- ❌ Free-threading (`python3.13t`) - 40% performance penalty in 3.13, wait for 3.14
- ❌ JIT compiler - Experimental, minimal/negative gains for I/O-bound workloads
- ✓ Standard build provides best performance for RAG workloads

**Actual Performance Gains:**
- PyTorch 2.9.1: Memory leak fixes, dynamic shape support, stability improvements
- Python 3.13: 5-10% general performance from automatic optimizations
- Worker scaling (4→8): 50% throughput improvement (already configured)

**See Decision**: [Decision Log - Python 3.13 Standard Build](#why-python-313-standard-build-not-free-threading)

---

#### 5. Post-Migration Dependency Updates

**Target**: Ongoing

~~Audit and update all dependencies after Python 3.13 migration to leverage new optimizations and security patches.~~

**Status**: Completed during Python 3.13 upgrade. PyTorch, FastAPI, docling, and supporting libraries are all current.

---

### GPU-Accelerated Features

**Note**: Hardware details in [internal_planning/HARDWARE_SETUP_GUIDE.md](../internal_planning/HARDWARE_SETUP_GUIDE.md)

---

#### 6. GPU Support Infrastructure

**Target**: v0.13.0-alpha

CUDA/ROCm GPU support for hardware-accelerated embedding generation and model inference. Enables 10-50x performance improvements for all GPU-accelerated features below.

---

#### 7. Embedding Model Upgrade & Reranking

**Target**: v0.13.0-alpha (requires GPU)

Upgrade to Qwen3-Embedding-8B (MTEB 70.58) and add BGE-Reranker-v2-m3 cross-encoder for +20-30% retrieval accuracy improvement. Makes re-indexing large knowledge bases practical (hours instead of weeks).

**See**: [internal_planning/EMBEDDING_MODEL_ANALYSIS.md](../internal_planning/EMBEDDING_MODEL_ANALYSIS.md)

---

#### 8. Video/Audio Processing Support

**Target**: v0.14.0-alpha (requires GPU)

Automatic transcription and indexing of video/audio files (podcasts, lectures, meetings, tutorials). Search across spoken content with temporal chunking for timestamp-accurate results.

---

#### 9. Local Vision Models

**Target**: v0.15.0-alpha (requires GPU)

Run vision models locally for video frame analysis instead of external APIs. Provides privacy, cost savings, and no rate limits.

---

### Medium-Low Priority

#### 10. Remote Processing Server Support

**Target**: v0.16.0-alpha

Offload compute-intensive processing to remote cloud workers (GPU/TPU) for pay-per-use indexing. Useful for one-time massive indexing without buying hardware.

---

#### 11. Web UI for Knowledge Base Management

**Target**: v0.18.0-alpha or later

Web interface with visual library view, document thumbnails, tagging system, drag-drop file upload, and GUI operational controls. Improves UX but not critical for core functionality.

---

#### 12. Multi-Vector Representations & Incremental Updates

Store multiple embeddings per chunk for better retrieval diversity. Delta indexing for modified files to avoid full reprocessing.

---

#### 13. Async Database Migration

**Target**: v0.15.0-alpha or v0.16.0-alpha

Migrate blocking database calls to async I/O (using `aiosqlite`) to fix slow API endpoints during indexing. Target <10ms response time for `/health` endpoint even during heavy indexing.

**See**: [KNOWN_ISSUES.md #5](KNOWN_ISSUES.md) - API Endpoints Block During Indexing (current problem)

---

#### 14. Chunking Strategy Evaluation & Improvement

**Target**: v0.15.0-alpha or v0.16.0-alpha

Systematic evaluation of chunking quality with metrics and content-aware strategies. Philosophy: chunking quality > embedding model quality. Improves retrieval for plain text and specialized content types.

**See**: [internal_planning/CHUNKING_STRATEGY_EVALUATION.md](../internal_planning/CHUNKING_STRATEGY_EVALUATION.md)

---

### Low Priority / Future

#### 15. Advanced Metadata Extraction
- Author, publication date, categories
- Automatic tagging via LLM
- Relationship mapping between documents

#### 16. Multi-Language Support
- Non-English document processing
- Language detection
- Multilingual embedding models

---

## Completed Features

### v0.14.0-alpha
- **Python 3.13 Upgrade**: Migrated from Python 3.11 to Python 3.13 (5-10% performance improvement)
- **Database Maintenance Webhooks**: Added `/maintenance/check-duplicates` and `/maintenance/cleanup-duplicates` endpoints
- **Queue Duplicate Detection**: IndexingQueue now prevents redundant file processing with smart tracking
- **Improved Error Handling**: Enhanced FileNotFoundError logging with full paths and stack traces
- **PyTorch Updates**: Updated to PyTorch 2.5.1+ (Python 3.13 compatible)
- **Bug Fixes**: Fixed RapidOCR cache mount path for Python 3.13, improved E2E test stability

### v0.13.0-alpha
- **Docker Build Optimization**: BuildKit cache mounts reduce rebuild time by 60% (7-10 min → 2-4 min)
- **Multi-Stage Docker Build**: 40-60% smaller final image (~2.0-2.5 GB vs ~3.5 GB), more secure runtime
- **Structured Progress Logging**: Real-time progress tracking with timing, rates, and ETA across all pipeline stages
- **Periodic Heartbeat**: Background updates every 60s for long-running operations
- **.dockerignore**: Optimized build context by excluding unnecessary files
- **Bug Fixes**: Fixed extraction method logging, EPUB conversion logging, renamed TextExtractor to ExtractionRouter

### v0.12.0-alpha
- **Configurable Knowledge Base Directory**: Environment variable `KNOWLEDGE_BASE_PATH` to customize KB location
- **Path Expansion**: Automatic ~ expansion to home directory and relative→absolute conversion
- **Flexible Storage**: Support for external drives, NAS, existing document collections
- **File Type Validation**: Magic byte verification prevents malicious files (Phase 1 - Security)
- **Configuration Validation**: Startup validation with clear error messages for misconfigurations
- **EPUB Conversion Fix**: Added texlive-plain-generic for soul.sty LaTeX package support
- **Documentation Improvements**: Restructured docs, added troubleshooting guides

### v0.11.0-alpha
- **Concurrent Processing Pipeline**: 3-stage pipeline (chunk → embed → store) with 4x throughput improvement
- **Go Language Support**: AST-based chunking for Go code with tree-sitter
- **Modular Architecture**: Reduced main.py from 1246 to 530 lines, extracted 9 service modules
- **Priority Queue System**: HIGH/NORMAL priority levels for urgent files
- **Operational Controls API**: Pause/resume/clear queue, fast-track files, orphan repair
- **Queue Management**: GET /queue/jobs, POST /indexing/pause, POST /indexing/resume, POST /indexing/clear
- **Sanitization Stage**: Orphan detection and automatic repair before indexing
- **Concurrent Workers**: Configurable CHUNK_WORKERS and EMBED_WORKERS

### v0.9.1-alpha
- Production-ready architecture (POODR refactoring: 4 God Classes → 25+ focused components)
- Jupyter notebook support (cell-aware chunking with AST parsing for 160+ languages)
- Obsidian Graph-RAG (NetworkX knowledge graph with wikilinks, tags, backlinks)
- Document Management API (DELETE /document/{path}, GET /documents/search?pattern=)
- Clean logging (silent skips, milestone-based progress, 90% noise reduction)
- EPUB longtable error fallback (automatic HTML-based conversion)
- File watcher improvements (show file before processing, .ipynb support)

### v0.8.0-alpha
- Code RAG with AST-based chunking (Python, Java, TypeScript, JavaScript, C#)
- Hybrid index (unified vector space for code + docs)
- Smart file filtering (excludes build artifacts, dependencies, secrets)
- Progress bar for indexing operations
- Tested with production codebases

### v0.7.0-alpha
- Sandi Metz refactoring (modular architecture)
- Docling HybridChunker for all document types
- EPUB validation and error handling
- MCP troubleshooting documentation

### v0.6.0-alpha
- Markdown support with Docling
- Async embedding pipeline (parallel processing)
- Hot reload for development

### v0.5.0-alpha
- EPUB support (Pandoc → PDF → Docling)
- Resumable processing with progress tracking
- Automatic Ghostscript PDF repair

---

## Decision Log

### Why Python 3.13 Standard Build (Not Free-Threading)?

**Date**: 2025-01-24
**Context**: Python 3.13 upgrade from 3.11

**Considered Options**:
- **Option A**: Python 3.13 standard build (chosen)
- **Option B**: Python 3.13t free-threaded build (GIL disabled)
- **Option C**: Python 3.13 with JIT compiler enabled

**Decision**: Option A - Python 3.13 Standard Build

**Rationale**:

**Why NOT Free-Threading (3.13t)?**
1. **40% Performance Penalty**: Free-threading in Python 3.13 has 40% overhead on single-threaded code
2. **Extension Compatibility**: PyTorch and sentence-transformers may re-enable GIL anyway
3. **Already Concurrent**: System uses `EMBEDDING_WORKERS=8` for parallelism
4. **PyTorch GIL Release**: Torch already releases GIL during CPU operations
5. **Wait for 3.14**: Python 3.14 reduces penalty to 5-10% with specializing interpreter

**Why NOT JIT Compiler?**
1. **Minimal Gains**: CPython core dev reports JIT is "slower than interpreter to roughly equivalent"
2. **I/O Bound**: RAG system bottleneck is database/disk, not CPU-bound Python code
3. **C Extensions**: JIT doesn't help torch, sentence-transformers (our hot path)
4. **Complexity**: Experimental feature adds build complexity for 0-2% gain

**What We DO Get (Automatic)?**
1. **PyTorch 2.9.1**: Memory leak fixes, dynamic shape support, stability
2. **Better Memory Management**: Improved GC and object allocation
3. **Optimized Error Handling**: Faster exception handling
4. **Standard Library Improvements**: Faster `os.path`, string ops, asyncio
5. **Expected Gain**: 5-10% overall performance improvement

**Performance Priorities (Actual Impact)**:
1. ✅ **Worker Scaling** (4→8): +50% throughput (already done)
2. ✅ **PyTorch 2.9.1**: Stability and memory improvements
3. 🔜 **Async DB Migration**: Fix 10s+ API blocking ([KNOWN_ISSUES.md #5](KNOWN_ISSUES.md))
4. 🔜 **Faster Storage**: NVMe SSD if not already
5. 🔜 **Model Upgrade**: Better embedding model ([ROADMAP.md #7](ROADMAP.md))

**Trade-offs Accepted**:
- No free-threading benefits (but they don't apply to our workload)
- No JIT benefits (but minimal for I/O-bound code)
- Gained: Stability, compatibility, automatic optimizations

**Future Consideration**:
- Revisit free-threading in Python 3.14 when penalty drops to 5-10%
- Evaluate when PyTorch/sentence-transformers explicitly support free-threading

---

### Why Option C (Hybrid Index) for Code RAG?

**Considered Options**:
- **Option A**: Single multi-modal model for everything
- **Option B**: Dual models (Qwen3 for code, Arctic for docs) with separate vector stores
- **Option C**: Hybrid chunking + unified embedding model

**Decision**: Option C - Hybrid Index

**Rationale**:
1. **Simplicity**: One model, one vector store, one search interface
2. **Natural ranking**: No score fusion gymnastics needed
3. **Modern models are multi-domain**: Qwen3-8B handles code + text well
4. **Easier maintenance**: Single model to update/optimize
5. **Fast iteration**: Change chunking without touching embeddings
6. **Quality where it matters**: Chunking strategy > embedding model choice

**Trade-offs Accepted**:
- Slight compromise on embedding quality vs dual-model
- But chunking quality matters more (AST vs basic text splitting)

---

## Contributing

Have ideas for the roadmap? Open an issue or PR with your suggestions!

**Contact**: horoshi@katanaquant.com

