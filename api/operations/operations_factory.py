"""
Operations factory for backend-agnostic maintenance operations.

Provides runtime selection of maintenance operations based on database backend.
Mirrors the pattern from ingestion.database_factory.DatabaseFactory.
"""
import logging
from typing import Optional, Literal

from ingestion.database_factory import DatabaseFactory
from config import default_config

logger = logging.getLogger(__name__)

BackendType = Literal['sqlite', 'postgresql']


class OperationsFactory:
    """Factory for creating maintenance operations based on database backend.

    Usage:
        # Get integrity checker for current backend
        checker = OperationsFactory.create_integrity_checker()
        result = checker.check()

        # Explicitly specify backend
        checker = OperationsFactory.create_integrity_checker(backend='sqlite')
    """

    @staticmethod
    def get_backend(config=None) -> BackendType:
        """Get the current database backend from config or detect it."""
        return DatabaseFactory.detect_backend(config or default_config.database)

    @staticmethod
    def create_integrity_checker(config=None, backend: Optional[BackendType] = None):
        """Create an IntegrityChecker for the specified backend.

        Args:
            config: Database configuration (uses default_config.database if None)
            backend: 'sqlite' or 'postgresql' (auto-detected if None)

        Returns:
            IntegrityChecker instance appropriate for the backend
        """
        if config is None:
            config = default_config.database
        if backend is None:
            backend = DatabaseFactory.detect_backend(config)

        if backend == 'postgresql':
            from operations.postgres_maintenance import PostgresIntegrityChecker
            return PostgresIntegrityChecker(config)
        else:
            from operations.integrity_checker import IntegrityChecker
            # SQLite checker takes db_path string
            db_path = getattr(config, 'path', None) or str(config)
            return IntegrityChecker(db_path)

    @staticmethod
    def create_orphan_cleaner(config=None, backend: Optional[BackendType] = None):
        """Create an OrphanCleaner for the specified backend.

        Args:
            config: Database configuration (uses default_config.database if None)
            backend: 'sqlite' or 'postgresql' (auto-detected if None)

        Returns:
            OrphanCleaner instance appropriate for the backend
        """
        if config is None:
            config = default_config.database
        if backend is None:
            backend = DatabaseFactory.detect_backend(config)

        if backend == 'postgresql':
            from operations.postgres_maintenance import PostgresOrphanCleaner
            return PostgresOrphanCleaner(config)
        else:
            from operations.orphan_cleaner import OrphanCleaner
            db_path = getattr(config, 'path', None) or str(config)
            return OrphanCleaner(db_path)

    @staticmethod
    def create_stats_collector(config=None, backend: Optional[BackendType] = None):
        """Create a StatsCollector for the specified backend.

        Args:
            config: Database configuration (uses default_config.database if None)
            backend: 'sqlite' or 'postgresql' (auto-detected if None)

        Returns:
            StatsCollector instance appropriate for the backend
        """
        if config is None:
            config = default_config.database
        if backend is None:
            backend = DatabaseFactory.detect_backend(config)

        if backend == 'postgresql':
            from operations.postgres_maintenance import PostgresStatsCollector
            return PostgresStatsCollector(config)
        else:
            # SQLite doesn't have a dedicated StatsCollector
            # Return PostgreSQL one with mock behavior or raise
            logger.warning("StatsCollector not implemented for SQLite, using PostgreSQL version")
            from operations.postgres_maintenance import PostgresStatsCollector
            return PostgresStatsCollector(config)

    @staticmethod
    def create_embedding_rebuilder(config=None, backend: Optional[BackendType] = None):
        """Create an EmbeddingRebuilder for the specified backend.

        Args:
            config: Database configuration (uses default_config.database if None)
            backend: 'sqlite' or 'postgresql' (auto-detected if None)

        Returns:
            EmbeddingRebuilder instance appropriate for the backend
        """
        if config is None:
            config = default_config.database
        if backend is None:
            backend = DatabaseFactory.detect_backend(config)

        if backend == 'postgresql':
            from operations.postgres_embedding_rebuilder import PostgresEmbeddingRebuilder
            return PostgresEmbeddingRebuilder(config)
        else:
            from operations.embedding_rebuilder import EmbeddingRebuilder
            db_path = getattr(config, 'path', None) or str(config)
            return EmbeddingRebuilder(db_path)

    @staticmethod
    def create_partial_rebuilder(config=None, backend: Optional[BackendType] = None):
        """Create a PartialRebuilder for the specified backend.

        Args:
            config: Database configuration (uses default_config.database if None)
            backend: 'sqlite' or 'postgresql' (auto-detected if None)

        Returns:
            PartialRebuilder instance appropriate for the backend
        """
        if config is None:
            config = default_config.database
        if backend is None:
            backend = DatabaseFactory.detect_backend(config)

        if backend == 'postgresql':
            from operations.postgres_partial_rebuilder import PostgresPartialRebuilder
            return PostgresPartialRebuilder(config)
        else:
            from operations.partial_rebuilder import PartialRebuilder
            db_path = getattr(config, 'path', None) or str(config)
            return PartialRebuilder(db_path)

    @staticmethod
    def create_hnsw_rebuilder(config=None, backend: Optional[BackendType] = None):
        """Create an HnswRebuilder for the specified backend.

        Note: PostgreSQL with pgvector doesn't need separate HNSW rebuilding
        as the index is automatically maintained. Returns SQLite version.

        Args:
            config: Database configuration (uses default_config.database if None)
            backend: 'sqlite' or 'postgresql' (auto-detected if None)

        Returns:
            HnswRebuilder instance (SQLite only, returns None for PostgreSQL)
        """
        if config is None:
            config = default_config.database
        if backend is None:
            backend = DatabaseFactory.detect_backend(config)

        if backend == 'postgresql':
            # pgvector maintains HNSW automatically
            logger.info("HNSW rebuilder not needed for PostgreSQL/pgvector")
            return None
        else:
            from operations.hnsw_rebuilder import HnswRebuilder
            db_path = getattr(config, 'path', None) or str(config)
            return HnswRebuilder(db_path)

    @staticmethod
    def create_fts_rebuilder(config=None, backend: Optional[BackendType] = None):
        """Create an FtsRebuilder for the specified backend.

        Note: PostgreSQL uses tsvector which has different semantics.
        Currently returns SQLite FTS rebuilder for SQLite only.

        Args:
            config: Database configuration (uses default_config.database if None)
            backend: 'sqlite' or 'postgresql' (auto-detected if None)

        Returns:
            FtsRebuilder instance (SQLite only, returns None for PostgreSQL)
        """
        if config is None:
            config = default_config.database
        if backend is None:
            backend = DatabaseFactory.detect_backend(config)

        if backend == 'postgresql':
            # PostgreSQL tsvector is maintained differently
            logger.info("FTS rebuilder not needed for PostgreSQL/tsvector")
            return None
        else:
            from operations.fts_rebuilder import FtsRebuilder
            db_path = getattr(config, 'path', None) or str(config)
            return FtsRebuilder(db_path)
