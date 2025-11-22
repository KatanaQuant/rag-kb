# RAG-KB Roadmap

This document outlines planned features and improvements for the RAG Knowledge Base system.

## Current Version: v0.12.0-alpha

**Status**: Production-ready with configurable storage, file type validation, and improved security

---

## Planned Features

### High Priority (No GPU Required)

#### 1. Notion Export Support

**Target**: v0.12.0-alpha

**Objective**: Add support for Notion export formats to enable indexing of Notion workspace content.

**Current Limitation**:
- Notion exports (.zip files containing markdown, HTML, CSV) are not automatically processed
- Users must manually extract and organize exported content
- Notion-specific features (databases, linked pages, embeds) are lost

**Implementation Plan**:
1. [ ] Add support for Notion export ZIP format detection
2. [ ] Extract and parse Notion markdown exports (preserves hierarchy)
3. [ ] Handle Notion-specific markdown extensions (callouts, toggles, databases)
4. [ ] Map Notion page links to internal cross-references
5. [ ] Support Notion database exports (CSV/inline databases)
6. [ ] Preserve page metadata (creation date, author, tags)
7. [ ] Test with real Notion workspace exports

**Supported Export Formats**:
- Markdown & CSV (recommended, preserves structure)
- HTML (fallback, less structured)

**Priority Rationale**: Notion is widely used for personal knowledge management and team wikis. Many users have extensive Notion workspaces they want to index locally.

---

#### 2. Document Security & Malware Scanning

**Target**: v0.12.0-alpha or v0.13.0-alpha

**Objective**: Add security validation for documents before indexing to prevent malicious files from being processed.

**Current Limitation**:
- No validation of file integrity or safety
- Potentially dangerous files (malware, exploits) could be indexed
- Users with pirated/untrusted content have no protection

**Use Cases**:
- **Personal safety**: Scanning downloaded PDFs, ebooks from untrusted sources
- **Pirated content**: Many users have digital copies of physical books (safe, but from untrusted sources)
- **Shared drives**: Enterprise users indexing shared network drives
- **Email attachments**: Documents from unknown senders

**Implementation Plan**:

