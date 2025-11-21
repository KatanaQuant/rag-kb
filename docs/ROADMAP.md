# RAG-KB Roadmap

This document outlines planned features and improvements for the RAG Knowledge Base system.

## Current Version: v0.11.0-alpha

**Status**: Production-ready with concurrent processing, modular architecture, and Go language support

---

## Planned Features

### High Priority (No GPU Required)

#### 1. Notion Export Support

**Target**: v0.10.0-alpha

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

#### 2. Go Language Support (AST-Based Chunking)

**Status**: Complete
**Released**: v0.11.0-alpha

**Objective**: Add Go language support to AST-based code chunking.

**Implementation Completed**:
1. Custom GoChunker implementation using tree-sitter-language-pack
2. Added `.go` extension to CodeExtractor routing and SUPPORTED_EXTENSIONS
3. Intelligent file filtering (vendor/, go.mod, binaries, certificates)
4. Complete test coverage (4/4 tests passing)
5. AST-based chunking for functions, methods, types, consts, vars, imports
6. Tested with production Go codebase ("Let's Go" book examples - 21 files successfully indexed)

**Features**:
- Function and method declarations
- Type declarations (structs, interfaces)
- Package-level declarations (const, var)
- Import and package clauses
- Preserves complete function boundaries

---

#### 2. Code RAG Support (AST-Based Chunking)

**Status**: Complete
**Released**: v0.8.0-alpha

**Objective**: Add intelligent code indexing with AST-based chunking alongside document support.

**Architecture**: Hybrid Index (Option C)
- **Documents**: Continue using Docling HybridChunker (current implementation)
  - Token-aware chunking
  - Preserves document structure (sections, paragraphs)
  - Smart merging of related content

