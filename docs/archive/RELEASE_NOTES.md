# Release Notes

Complete release history for RAG Knowledge Base.

---

## Releases

### v0.7.0-alpha - 2025-11-17
**Structure and Complexity Reduction**

- Split 1310-line monolith into 7 focused modules
- All modules achieve A maintainability rating
- Added 29 new unit tests (145 total, 100% passing)
- Eliminated all D/C complexity violations
- Comprehensive repository cleanup and documentation improvements

### [v0.6.0-alpha](RELEASE_v0.6.0-alpha.md) - 2025-11-17
**EPUB Support & Automatic Ghostscript Retry**

- Full EPUB processing pipeline (Pandoc + XeLaTeX + Ghostscript)
- Automatic Ghostscript retry for ANY failing PDF extraction
- Extraction method tracking with new API endpoint
- Improved error logging and warning suppression
- Smart file organization (original/, problematic/ subdirectories)

### [v0.5.0-alpha](RELEASE_v0.5.0-alpha.md) - 2025-11-17
**HybridChunker & Advanced PDF Processing**

- HybridChunker with token-aware semantic chunking
- Docling 2.61.2 upgrade with advanced PDF processing
- RapidOCR support for scanned PDFs and images
- Table structure extraction and preservation
- CPU-optimized Docker build

### [v0.4.0-alpha](RELEASE_v0.4.0-alpha.md)
**Enhanced Search & Configuration**

- Arctic Embed 2.0 model support
- Multi-model embedding configuration
- Performance optimizations

### [v0.3.0-alpha](RELEASE_v0.3.0-alpha.md)
**Production Hardening**

- Improved error handling
- Database schema enhancements
- Documentation improvements

### [v0.2.0-alpha](RELEASE_v0.2.0-alpha.md)
**MCP Integration**

- Model Context Protocol server
- Enhanced API endpoints
- Configuration management

### [v0.1.0-alpha](RELEASE_v0.1.0-alpha.md)
**Initial Release**

- Core RAG functionality
- Hybrid search implementation
- Document processing pipeline
- Docker deployment

---

## Latest Release

**Current Version**: v0.7.0-alpha

Major architectural refactoring focused on code quality and maintainability.

---

## Upgrade Path

- v0.6.0-alpha → v0.7.0-alpha: Fully compatible, internal refactoring only (no migration needed)
- v0.5.0-alpha → v0.7.0-alpha: Fully compatible, database auto-migrates
- v0.4.0-alpha → v0.7.0-alpha: Fully compatible, recommended to re-index
- Earlier versions → v0.7.0-alpha: See migration guides in individual releases

---

## Version Naming

RAG Knowledge Base follows semantic versioning during alpha development:

- **Major.Minor.Patch-alpha**
- Major: Breaking changes
- Minor: New features, enhancements
- Patch: Bug fixes only

Alpha releases (0.x.x-alpha) may have API changes between minor versions.
