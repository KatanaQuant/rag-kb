# Release Notes: v0.8.0-alpha

**Release Date:** 2025-11-18
**Status:** Ready for Testing

---

## Major Features

### Code RAG Support (AST-Based Chunking)

Index entire codebases alongside your documentation with intelligent, structure-aware chunking.

**Key Features:**
- **AST-based chunking** using `astchunk` library (tree-sitter backend)
- **Language support**: Python, Java, TypeScript/JavaScript, C#
- **Respects code boundaries**: Functions, classes, and logical units stay together
- **Same simple UX**: Drop repos into `knowledge_base/` just like documents

**Usage:**

```bash
cd knowledge_base
git clone https://github.com/anthropics/anthropic-sdk-python.git

# System automatically:
# - Routes .py → AST chunking (function/class boundaries)
# - Routes .md → Docling (documentation)
# - Skips .git/, node_modules/, __pycache__/, .env, etc.
```

**Query Example:**
```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"text": "How does the SDK handle API retries?", "top_k": 5}'

# Returns:
# - retry.py implementation (AST-chunked code)
# - README.md section (documentation)
# - Related error handling code
```

**Architecture:**
- **Hybrid Index** (Option C from research)
  - Different chunking per type (AST for code, Docling for docs)
  - Unified vector space (single embedding model)
  - Natural ranking across both code and documentation
- **Research-backed**: cAST approach (+5.5 points RepoEval, +4.3 CrossCodeEval)
- **Model**: Compatible with existing embedding models (Arctic, MiniLM, etc.)

**Benefits:**
- Search across documentation AND implementation in one query
- Better context for code-related questions
- Foundation for full repository indexing
- Zero configuration - automatic file type detection

**Implementation Status:**
- ✅ File filtering/sanitization (excludes build artifacts, dependencies, secrets)
- ✅ `astchunk` integration
- ✅ `CodeExtractor` class
- ✅ Language detection and routing
- ✅ Tested with production codebase (50 Python files, 353 chunks)

**See:** [ROADMAP.md](ROADMAP.md) for detailed architecture and implementation plan

---

## 🐛 Bug Fixes

### EPUB Processing

**Fixed: Invalid EPUB file handling with helpful error messages**

