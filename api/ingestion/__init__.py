"""
Ingestion package - Document processing and storage

This package handles the complete document ingestion pipeline:
- Text extraction from various formats (PDF, DOCX, MD, EPUB)
- Semantic chunking via specialized extractors (Docling, AST, Jupyter, Obsidian)
- Progress tracking with resume capability
- Vector database storage

Note: Legacy TextChunker has been removed. All chunking is now handled by
specialized extractors that produce pre-chunked content.
"""

# Helpers
from .helpers import FileHasher, GhostscriptHelper

# Extractors
from .extractors import (
    DoclingExtractor,
    DOCXExtractor,
    TextFileExtractor,
    MarkdownExtractor,
    EpubExtractor,
    ExtractionRouter
)

# Processing
from .processing import (
    MetadataEnricher,
    DocumentProcessor
)

# Progress tracking
from .progress import (
    ProcessingProgress,
    ProcessingProgressTracker
)

# Database
from .database import (
    DatabaseConnection,
    SchemaManager,
    VectorRepository,
    VectorStore
)

__all__ = [
    # Helpers
    'FileHasher',
    'GhostscriptHelper',
    # Extractors
    'DoclingExtractor',
    'DOCXExtractor',
    'TextFileExtractor',
    'MarkdownExtractor',
    'EpubExtractor',
    'ExtractionRouter',
    # Processing
    'MetadataEnricher',
    'DocumentProcessor',
    # Progress
    'ProcessingProgress',
    'ProcessingProgressTracker',
    # Database
    'DatabaseConnection',
    'SchemaManager',
    'VectorRepository',
    'VectorStore',
]
