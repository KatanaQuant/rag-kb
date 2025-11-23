"""
Ingestion package - Document processing, chunking, and storage

This package handles the complete document ingestion pipeline:
- Text extraction from various formats (PDF, DOCX, MD, TXT, EPUB)
- Semantic and fixed-size chunking
- Progress tracking with resume capability
- Vector database storage
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

# Chunking
from .chunking import (
    ChunkingStrategy,
    SemanticChunkingStrategy,
    FixedChunkingStrategy,
    TextChunker
)

# Processing
from .processing import (
    ChunkedTextProcessor,
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
    # Chunking
    'ChunkingStrategy',
    'SemanticChunkingStrategy',
    'FixedChunkingStrategy',
    'TextChunker',
    # Processing
    'ChunkedTextProcessor',
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
