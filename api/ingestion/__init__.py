"""
Ingestion package - Document processing and storage.

This package handles the complete document ingestion pipeline:
- Text extraction from various formats (PDF, DOCX, MD, EPUB)
- Semantic chunking via specialized extractors (Docling, AST, Jupyter, Obsidian)
- Progress tracking with resume capability
- Vector database storage
"""

# Helpers
from .helpers import FileHasher, GhostscriptHelper

# Extractors
from .extractors import (
    DoclingExtractor,
    DOCXExtractor,
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

# Database (synchronous)
from .database import (
    DatabaseConnection,
    SchemaManager,
    VectorRepository,
    VectorStore
)

# Database (asynchronous)
from .async_database import (
    AsyncDatabaseConnection,
    AsyncSchemaManager,
    AsyncVectorRepository,
    AsyncVectorStore
)

__all__ = [
    # Helpers
    'FileHasher',
    'GhostscriptHelper',
    # Extractors
    'DoclingExtractor',
    'DOCXExtractor',
    'MarkdownExtractor',
    'EpubExtractor',
    'ExtractionRouter',
    # Processing
    'MetadataEnricher',
    'DocumentProcessor',
    # Progress
    'ProcessingProgress',
    'ProcessingProgressTracker',
    # Database (synchronous)
    'DatabaseConnection',
    'SchemaManager',
    'VectorRepository',
    'VectorStore',
    # Database (asynchronous)
    'AsyncDatabaseConnection',
    'AsyncSchemaManager',
    'AsyncVectorRepository',
    'AsyncVectorStore',
]