**Problem:**
- Corrupted or placeholder EPUB files (e.g., from Anna's Archive) caused cryptic Pandoc errors
- No validation before attempting conversion
- Users couldn't easily identify the root cause

**Solution:**
- ✅ **Validate EPUB files** before processing (ZIP magic bytes + mimetype check)
- ✅ **Show actual file content** for small files (<10KB) in error message
- ✅ **Clear error messaging** with actionable next steps
- ✅ **Auto-move problematic files** to `problematic/` subdirectory

**Example Error (Before):**
```
Pandoc error: Couldn't extract ePub file: Did not find end of central directory signature
```

**Example Error (After):**
```
================================================================================
ERROR: Failed to process Advanced Futures Trading Strategies.epub
================================================================================
Invalid EPUB file: Advanced Futures Trading Strategies.epub
  File does not appear to be a valid EPUB archive.
  EPUB files must be ZIP containers with proper structure.

  Actual file content (80 bytes):
  "This book is not available on Anna's Archive. Please request it..."

  → This may be a placeholder, corrupted download, or renamed file.
  → Re-download from source and replace this file.
================================================================================

→ Moved Advanced Futures Trading Strategies.epub to problematic/ subdirectory
```

**Impact:**
- Users immediately understand the issue
- No need to dig through logs or debug Pandoc
- Problematic files are isolated automatically

---

## Improvements

### Enhanced Error Logging

**Improved exception handling in processing pipeline**

- ✅ **Detailed tracebacks** for unexpected errors (previously swallowed)
- ✅ **Error type identification** in logs
- ✅ **File context** included in error messages

**Before:**
```
Error processing: document.pdf
```

**After:**
```
Error processing: document.pdf
Error type: RuntimeError: Docling conversion failed
[Full traceback with line numbers and context]
Returning empty chunks for: document.pdf
```

**Files Changed:**
- [api/ingestion/processing.py:277-287](../api/ingestion/processing.py#L277-287)

### Duplicate Log Removal

**Fixed: Duplicate "Processing:" messages**

- ✅ Removed redundant log in `main.py` (kept single log in `processing.py`)
- ✅ Cleaner output during batch processing

### File Filtering for Codebases

**Smart exclusion of development artifacts**

When indexing codebases, automatically excludes:
- **Version control**: `.git/`, `.svn/`, `.hg/`
- **Dependencies**: `node_modules/`, `__pycache__/`, `.pytest_cache/`
- **Virtual environments**: `.venv/`, `venv/`, `env/`, `.env/`
- **Build artifacts**: `dist/`, `build/`, `.eggs/`, `*.egg-info/`
- **IDE directories**: `.idea/`, `.vscode/`, `.vs/`
- **Compiled files**: `*.pyc`, `*.class`, `*.jar`, `*.dll`, `*.so`
- **Minified assets**: `*.min.js`, `*.min.css`
- **Secret files**: `.env*`, `secrets`, `credentials`

**Files Changed:**
- [api/main.py:79-125](../api/main.py#L79-125)

---

## 📚 Documentation

### Updated README

- ✅ Added Code RAG workflow with examples
- ✅ Clarified UX for mixed document/code indexing
- ✅ Updated MCP troubleshooting (path issues after machine migration)

### Updated ROADMAP

- ✅ Code RAG detailed implementation plan
- ✅ Architecture decision (Option C: Hybrid Index)
- ✅ Research references (cAST, astchunk, MTEB-Code)
- ✅ User experience examples

---

## 🧹 Cleanup

### Removed Obsolete Scripts

Removed custom shell scripts now superseded by cleaner UX:
- ❌ `export-codebase.sh` (replaced by direct `knowledge_base/` usage)
- ❌ `export-codebase-simple.sh` (replaced by direct `knowledge_base/` usage)
- ❌ `export-for-analysis.sh` (replaced by direct `knowledge_base/` usage)
- ❌ `get-port.sh` (no longer needed)

**Kept:**
- ✅ `ingest-obsidian.sh` (future feature - Obsidian vault syncing)
- ✅ `setup-test-data.sh` (development)
- ✅ `test-runner.sh` (development)

---

## 🔄 Migration Guide

No breaking changes. This is a feature-additive release.

**To use Code RAG (when available):**
1. Update to v0.8.0-alpha: `git pull && docker-compose up --build -d`
2. Drop codebases into `knowledge_base/`: `git clone <repo-url> knowledge_base/`
3. Wait for automatic indexing
4. Query naturally: "how does X implement Y?"

---

## 🙏 Contributors

- Development: horoshi@katanaquant.com
- Research: cAST paper authors, astchunk library maintainers
- Testing: Community feedback on EPUB issues

---

## 📖 References

- [ROADMAP.md](ROADMAP.md) - Detailed Code RAG architecture
- [cAST Paper](https://arxiv.org/html/2506.15655v1) - AST-based chunking research
- [astchunk GitHub](https://github.com/yilinjz/astchunk) - Tree-sitter chunking library
- [MTEB-Code Leaderboard](https://huggingface.co/spaces/mteb/leaderboard) - Embedding model benchmarks

---

## Known Issues

- EPUB processing still requires Pandoc + texlive (see README.md for installation)
- Large codebases (>10K files) may take significant time to index initially
- Progress bar shows "0 indexed" when all files are already processed (expected behavior)

---

## What's Next (v0.9.0)

- Query result ranking improvements (reranking stage)
- Multi-vector representations per chunk
- Incremental updates (delta indexing for modified files)
- Additional language support (Go, Rust, C++)

See [ROADMAP.md](ROADMAP.md) for full feature pipeline.
