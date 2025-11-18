# RAG-KB Roadmap

This document outlines planned features and improvements for the RAG Knowledge Base system.

## Current Version: v0.8.0-alpha

**Status**: Production-ready for document + code ingestion (PDF, DOCX, EPUB, Markdown, Python, Java, TypeScript, C#)

---

## Planned Features

### High Priority

#### 1. Code RAG Support (AST-Based Chunking)

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

#### 2. Query Result Ranking Improvements
- Add reranking stage after hybrid search
- Experiment with cross-encoder models
- A/B test different fusion algorithms

#### 3. Multi-Vector Representations
- Store multiple embeddings per chunk (e.g., question + answer pairs)
- Improve retrieval diversity
- Better handling of multi-aspect content

#### 4. Incremental Updates
- Delta indexing for modified files
- Avoid full reprocessing on small changes
- Track file modification times

---

### Low Priority / Future

#### 5. Web UI for Knowledge Base Management
- Browse indexed documents
- Search interface with filters
- Document preview and highlighting

#### 6. Advanced Metadata Extraction
- Author, publication date, categories
- Automatic tagging via LLM
- Relationship mapping between documents

#### 7. Multi-Language Support
- Non-English document processing
- Language detection
- Multilingual embedding models

---

## Completed Features

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