- **Code Files**: Add AST-based chunking via `astchunk` library
  - Function/class boundaries respected
  - Cross-file context preserved (imports, dependencies)
  - Language-agnostic structure (Python, Java, TypeScript, C#)

- **Unified Vector Space**: Single embedding model for both types
  - Natural cosine similarity ranking
  - Can retrieve mixed results (code + docs in same query)
  - Simpler architecture than dual-model approach

**User Experience**:
Same simple workflow as documents - just drop codebases into `knowledge_base/`:

```bash
cd knowledge_base
git clone https://github.com/anthropics/anthropic-sdk-python.git
# System automatically:
# - Routes .py files → AST chunking (respects function/class boundaries)
# - Routes .md files → Docling markdown (documentation)
# - Skips .git/, __pycache__/, node_modules/, .env files, etc.
```

**Query Example**: "how does the SDK handle API retries?"
- Returns: `retry.py` implementation + SDK docs + related code

**Implementation Plan**:
1. File sanitization/filtering (exclude `.git`, `node_modules`, `.env`, etc.)
2. Add `astchunk` to requirements.txt
3. Create `CodeExtractor` class using AST chunking
4. Add language detection (by file extension)
5. Route `.py`, `.java`, `.ts`, `.tsx`, `.cs`, `.jsx` to AST chunker
6. Keep Docling for documents (`.pdf`, `.docx`, `.md`, `.epub`)
7. Tested with production codebase

**Benefits**:
- **Zero new concepts**: Same UX as documents (drop files → automatic indexing)
- **Smart filtering**: Automatically excludes build artifacts, dependencies, secrets
- **Mixed results**: Query returns both code implementations AND documentation
- **Cross-language**: Works with Python, Java, TypeScript, C#
- **Flexible organization**: Mix docs and code however you prefer

**Research**:
- **Best Model**: Alibaba Qwen3-8B (32K context, #1 on MTEB-Code benchmark)
- **Chunking**: cAST approach (+5.5 points RepoEval, +4.3 CrossCodeEval)
- **Library**: `astchunk` (tree-sitter based, 4 languages supported)

**References**:
- [cAST Paper](https://arxiv.org/html/2506.15655v1)
- [astchunk GitHub](https://github.com/yilinjz/astchunk)
- [MTEB-Code Leaderboard](https://huggingface.co/spaces/mteb/leaderboard)

---

### Medium Priority

#### 3. Embedding Model Validation & Optimization

**Target**: v0.10.0-alpha

**Objective**: Validate current model choice (Arctic Embed L) and evaluate upgrade to Qwen3-Embedding series for better quality and performance across different hardware configurations.

**Current Model**: Snowflake Arctic Embed L (335M params, 1024 dim, MTEB 59.0)

**Proposed Upgrades**:
- **CPU-only**: Switch to Qwen3-Embedding-0.6B (MTEB 64.33, +9% quality, same CPU-friendliness)
- **GPU (12GB+)**: Upgrade to Qwen3-Embedding-8B (MTEB 70.58, #1 multilingual, 16x faster)
- **Reranking**: Add BGE-Reranker-v2-m3 for +20-30% ranking accuracy (requires GPU)

**Implementation Plan**:
1. [ ] Benchmark Qwen3-0.6B vs Arctic Embed L on current CPU
2. [ ] Implement model auto-selection based on available hardware (CPU/GPU/VRAM)
3. [ ] Add model configuration to `.env` with smart defaults
4. [ ] Provide migration/reindexing script for model changes
5. [ ] Document model comparison and hardware requirements

**Detailed Analysis**: See `internal_planning/EMBEDDING_MODEL_ANALYSIS.md` for comprehensive research on model performance and cost-benefit analysis.

**Priority Rationale**: Current Arctic Embed L is good for CPU, but Qwen3 models (released 2025) offer significant quality improvements.

---

#### 4. Python 3.13 Upgrade

**Target**: v0.16.0+ (when Python 3.13 stable)

**Objective**: Upgrade to Python 3.13 for performance improvements with free-threading and JIT compilation.

**Benefits**:
- Free-threading (no GIL) - true multi-core parallelism for embedding generation
- JIT compiler - faster execution for hot code paths
- 10-20% performance improvement for CPU-intensive operations
- Better concurrency for multi-threaded workloads

**Implementation Plan**:
1. [ ] Wait for Python 3.13 stable release and ecosystem compatibility
2. [ ] Update Docker base images to Python 3.13
3. [ ] Test all dependencies for Python 3.13 compatibility
4. [ ] Benchmark embedding performance (CPU multi-threading)
5. [ ] **Re-validate embedding model choices** (free-threading may change CPU/GPU tradeoffs)
6. [ ] Update documentation and deployment guides

**Model Re-Evaluation**: After Python 3.13 migration, revisit `internal_planning/EMBEDDING_MODEL_ANALYSIS.md` to re-benchmark all models. Free-threading (no GIL) may significantly improve CPU inference performance.

**Priority Rationale**: Python 3.13's free-threading and JIT compiler provide significant performance improvements while maintaining Python's ML ecosystem advantages.

---

#### 5. Configurable Knowledge Base Directory

**Target**: v0.10.0-alpha

**Objective**: Allow users to configure the knowledge base directory location instead of being restricted to the default `./knowledge_base/` path.

**Current Limitation**:
- Knowledge base must be in project root `./knowledge_base/`
- Users cannot easily point to existing document collections on different drives
- Cannot use symlinks effectively for distributed storage

**Implementation Plan**:
1. [ ] Add `KNOWLEDGE_BASE_PATH` to config.py
2. [ ] Update Docker volume mounting to support custom paths
3. [ ] Add validation for path existence and permissions
4. [ ] Update documentation with configuration examples
5. [ ] Support multiple knowledge base paths (priority-based search)

**Use Cases**:
- Point to existing document collections without copying
- Store knowledge base on faster/larger drives
- Support network-attached storage (NAS)
- Enable multiple knowledge bases per project

**Priority Rationale**: Flexibility for users with large existing document collections or specific storage requirements.

---

### GPU-Accelerated Features

**Note**: Hardware details and implementation guides are available in `internal_planning/HARDWARE_SETUP_GUIDE.md`

---

#### 6. GPU Support Infrastructure

**Target**: v0.11.0-alpha

**Objective**: Add CUDA/ROCm GPU support to enable hardware-accelerated embedding generation, transcription, and model inference.

**Implementation Plan**: See internal planning documentation for detailed hardware requirements and setup instructions.

**Priority Rationale**: Foundation for all GPU-accelerated features below. Enables 10-50x performance improvements.

---

#### 7. Video/Audio Processing Support

**Target**: v0.12.0-alpha (requires GPU Support #6)

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

#### 8. Advanced Embedding Models & Reranking

**Target**: v0.13.0-alpha (requires GPU Support #6)

**Objective**: Upgrade to larger, more accurate embedding models and add cross-encoder reranking for better retrieval quality.

**Implementation Options**:
- Larger embedding models (Qwen3-8B, GTE-Qwen2-7B)
- Cross-encoder reranking for top-K results
- Two-stage pipeline: fast retrieval → precise reranking

**Priority Rationale**: Significant quality improvement (+20-30% ranking accuracy). Hardware details in internal planning docs.

---

#### 9. Local Vision Models

**Target**: v0.14.0-alpha (requires GPU Support #6)

**Objective**: Run vision models locally instead of relying on external APIs (Gemini/OpenAI) for video frame analysis.

**Priority Rationale**: Privacy, cost savings, no rate limits. Lower priority than reranking as external APIs work well for now.

---

### Medium-Low Priority

#### 10. Remote Processing Server Support (Cloud TPU/GPU Workers)

**Target**: v0.15.0-alpha

**Objective**: Enable offloading compute-intensive processing to remote cloud workers (GPU/TPU) while keeping local query interface. Pay-per-use for fast indexing without buying hardware.

**Use Cases**:
- One-time indexing of massive archives (100K+ documents)
- Podcast/video transcription bursts (rent GPU for 2 hours)
- Distributed team with shared cloud knowledge base
- Startup without GPU budget (pay $20/month for occasional indexing)

**Priority Rationale**: Most users should get local GPU first - much simpler. Only valuable for one-time massive indexing, no hardware budget, or distributed teams. Detailed architecture and cost analysis in internal planning docs.

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

### Low Priority / Future

#### 13. Web UI for Knowledge Base Management
- Browse indexed documents
- Search interface with filters
- Document preview and highlighting

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

## v0.9.3-alpha - Operational Controls & Queue Architecture

**Status**: Complete (In-Memory Queue Implementation)
**Released**: 2025-11-20

**Focus:** Production operational capabilities with in-memory priority queue

### Implemented Features

**Pause/Resume Indexing:** API endpoints to control background processing
**Priority Queue:** Push test files or critical documents to front of queue
**Indexing Queue Service:** Extract queue abstraction following Sandi Metz principles
  - `IndexingQueue` class with priority support (Python `PriorityQueue`)
  - `IndexingWorker` class for background processing
  - Thread-safe implementation
  - 4 priority levels: URGENT, HIGH, NORMAL, LOW

**Operational Endpoints:**
  - `POST /indexing/pause` - Pause background indexing
  - `POST /indexing/resume` - Resume background indexing
  - `POST /indexing/priority/{path}` - Add file with high priority
  - `GET /indexing/status` - Show queue state and progress

**Sanitization Stage:** Structured startup sequence ensures clean state
  - Resume incomplete files first
  - Detect and repair orphans synchronously (BEFORE new indexing)
  - Only after repairs complete, start processing new files
  - Prevents competition between repair and new processing
  - Maintains pause/resume/priority capabilities throughout

### Implementation Details

**Architecture Choice:** In-Memory Queue (Not Redis/RabbitMQ)
- Uses Python standard library `queue.PriorityQueue`
- Thread-based worker (not distributed)
- Sufficient for single-instance deployments
- Lightweight, no external dependencies

**Trade-offs:**
- No state persistence (queue cleared on restart)
- No distributed processing
- Simple, maintainable code
- Fast startup, no infrastructure needed
- Perfect for testing and development

### Future Enhancements (v0.10+)

**Mid-Pipeline Priority Boosting:**
- Add endpoint to boost priority of files already in pipeline queues
- Allow changing priority of items in embed_queue or store_queue
- Use case: Rush a file through after chunking completes
- Implementation: Drain queue, find item, update priority, re-add all items
- Trade-off: Queue manipulation overhead vs flexibility

**State Persistence:**
- Persist queue state to SQLite on shutdown
- Resume queue on startup
- Track processing history

**Distributed Processing (Optional):**
- Redis/RabbitMQ integration
- Multiple worker instances
- Remote processing servers

### Architecture References
- Message Queues (System Design Interview - Alex Xu)
- Task Queues (High Performance Python - Gorelick)
- Async Processing (Designing Data-Intensive Applications - Kleppmann)

