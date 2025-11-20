"""
Environment configuration loader.

Fixes Feature Envy: Logic for reading environment variables
lives with the data source (environment) rather than in Config dataclass.
"""
import os
from config import (
    Config, ModelConfig, PathConfig, WatcherConfig, CacheConfig,
    BatchConfig, DoclingConfig, ProcessingConfig, ChunkConfig
)

class EnvironmentConfigLoader:
    """Loads configuration from environment variables.

    Single Responsibility: Environment access logic.
    """

    def load(self) -> Config:
        """Create Config from environment variables"""
        model = self._load_model_config()
        watcher = self._load_watcher_config()
        cache = self._load_cache_config()
        batch = self._load_batch_config()
        docling = self._load_docling_config()
        processing = self._load_processing_config()
        chunks = self._load_chunk_config()

        return Config(
            chunks=chunks,
            database=self._load_database_config(model.get_embedding_dim()),
            model=model,
            paths=PathConfig(),
            watcher=watcher,
            cache=cache,
            batch=batch,
            docling=docling,
            processing=processing
        )

    def _load_model_config(self) -> ModelConfig:
        """Load model configuration from environment"""
        return ModelConfig(
            name=self._get_optional("MODEL_NAME", ModelConfig.name)
        )

    def _load_watcher_config(self) -> WatcherConfig:
        """Load file watcher configuration from environment"""
        return WatcherConfig(
            enabled=self._get_bool("WATCH_ENABLED", True),
            debounce_seconds=self._get_float("WATCH_DEBOUNCE_SECONDS", 10.0),
            batch_size=self._get_int("WATCH_BATCH_SIZE", 50)
        )

    def _load_cache_config(self) -> CacheConfig:
        """Load cache configuration from environment"""
        return CacheConfig(
            enabled=self._get_bool("CACHE_ENABLED", True),
            max_size=self._get_int("CACHE_MAX_SIZE", 100)
        )

    def _load_batch_config(self) -> BatchConfig:
        """Load batch processing configuration from environment"""
        return BatchConfig(
            size=self._get_int("BATCH_SIZE", 5),
            delay=self._get_float("BATCH_DELAY", 0.5)
        )

    def _load_docling_config(self) -> DoclingConfig:
        """Load Docling PDF configuration from environment"""
        return DoclingConfig(
            enabled=self._get_bool("USE_DOCLING", True)
        )

    def _load_processing_config(self) -> ProcessingConfig:
        """Load processing configuration from environment"""
        from dataclasses import dataclass
        return ProcessingConfig(
            enabled=self._get_bool("RESUMABLE_PROCESSING", True),
            batch_size=self._get_int("PROCESSING_BATCH_SIZE", 50),
            max_retries=self._get_int("PROCESSING_MAX_RETRIES", 3),
            cleanup_completed=self._get_bool("CLEANUP_COMPLETED_PROGRESS", False)
        )

    def _load_chunk_config(self) -> ChunkConfig:
        """Load chunking configuration from environment"""
        return ChunkConfig(
            semantic=self._get_bool("SEMANTIC_CHUNKING", True),
            max_tokens=self._get_int("CHUNK_MAX_TOKENS", 512)
        )

    def _load_database_config(self, embedding_dim: int):
        """Load database configuration from environment"""
        from config import DatabaseConfig
        return DatabaseConfig(embedding_dim=embedding_dim)

    def _get_optional(self, key: str, default: str) -> str:
        """Get optional string environment variable"""
        return os.getenv(key, default)

    def _get_bool(self, key: str, default: bool) -> bool:
        """Get boolean environment variable"""
        value = os.getenv(key, str(default).lower())
        return value.lower() == "true"

    def _get_int(self, key: str, default: int) -> int:
        """Get integer environment variable"""
        value = os.getenv(key, str(default))
        return int(value)

    def _get_float(self, key: str, default: float) -> float:
        """Get float environment variable"""
        value = os.getenv(key, str(default))
        return float(value)
