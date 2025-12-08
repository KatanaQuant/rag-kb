"""
Database factory for runtime backend selection.

Selects PostgreSQL or SQLite implementation based on DATABASE_URL.

This module provides the primary entry point for obtaining database
connections and vector stores. It abstracts away the backend implementation
details, allowing the application to work with either PostgreSQL (pgvector)
or SQLite (vectorlite) seamlessly.

Usage:
    from ingestion.database_factory import DatabaseFactory

    # Automatically selects based on DATABASE_URL
    store = DatabaseFactory.create_vector_store(config)

    # Or explicitly select backend
    store = DatabaseFactory.create_vector_store(config, backend='postgresql')

    # Simple convenience function
    from ingestion.database_factory import get_vector_store
    store = get_vector_store()

Backend Detection:
    - postgresql:// or postgres:// -> PostgreSQL + pgvector
    - sqlite:// or sqlite: -> SQLite + vectorlite
    - Config with 'host' attribute -> PostgreSQL
    - Config with 'path' attribute -> SQLite
    - Default fallback -> PostgreSQL
"""
import logging
from typing import Optional, Literal, TYPE_CHECKING

if TYPE_CHECKING:
    from config import DatabaseConfig
    from .interfaces import (
        DatabaseConnection,
        SchemaManager,
        VectorStore,
        HybridSearcher,
    )

logger = logging.getLogger(__name__)

BackendType = Literal['postgresql', 'sqlite']