**Phase 1: File Type Validation** (COMPLETED in v0.12.0-alpha)
1. [x] Add magic byte verification (ensure PDFs aren't executables)
2. [x] Validate file extension matches actual file type
3. [x] Check for suspicious file headers
4. [x] Reject obviously tampered files
5. [x] Log warnings for review

**Phase 2: ClamAV Integration** (Full Protection - 4-8 hours)
1. [ ] Add ClamAV Docker sidecar container
2. [ ] Integrate clamav-python or subprocess calls
3. [ ] Scan files before indexing pipeline
4. [ ] Quarantine/reject infected files
5. [ ] Add MALWARE_SCAN_ENABLED environment variable
6. [ ] Document setup and signature updates

**Phase 3: Advanced Protection** (Optional - Future)
1. [ ] YARA rules for custom malware patterns
2. [ ] PDF exploit detection (malicious JavaScript, forms)
3. [ ] Macro detection in Office documents
4. [ ] File hash reputation checking (VirusTotal API)

**Configuration**:
```bash
# .env
MALWARE_SCAN_ENABLED=true          # Enable/disable scanning
MALWARE_SCAN_ACTION=reject         # reject|quarantine|warn
CLAMAV_HOST=clamav                 # ClamAV container hostname
```

**Performance Impact**:
- File type validation: <1ms per file (negligible)
- ClamAV scanning: 100-500ms per file (acceptable for batch indexing)
- Optional: Skip scanning for trusted directories

**Priority Rationale**: Security is critical for users indexing untrusted content. File type validation is a quick win (1-2 hours). ClamAV provides comprehensive protection without disrupting workflow.

---


### Medium Priority

#### 3. Python 3.13 Upgrade

**Target**: v0.16.0-alpha

**Status**: ✅ Ready to migrate (see `docs/PYTHON_3.13_COMPATIBILITY_AUDIT.md`)

**Objective**: Upgrade to Python 3.13 for performance improvements with free-threading and JIT compilation.

**Benefits**:
- Free-threading (no GIL) - true multi-core parallelism for embedding generation
- JIT compiler - faster execution for hot code paths
- 8-12% performance improvement for CPU-intensive operations (standard)
- 30-100% concurrent embedding improvement (free-threading mode)

**Implementation Plan**:
1. [x] Audit Python 3.13 compatibility (✅ All deps compatible)
2. [ ] Update Dockerfile to python:3.13-slim
3. [ ] Upgrade PyTorch to 2.6.0+ and NumPy to 2.0+
4. [ ] Run full test suite and benchmarks
5. [ ] **Re-validate embedding model choices** (free-threading may change CPU/GPU tradeoffs)
6. [ ] Update documentation and deployment guides
7. [ ] Optional: Evaluate free-threading mode (python3.13t)

**Model Re-Evaluation**: After Python 3.13 migration, revisit `internal_planning/EMBEDDING_MODEL_ANALYSIS.md` to re-benchmark all models. Free-threading (no GIL) may significantly improve CPU inference performance.

**Priority Rationale**: Python 3.13's free-threading and JIT compiler provide significant performance improvements while maintaining Python's ML ecosystem advantages. All dependencies now support Python 3.13.

---

#### 4. Post-Migration Dependency Updates

**Target**: v0.17.0-alpha (after Python 3.13 migration)

**Objective**: After migrating to Python 3.13, audit and update all dependencies to latest stable versions to benefit from new features and performance improvements.

**Rationale**:
- Dependencies may have Python 3.13-specific optimizations
- Newer versions may have bug fixes and security patches
- Check backwards compatibility before updating

**Implementation Plan**:
1. [ ] Generate dependency update report (pip list --outdated)
2. [ ] Review changelogs for breaking changes
3. [ ] Update dependencies one category at a time:
   - [ ] PyTorch ecosystem (torch, torchvision, sentence-transformers)
   - [ ] FastAPI ecosystem (fastapi, pydantic, uvicorn)
   - [ ] Document processing (docling, pypdf, python-docx)
   - [ ] Code/notebook parsing (astchunk, nbformat, tree-sitter)
   - [ ] Supporting libs (watchdog, networkx, obsidiantools)
4. [ ] Run full test suite after each category update
5. [ ] Benchmark performance impact
6. [ ] Document version changes and rationale

**Backwards Compatibility**:
- Test with existing knowledge bases (no reindexing required)
- Verify API compatibility (no breaking changes for users)
- Fallback plan if major issues arise

**Priority Rationale**: Keeping dependencies up-to-date improves security, performance, and ensures access to latest features. Python 3.13 migration is prerequisite.

---

### GPU-Accelerated Features

**Note**: Hardware details and implementation guides are available in `internal_planning/HARDWARE_SETUP_GUIDE.md`

---

#### 5. GPU Support Infrastructure

**Target**: v0.13.0-alpha

**Objective**: Add CUDA/ROCm GPU support to enable hardware-accelerated embedding generation, transcription, and model inference.

**Implementation Plan**: See internal planning documentation for detailed hardware requirements and setup instructions.

**Priority Rationale**: Foundation for all GPU-accelerated features below. Enables 10-50x performance improvements.

---

#### 6. Embedding Model Upgrade & Reranking

**Target**: v0.13.0-alpha (requires GPU Support #5)

**Objective**: Upgrade to larger, more accurate embedding models and add cross-encoder reranking for better retrieval quality.

**Current Model**: Snowflake Arctic Embed L (335M params, 1024 dim, MTEB 59.0)

**Proposed Upgrades**:
- **GPU (12GB+)**: Upgrade to Qwen3-Embedding-8B (MTEB 70.58, #1 multilingual, 16x faster)
- **Reranking**: Add BGE-Reranker-v2-m3 for +20-30% ranking accuracy (requires GPU)

**Implementation Plan**:
1. [ ] Implement model auto-selection based on available hardware (GPU/VRAM)
2. [ ] Add GPU-accelerated embedding generation
3. [ ] Benchmark Qwen3-8B on GPU vs Arctic Embed L on CPU
4. [ ] Add cross-encoder reranking for top-K results
5. [ ] Provide migration/reindexing script for model changes
6. [ ] Document model comparison and hardware requirements

**Detailed Analysis**: See `internal_planning/EMBEDDING_MODEL_ANALYSIS.md` for comprehensive research on model performance and cost-benefit analysis.

**Priority Rationale**: Re-indexing large knowledge bases on CPU would take weeks. GPU makes this practical (hours instead of weeks). Significant quality improvement (+20-30% ranking accuracy with reranking).

---

#### 7. Video/Audio Processing Support

**Target**: v0.14.0-alpha (requires GPU Support #5)

**Objective**: Enable indexing and querying of video and audio files (lectures, podcasts, meetings, tutorials) through automatic transcription and temporal chunking.

**Supported Formats**: `.mp4`, `.mp3`, `.wav`, `.m4a`, `.webm`, `.mkv`, `.avi`

**Use Cases**:
- Podcast search: "Find episodes where they discuss options trading"
- Lecture notes: "What did the professor say about recursion in week 3?"
- Meeting search: "When did we discuss the Q4 roadmap?"
- Tutorial indexing: "How to implement authentication in that Django video?"
- YouTube backup: Index downloaded educational content locally

**Priority Rationale**: High user demand for podcast/lecture indexing. Complements existing document/code RAG capabilities.

---

#### 8. Local Vision Models

**Target**: v0.15.0-alpha (requires GPU Support #5)

**Objective**: Run vision models locally instead of relying on external APIs (Gemini/OpenAI) for video frame analysis.

**Priority Rationale**: Privacy, cost savings, no rate limits. Lower priority than reranking as external APIs work well for now.

---

### Medium-Low Priority

#### 9. Remote Processing Server Support (Cloud TPU/GPU Workers)

**Target**: v0.16.0-alpha

**Objective**: Enable offloading compute-intensive processing to remote cloud workers (GPU/TPU) while keeping local query interface. Pay-per-use for fast indexing without buying hardware.

**Use Cases**:
- One-time indexing of massive archives (100K+ documents)
- Podcast/video transcription bursts (rent GPU for 2 hours)
- Distributed team with shared cloud knowledge base
- Startup without GPU budget (pay $20/month for occasional indexing)

**Priority Rationale**: Most users should get local GPU first - much simpler. Only valuable for one-time massive indexing, no hardware budget, or distributed teams. Detailed architecture and cost analysis in internal planning docs.

---

#### 10. Web UI for Knowledge Base Management

**Target**: v0.18.0-alpha or later

**Objective**: Build a web interface for browsing, organizing, and managing the indexed knowledge base with visual library view and operational controls.

**Current Limitation**:
- All operations done via terminal/CLI (cURL, Python scripts)
- No visual way to browse indexed documents
- No organization/tagging system
- Operational controls require terminal commands

**Features**:

**Library View**:
- Visual grid/list of all indexed documents
- Cover images/thumbnails for PDFs, ebooks, documents
- Document metadata (title, type, size, chunks, indexed date)
- Sort by: date added, name, type, size, chunks
- Filter by: file type, tag, date range
- Search indexed documents by name/path

**Tagging System**:
- Manual tags for organization (e.g., "finance", "machine-learning", "work", "personal")
- Tag management UI (create, rename, delete tags)
- Multi-tag support per document
- Tag-based filtering and search
- Color-coded tag badges
- Optional: Auto-tagging via LLM analysis of content

**File Upload & Import**:
- Drag-and-drop file upload interface
- Browse and select multiple files
- Upload progress indicators (per-file and overall)
- Automatic indexing after upload
- Supported formats: PDF, DOCX, EPUB, Markdown, Code, Jupyter, etc.
- Batch upload (multiple files at once)
- Upload to specific folders/categories
- Alternative to manually copying files to knowledge_base directory

**Document Management**:
- View document details (path, hash, chunks, embeddings)
- Re-index individual documents
- Delete documents from index (with option to delete original file)
- Download original file
- View chunk breakdown with preview
- Move/rename documents within KB

**Operational Controls (GUI)**:
- Dashboard with system stats (indexed docs, total chunks, queue status)
- Queue management: pause/resume/clear indexing queue
- View current indexing jobs (file, status, progress)
- Fast-track files (move to HIGH priority)
- Orphan detection and repair buttons
- Real-time indexing progress indicators

**Search Interface**:
- Full-text RAG search with preview
- Highlighting of relevant chunks
- Relevance scores
- Chunk-level navigation
- Export search results

**Implementation Plan**:
1. [ ] Choose web framework (React + FastAPI backend, or Streamlit for simplicity)
2. [ ] Design library view UI/UX mockups
3. [ ] Implement document listing API endpoints
4. [ ] Build file upload system (drag-drop, multipart upload, progress tracking)
5. [ ] Add cover extraction for PDFs/ebooks (first page thumbnail)
6. [ ] Build tagging system (DB schema, API, UI)
7. [ ] Create operational controls dashboard
8. [ ] Implement search interface with highlighting
9. [ ] Add real-time updates (WebSocket for queue status)
10. [ ] Deploy as separate Docker service or integrated

**Technology Options**:
- **Option A**: Streamlit (fastest, Python-only, good for MVP)
- **Option B**: React + FastAPI (more polished, better UX)
- **Option C**: Gradio (ML-focused, simpler than React)

**Priority Rationale**: Improves UX significantly but not critical for core functionality. Terminal/API access works for power users. Good stretch goal after Python 3.13 migration.

---

#### 11. Multi-Vector Representations
- Store multiple embeddings per chunk (e.g., question + answer pairs)
- Improve retrieval diversity
- Better handling of multi-aspect content

#### 12. Incremental Updates
- Delta indexing for modified files
- Avoid full reprocessing on small changes
- Track file modification times

---

#### 13. Async Database Migration (Performance)

**Target**: v0.13.0-alpha or v0.14.0-alpha

**Objective**: Migrate all blocking database calls to async I/O to prevent API endpoint slowness during heavy indexing.

**Current Limitation**:
- All database queries are synchronous blocking calls
- API endpoints block while counting documents, fetching stats, querying vectors
- Noticeable slowness when accessing `/health`, `/documents`, `/query` during indexing
- User experience: "feels slow when curling to localhost:8000 webhooks"

**Blocking Endpoints Identified** (2025-11-22 audit):
1. **`/health`** - Calls `COUNT(*)` on documents + chunks tables (CRITICAL - health checks should be fast)
2. **`/documents`** - Queries all documents with JOIN (1,599+ docs = slow)
3. **`/documents/search`** - Pattern matching across file paths
4. **`/query`** - Vector similarity search + chunk retrieval (main RAG query)
5. **`/document/{filename}`** - Document info lookup with LIKE query

**Non-Blocking Endpoints** (already fast):
- `/queue/jobs` - In-memory queue stats ✅
- `/indexing/status` - In-memory worker state ✅
- `/indexing/pause|resume|clear` - Queue operations ✅

**Implementation Plan**:
1. [ ] Add `aiosqlite` or `asyncpg` (if migrating to PostgreSQL) dependency
2. [ ] Create async database connection pool
3. [ ] Migrate repository classes to async methods:
   - `DocumentRepository.count()` → `async count()`
   - `ChunkRepository.count()` → `async count()`
   - `VectorRepository.search()` → `async search()`
4. [ ] Add caching layer for `/health` endpoint stats (update every 10s, not every request)
5. [ ] Update all `async def` endpoints to use `await` for database calls
6. [ ] Add comprehensive tests for async database operations
7. [ ] Benchmark before/after response times under load

**Performance Targets**:
- `/health`: <10ms response time (currently 50-200ms with 1,599 docs)
- `/documents`: <100ms for listing (currently 200-500ms)
- `/query`: <500ms for vector search (currently 1-3s with context switches)

**Alternative Approach** (shorter-term fix):
- Cache `/health` stats in memory, refresh every 10 seconds via background thread
- Moves counting off request path, instant health checks
- Doesn't solve `/documents` and `/query` slowness

**Priority Rationale**: User-facing API should be responsive during indexing. Blocking database calls create poor UX when monitoring progress via webhooks/CLI.

---

### Low Priority / Future

#### 14. Advanced Metadata Extraction
- Author, publication date, categories
- Automatic tagging via LLM
- Relationship mapping between documents

#### 15. Multi-Language Support
- Non-English document processing
- Language detection
- Multilingual embedding models

---

## Completed Features

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

