# RAG-KB Roadmap

This document outlines planned features and improvements for the RAG Knowledge Base system.

## Current Version: v0.9.1-alpha

**Status**: Production-ready with enterprise architecture and document management APIs

---

## Planned Features

### High Priority

#### 1. Go Language Support (AST-Based Chunking)

**Target**: v0.10.0-alpha

**Objective**: Add Go language support to AST-based code chunking.

**Current Limitation**:
- Go files (.go) are not yet supported in AST chunking (documented in README.md and RELEASE_v0.9.1-alpha.md)
- Need to add tree-sitter Go grammar to astchunk integration

**Implementation Plan**:
1. [ ] Verify tree-sitter-go grammar availability in astchunk library
2. [ ] Add `.go` extension to CodeExtractor routing
3. [ ] Test with production Go codebase
4. [ ] Update documentation

**Priority Rationale**: Go is widely used for backend services and infrastructure code. Many users have Go codebases in their knowledge bases.

---

#### 2. Code RAG Support (AST-Based Chunking)

**Status**: ✅ Complete
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
1. ✅ File sanitization/filtering (exclude `.git`, `node_modules`, `.env`, etc.)
2. ✅ Add `astchunk` to requirements.txt
3. ✅ Create `CodeExtractor` class using AST chunking
4. ✅ Add language detection (by file extension)
5. ✅ Route `.py`, `.java`, `.ts`, `.tsx`, `.cs`, `.jsx` to AST chunker
6. ✅ Keep Docling for documents (`.pdf`, `.docx`, `.md`, `.epub`)
7. ✅ Tested with production codebase

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

#### 3. Configurable Knowledge Base Directory

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

#### 4. Remote Processing Server Support

**Target**: v0.11.0-alpha

**Objective**: Enable offloading CPU-intensive processing (embedding, chunking) to remote servers while keeping local query interface.

**Current Limitation**:
- All processing happens locally on CPU
- Large knowledge bases can take days to index
- No way to leverage cloud/remote compute resources

**Architecture Options**:
- **Option A**: gRPC server/client for processing delegation
- **Option B**: Message queue (Redis/RabbitMQ) for distributed work
- **Option C**: HTTP API for stateless processing nodes

**Implementation Plan**:
1. [ ] Design distributed processing protocol
2. [ ] Create worker node Docker image
3. [ ] Add connection pooling for remote workers
4. [ ] Implement fallback to local processing if remote unavailable
5. [ ] Add authentication/encryption for remote connections
6. [ ] Create worker deployment guide (VPS, cloud instances)

**Use Cases**:
- Rent GPU servers for faster embedding generation
- Distribute indexing across multiple machines
- Use beefy cloud instances temporarily for initial indexing
- Keep local query latency while offloading heavy processing

**Security Considerations**:
- Documents sent to remote workers (privacy concerns)
- Need encryption in transit (TLS)
- Authentication tokens for worker nodes
- Option to keep sensitive docs local

**Priority Rationale**: Addresses the main pain point of slow CPU-based indexing for large knowledge bases.

---

#### 5. Query Result Ranking Improvements
- Add reranking stage after hybrid search
- Experiment with cross-encoder models
- A/B test different fusion algorithms

#### 6. Multi-Vector Representations
- Store multiple embeddings per chunk (e.g., question + answer pairs)
- Improve retrieval diversity
- Better handling of multi-aspect content

#### 7. Incremental Updates
- Delta indexing for modified files
- Avoid full reprocessing on small changes
- Track file modification times

---

### Low Priority / Future

#### 8. Web UI for Knowledge Base Management
- Browse indexed documents
- Search interface with filters
- Document preview and highlighting

#### 9. Advanced Metadata Extraction
- Author, publication date, categories
- Automatic tagging via LLM
- Relationship mapping between documents

#### 10. Multi-Language Support
- Non-English document processing
- Language detection
- Multilingual embedding models

---

## Completed Features

### v0.9.1-alpha
- ✅ Production-ready architecture (POODR refactoring: 4 God Classes → 25+ focused components)
- ✅ Jupyter notebook support (cell-aware chunking with AST parsing for 160+ languages)
- ✅ Obsidian Graph-RAG (NetworkX knowledge graph with wikilinks, tags, backlinks)
- ✅ Document Management API (DELETE /document/{path}, GET /documents/search?pattern=)
- ✅ Clean logging (silent skips, milestone-based progress, 90% noise reduction)
- ✅ EPUB longtable error fallback (automatic HTML-based conversion)
- ✅ File watcher improvements (show file before processing, .ipynb support)

### v0.8.0-alpha
- ✅ Code RAG with AST-based chunking (Python, Java, TypeScript, JavaScript, C#)
- ✅ Hybrid index (unified vector space for code + docs)
- ✅ Smart file filtering (excludes build artifacts, dependencies, secrets)
- ✅ Progress bar for indexing operations
- ✅ Tested with production codebases

### v0.7.0-alpha
- ✅ Sandi Metz refactoring (modular architecture)
- ✅ Docling HybridChunker for all document types
- ✅ EPUB validation and error handling
- ✅ MCP troubleshooting documentation

### v0.6.0-alpha
- ✅ Markdown support with Docling
- ✅ Async embedding pipeline (parallel processing)
- ✅ Hot reload for development

### v0.5.0-alpha
- ✅ EPUB support (Pandoc → PDF → Docling)
- ✅ Resumable processing with progress tracking
- ✅ Automatic Ghostscript PDF repair

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

**Status**: ✅ Complete (In-Memory Queue Implementation)
**Released**: 2025-11-20

**Focus:** Production operational capabilities with in-memory priority queue

### Implemented Features

✅ **Pause/Resume Indexing:** API endpoints to control background processing
✅ **Priority Queue:** Push test files or critical documents to front of queue
✅ **Indexing Queue Service:** Extract queue abstraction following Sandi Metz principles
  - `IndexingQueue` class with priority support (Python `PriorityQueue`)
  - `IndexingWorker` class for background processing
  - Thread-safe implementation
  - 4 priority levels: URGENT, HIGH, NORMAL, LOW

✅ **Operational Endpoints:**
  - `POST /indexing/pause` - Pause background indexing
  - `POST /indexing/resume` - Resume background indexing
  - `POST /indexing/priority/{path}` - Add file with high priority
  - `GET /indexing/status` - Show queue state and progress

✅ **Sanitization Stage:** Structured startup sequence ensures clean state
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
- ❌ No state persistence (queue cleared on restart)
- ❌ No distributed processing
- ✅ Simple, maintainable code
- ✅ Fast startup, no infrastructure needed
- ✅ Perfect for testing and development

### Future Enhancements (v0.10+)

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

