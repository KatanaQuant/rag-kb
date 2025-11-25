"""
Chunking module - DEPRECATED

All chunking is now handled by specialized extractors:
- Docling HybridChunker for PDF/DOCX/EPUB/Markdown
- AST-based chunking for code files
- Cell-aware chunking for Jupyter notebooks
- Graph-RAG for Obsidian vaults

This module is kept for backwards compatibility but contains no active code.
The legacy TextChunker class has been removed as it's no longer used.
"""

# This module intentionally left empty.
# All chunking is now done by extractors that produce pre-chunked content.