class DatabaseFactory:
    """Factory for creating database implementations.

    Supports runtime selection of database backend based on:
    1. Explicit backend parameter
    2. DATABASE_URL environment variable
    3. Config database_url field

    This enables:
    - Easy testing with SQLite in-memory databases
    - Production deployment with PostgreSQL
    - Migration between backends without code changes

    Example:
        # Auto-detect from config
        store = DatabaseFactory.create_vector_store(config)

        # Explicit backend
        conn = DatabaseFactory.create_connection(config, backend='sqlite')

        # Force PostgreSQL regardless of config
        store = DatabaseFactory.create_vector_store(config, backend='postgresql')
    """

    @staticmethod
    def detect_backend(config: 'DatabaseConfig') -> BackendType:
        """Detect database backend from config.

        Examines the config object to determine which backend to use.
        Detection priority:
        1. database_url prefix (postgresql://, postgres://, sqlite://)
        2. Presence of host attribute (PostgreSQL-style config)
        3. Presence of path attribute (SQLite-style config)
        4. Default to PostgreSQL

        Args:
            config: Database configuration object with database_url or
                   host/path attributes.

        Returns:
            'postgresql' or 'sqlite' based on configuration.
        """
        db_url = getattr(config, 'database_url', '')

        # Check URL prefix first (most explicit)
        if db_url:
            if db_url.startswith('postgresql://') or db_url.startswith('postgres://'):
                return 'postgresql'
            elif db_url.startswith('sqlite://') or db_url.startswith('sqlite:'):
                return 'sqlite'

        # Check for backend-specific attributes
        if hasattr(config, 'host') and getattr(config, 'host', None):
            # PostgreSQL config typically has host/port
            return 'postgresql'
        elif hasattr(config, 'path') and getattr(config, 'path', None):
            # SQLite config has path to database file
            return 'sqlite'

        # Default to PostgreSQL (primary supported backend)
        logger.warning("Could not detect backend from config, defaulting to PostgreSQL")
        return 'postgresql'

    @staticmethod
    def create_connection(config: 'DatabaseConfig' = None,
                         backend: Optional[BackendType] = None) -> 'DatabaseConnection':
        """Create database connection for the specified backend.

        Creates a low-level connection wrapper that handles:
        - Connection establishment
        - Extension loading (pgvector or vectorlite)
        - Connection lifecycle management

        Args:
            config: Database configuration. Uses default_config.database if None.
            backend: Explicit backend ('postgresql' or 'sqlite').
                    Auto-detects from config if None.

        Returns:
            DatabaseConnection implementation (PostgresConnection or
            SqliteConnection).

        Raises:
            ValueError: If backend is not supported or unavailable.
            RuntimeError: If connection or extension loading fails.

        Example:
            conn = DatabaseFactory.create_connection(config)
            db = conn.connect()
            # ... use db ...
            conn.close()
        """
        if config is None:
            from config import default_config
            config = default_config.database

        if backend is None:
            backend = DatabaseFactory.detect_backend(config)

        logger.debug(f"Creating database connection with backend: {backend}")

        if backend == 'postgresql':
            from .postgres_connection import PostgresConnection
            return PostgresConnection(config)
        elif backend == 'sqlite':
            # SQLite implementation - imports from existing database.py
            try:
                from .database import DatabaseConnection as SqliteDatabaseConnection
                return SqliteDatabaseConnection(config)
            except ImportError as e:
                raise ValueError(
                    f"SQLite backend not available. Install sqlite/vectorlite dependencies. "
                    f"Error: {e}"
                )
        else:
            raise ValueError(f"Unsupported backend: {backend}. Use 'postgresql' or 'sqlite'.")

    @staticmethod
    def create_schema_manager(conn, config: 'DatabaseConfig' = None,
                             backend: Optional[BackendType] = None) -> 'SchemaManager':
        """Create schema manager for the specified backend.

        Schema managers create all required database tables:
        - documents: File metadata
        - chunks: Text content
        - vec_chunks: Vector embeddings
        - fts_chunks: Full-text search
        - graph tables: Knowledge graph
        - processing_progress: Resume support
        - security_scan_cache: Malware scan results

        Args:
            conn: Database connection object from create_connection().connect().
            config: Database configuration. Uses default_config.database if None.
            backend: Explicit backend. Auto-detects from config if None.

        Returns:
            SchemaManager implementation.

        Raises:
            ValueError: If backend is not supported or unavailable.

        Example:
            conn = DatabaseFactory.create_connection(config)
            db = conn.connect()
            schema = DatabaseFactory.create_schema_manager(db, config)
            schema.create_schema()
        """
        if config is None:
            from config import default_config
            config = default_config.database

        if backend is None:
            backend = DatabaseFactory.detect_backend(config)

        if backend == 'postgresql':
            from .postgres_connection import PostgresSchemaManager
            return PostgresSchemaManager(conn, config)
        elif backend == 'sqlite':
            try:
                from .database import SchemaManager as SqliteSchemaManager
                return SqliteSchemaManager(conn, config)
            except ImportError as e:
                raise ValueError(f"SQLite backend not available. Error: {e}")
        else:
            raise ValueError(f"Unsupported backend: {backend}")

    @staticmethod
    def create_vector_store(config: 'DatabaseConfig' = None,
                           backend: Optional[BackendType] = None) -> 'VectorStore':
        """Create vector store for the specified backend.

        This is the main entry point for applications. The VectorStore
        provides a high-level interface for:
        - Document indexing (add_document)
        - Semantic search (search with hybrid FTS)
        - Document management (delete, stats)

        The returned store is thread-safe and handles:
        - Connection management
        - Schema initialization
        - Hybrid search coordination
        - Proper resource cleanup

        Args:
            config: Database configuration. Uses default_config.database if None.
            backend: Explicit backend ('postgresql' or 'sqlite').
                    Auto-detects from config if None.

        Returns:
            VectorStore implementation (PostgresVectorStore or VectorStore).

        Raises:
            ValueError: If backend is not supported or unavailable.
            RuntimeError: If database initialization fails.

        Example:
            # Simple usage with auto-detection
            store = DatabaseFactory.create_vector_store()

            # Check and index document
            if not store.is_document_indexed(path, hash_val):
                store.add_document(path, hash_val, chunks, embeddings)

            # Search
            results = store.search(embedding, top_k=5, query_text="search")

            # Cleanup
            store.close()
        """
        if config is None:
            from config import default_config
            config = default_config.database

        if backend is None:
            backend = DatabaseFactory.detect_backend(config)

        logger.info(f"Creating VectorStore with backend: {backend}")

        if backend == 'postgresql':
            from .postgres_database import PostgresVectorStore
            return PostgresVectorStore(config)
        elif backend == 'sqlite':
            try:
                from .database import VectorStore as SqliteVectorStore
                return SqliteVectorStore(config)
            except ImportError as e:
                raise ValueError(
                    f"SQLite backend not available. Check vectorlite installation. "
                    f"Error: {e}"
                )
        else:
            raise ValueError(f"Unsupported backend: {backend}")

    @staticmethod
    def create_progress_tracker(config: 'DatabaseConfig' = None,
                               backend: Optional[BackendType] = None):
        """Create progress tracker for resumable processing.

        Progress trackers persist processing state to enable resume
        after interruption. Each backend has its own implementation.

        Args:
            config: Database configuration. Uses default_config.database if None.
            backend: Explicit backend. Auto-detects from config if None.

        Returns:
            ProgressTracker implementation.

        Raises:
            ValueError: If backend is not supported or unavailable.
        """
        if config is None:
            from config import default_config
            config = default_config.database

        if backend is None:
            backend = DatabaseFactory.detect_backend(config)

        if backend == 'postgresql':
            from .postgres_progress import PostgresProgressTracker
            return PostgresProgressTracker(config)
        elif backend == 'sqlite':
            try:
                from .progress import ProcessingProgressTracker
                return ProcessingProgressTracker(config)
            except ImportError as e:
                raise ValueError(f"SQLite backend not available. Error: {e}")
        else:
            raise ValueError(f"Unsupported backend: {backend}")

    @staticmethod
    def create_hybrid_searcher(conn, config: 'DatabaseConfig' = None,
                               backend: Optional[BackendType] = None):
        """Create hybrid searcher for the specified backend.

        Hybrid search combines vector similarity with BM25 keyword search
        using Reciprocal Rank Fusion for better results than either alone.

        Args:
            conn: Database connection object from create_connection().connect()
                  or from VectorStore.conn property.
            config: Database configuration. Uses default_config.database if None.
            backend: Explicit backend. Auto-detects from config if None.

        Returns:
            HybridSearcher implementation (PostgresHybridSearcher or HybridSearcher).

        Raises:
            ValueError: If backend is not supported or unavailable.

        Example:
            store = DatabaseFactory.create_vector_store()
            searcher = DatabaseFactory.create_hybrid_searcher(store.conn)
            results = searcher.search(query, vector_results, top_k=10)
        """
        if config is None:
            from config import default_config
            config = default_config.database

        if backend is None:
            backend = DatabaseFactory.detect_backend(config)

        logger.debug(f"Creating hybrid searcher with backend: {backend}")

        if backend == 'postgresql':
            from hybrid_search import PostgresHybridSearcher
            return PostgresHybridSearcher(conn)
        elif backend == 'sqlite':
            try:
                from hybrid_search import HybridSearcher as SqliteHybridSearcher
                return SqliteHybridSearcher(conn)
            except ImportError as e:
                raise ValueError(f"SQLite hybrid search not available. Error: {e}")
        else:
            raise ValueError(f"Unsupported backend: {backend}")

    @staticmethod
    def get_backend_info(config: 'DatabaseConfig' = None) -> dict:
        """Get information about the detected backend.

        Useful for diagnostics and logging.

        Args:
            config: Database configuration. Uses default_config.database if None.

        Returns:
            Dictionary with:
            - backend: 'postgresql' or 'sqlite'
            - database_url: The URL if configured
            - available: Whether the backend can be imported
        """
        if config is None:
            from config import default_config
            config = default_config.database

        backend = DatabaseFactory.detect_backend(config)
        db_url = getattr(config, 'database_url', '')

        # Check availability
        available = False
        error_msg = None

        if backend == 'postgresql':
            try:
                import psycopg2  # noqa: F401
                available = True
            except ImportError as e:
                error_msg = str(e)
        elif backend == 'sqlite':
            try:
                import vectorlite_py  # noqa: F401
                available = True
            except ImportError as e:
                error_msg = str(e)

        return {
            'backend': backend,
            'database_url': db_url[:50] + '...' if len(db_url) > 50 else db_url,
            'available': available,
            'error': error_msg,
        }


def get_vector_store(config: 'DatabaseConfig' = None) -> 'VectorStore':
    """Get a VectorStore instance using auto-detected backend.

    Simple convenience wrapper around DatabaseFactory.create_vector_store().
    This is the recommended entry point for most applications.

    Args:
        config: Database configuration. Uses default_config.database if None.

    Returns:
        VectorStore implementation ready for use.

    Example:
        from ingestion.database_factory import get_vector_store

        store = get_vector_store()
        results = store.search(embedding, top_k=5)
        store.close()
    """
    return DatabaseFactory.create_vector_store(config)


def get_backend() -> BackendType:
    """Get the currently configured backend type.

    Convenience function to check which backend will be used.

    Returns:
        'postgresql' or 'sqlite' based on default configuration.

    Example:
        from ingestion.database_factory import get_backend

        if get_backend() == 'postgresql':
            print("Using PostgreSQL + pgvector")
        else:
            print("Using SQLite + vectorlite")
    """
    from config import default_config
    return DatabaseFactory.detect_backend(default_config.database)
