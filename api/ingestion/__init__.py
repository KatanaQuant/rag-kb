"""
Ingestion package - Document processing and storage.

This package handles the complete document ingestion pipeline:
- Text extraction from various formats (PDF, DOCX, MD, EPUB)
- Semantic chunking via specialized extractors (Docling, AST, Jupyter, Obsidian)
- Progress tracking with resume capability
- Vector database storage

Database Backend Support:
- PostgreSQL + pgvector (default, recommended)
- SQLite + vectorlite (legacy, for development)

Use DatabaseFactory for runtime backend selection:
    from ingestion import DatabaseFactory
    store = DatabaseFactory.create_vector_store(config)
"""

# Helpers
from .helpers import FileHasher, GhostscriptHelper

# Extractors
from .extractors import (
    DoclingExtractor,
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
from .progress import ProcessingProgress

# ============================================================
# Database Abstraction Layer (NEW)
# ============================================================
# Interfaces - abstract contracts for database implementations
from .interfaces import (
    DatabaseConnection as DatabaseConnectionInterface,
    SchemaManager as SchemaManagerInterface,
    VectorStore as VectorStoreInterface,
    DocumentRepository,
    ChunkRepository,
    VectorChunkRepository,
    FTSChunkRepository,
    SearchRepository,
    GraphRepository,
    ProgressTracker,
    SearchResult,
)

# Factory - runtime backend selection
from .database_factory import DatabaseFactory, get_vector_store, get_backend

# ============================================================
# Concrete Implementations (explicit names - no aliases)
# ============================================================
# PostgreSQL (production)
from .postgres_connection import PostgresConnection, PostgresSchemaManager
from .postgres_database import PostgresVectorRepository, PostgresVectorStore
from .postgres_progress import PostgresProgressTracker

# SQLite (legacy/testing) - import from submodules directly:
#   from ingestion.database import DatabaseConnection, SchemaManager, VectorStore
#   from ingestion.progress import ProcessingProgressTracker

# Database (asynchronous) - PostgreSQL + asyncpg
from .async_postgres import (
    AsyncPostgresConnection as AsyncDatabaseConnection,
    AsyncPostgresSchemaManager as AsyncSchemaManager,
    AsyncPostgresVectorRepository as AsyncVectorRepository,
    AsyncPostgresVectorStore as AsyncVectorStore,
)

# Async adapter for unified architecture
from .async_adapter import AsyncVectorStoreAdapter

__all__ = [
    # Helpers
    'FileHasher',
    'GhostscriptHelper',
    # Extractors
    'DoclingExtractor',
    'MarkdownExtractor',
    'EpubExtractor',
    'ExtractionRouter',
    # Processing
    'MetadataEnricher',
    'DocumentProcessor',
    # Progress
    'ProcessingProgress',
    # Database Abstraction
    'DatabaseFactory',
    'get_vector_store',
    'get_backend',
    # Interfaces (for type hints and custom implementations)
    'DatabaseConnectionInterface',
    'SchemaManagerInterface',
    'VectorStoreInterface',
    'DocumentRepository',
    'ChunkRepository',
    'VectorChunkRepository',
    'FTSChunkRepository',
    'SearchRepository',
    'GraphRepository',
    'ProgressTracker',
    'SearchResult',
    # PostgreSQL (synchronous) - explicit names
    'PostgresConnection',
    'PostgresSchemaManager',
    'PostgresVectorRepository',
    'PostgresVectorStore',
    'PostgresProgressTracker',
    # PostgreSQL (asynchronous)
    'AsyncDatabaseConnection',
    'AsyncSchemaManager',
    'AsyncVectorRepository',
    'AsyncVectorStore',
    # Async adapter for unified architecture
    'AsyncVectorStoreAdapter',
]
