# Release v0.9.1-alpha

**Release Date**: 2025-11-19

This release combines v0.9.0 and v0.9.1 development work into a single comprehensive update, focusing on production-ready code architecture and enhanced document management capabilities.

## Major Changes

### Architecture Refactoring (POODR)

Complete refactoring following Sandi Metz's "Practical Object-Oriented Design in Ruby" principles:

- **Decomposed 4 God Classes into 25+ focused components**
  - TextExtractor: Document processing orchestrator
  - JupyterExtractor: Notebook processing with cell-aware chunking
  - ObsidianExtractor: Graph-RAG for knowledge vaults
  - DocumentProcessor: File ingestion coordinator

- **Applied POODR Patterns**
  - Dependency Injection: All dependencies passed at construction
  - Duck Typing: Polymorphic chunkers respond to chunk(cell, path)
  - Orchestrator Pattern: Coordinating objects delegate specialized work
  - Facade Pattern: Simplified interfaces hide complex subsystems

- **Extracted Specialized Components**
  - NotebookOutputParser: Parse Jupyter cell outputs
  - KernelLanguageDetector: Map kernel names to languages
  - MarkdownCellChunker: Process markdown cells
  - CodeCellChunker: AST-aware code cell processing
  - CellCombiner: Smart adjacent cell combination
  - FrontmatterParser: YAML metadata extraction
  - SemanticChunker: Content-aware text chunking
  - GraphEnricher: Knowledge graph metadata enrichment
  - FileHasher: Content-based deduplication
  - MetadataEnricher: Chunk metadata augmentation
  - ProcessingProgressTracker: Resumable processing state

### Document Management API

New REST endpoints for document lifecycle management:

**DELETE /document/{path}**
- Removes document from all 3 tables (documents, chunks, processing_progress)
- Returns deletion statistics
- Enables testing and maintenance workflows

**GET /documents/search?pattern={pattern}**
- Case-insensitive pattern matching across file paths
- Returns file paths, names, hashes, timestamps, chunk counts
- Examples: `/documents/search?pattern=AFTS`, `/documents/search?pattern=.ipynb`

### Logging Improvements

Significantly reduced log noise while maintaining visibility:

- **Silent Operations**
  - No logging for already-completed files
  - No logging for duplicate files
  - No logging for empty files

- **Milestone-Based Progress**
  - Reports at 25%, 50%, 75%, 100% completion
  - Progress every 100 files (down from every 10)
  - Final summary with counts

- **Enhanced Error Context**
  - Shows "Processing file..." before success/failure
  - Clear extraction method logging (docling_hybrid, ast_python, jupyter_ast, obsidian_graph_rag)
  - Character counts and chunk counts on completion

### Bug Fixes

- **EPUB Processing**: Added longtable error fallback using wkhtmltopdf for problematic EPUB files
- **File Watcher**: Added .ipynb to SUPPORTED_EXTENSIONS for automatic notebook indexing
- **Jupyter Extraction**: Fixed instance method issue (JupyterExtractor now properly instantiated)
- **Document Search API**: Fixed config path reference (database.path instead of DB_PATH)
- **Git Hygiene**: Added core.* pattern to .gitignore for core dump files

## Testing Results

All major file types tested successfully:

- **EPUB→PDF→embeddings**: Test-Driven Development by Kent Beck (317 chunks)
- **PDF→embeddings**: 99 Bottles by Sandi Metz (594 chunks)
- **Jupyter notebooks**: xs_carry_kris.ipynb (132 chunks, jupyter_ast extraction)
- **Python codebase**: AFTS (36 files, ast_python extraction)
- **Markdown files**: qoppac blog posts (28 chunks, obsidian_graph_rag extraction)

## Breaking Changes

None. This release maintains full backward compatibility with existing databases and configurations.

## Performance Characteristics

- **Logging overhead**: Reduced by ~90% through silent skips and milestone reporting
- **Processing throughput**: Unchanged (refactoring focused on maintainability)
- **Memory footprint**: Unchanged
- **Database size**: Unchanged

## Migration Notes

No migration required. Existing databases are fully compatible.

## Known Issues

- JavaScript files (.js) not yet supported in AST chunking (will be added in future release)
- Large EPUBs with complex tables may still fail conversion (manual intervention required)

## Acknowledgments

This release was developed and tested against a personal knowledge base of 900+ documents including books, code repositories, blog posts, and Jupyter notebooks.
