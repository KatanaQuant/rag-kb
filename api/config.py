"""
Configuration constants for RAG system
"""
import os
from pathlib import Path
from dataclasses import dataclass

# Model dimension mapping
MODEL_DIMENSIONS = {
    "sentence-transformers/all-MiniLM-L6-v2": 384,
    "Snowflake/snowflake-arctic-embed-l-v2.0": 1024,
    "Snowflake/snowflake-arctic-embed-m-v2.0": 768,
    "google/embeddinggemma-300m": 768,
    "BAAI/bge-large-en-v1.5": 1024,
    "BAAI/bge-base-en-v1.5": 768,
    "sentence-transformers/static-retrieval-mrl-en-v1": 1024,  # Static embedding, 100-400x faster on CPU
}

@dataclass
class ChunkConfig:
    """Text chunking configuration"""
    size: int = 1000
    overlap: int = 200
    min_size: int = 50
    semantic: bool = True  # Use semantic chunking with Docling (HybridChunker)
    max_tokens: int = 512  # Token limit for semantic chunks

@dataclass
class DatabaseConfig:
    """Database configuration"""
    path: str = "/app/data/rag.db"
    embedding_dim: int = 384
    check_same_thread: bool = False
    require_vec_extension: bool = True

@dataclass
class ModelConfig:
    """Embedding model configuration"""
    name: str = "sentence-transformers/all-MiniLM-L6-v2"
    show_progress: bool = False

    def get_embedding_dim(self) -> int:
        """Get embedding dimension for configured model"""
        return MODEL_DIMENSIONS.get(self.name, 384)

@dataclass
class PathConfig:
    """File path configuration"""
    knowledge_base: Path = Path("/app/knowledge_base")
    data_dir: Path = Path("/app/data")

@dataclass
class WatcherConfig:
    """File watcher configuration"""
    enabled: bool = True
    debounce_seconds: float = 10.0
    batch_size: int = 50

@dataclass
class CacheConfig:
    """Query cache configuration"""
    enabled: bool = True
    max_size: int = 100

@dataclass
class BatchConfig:
    """Batch processing configuration for resource management"""
    size: int = 5
    delay: float = 0.5

@dataclass
class DoclingConfig:
    """Docling PDF extraction configuration"""
    enabled: bool = True  # Default to advanced PDF extraction

@dataclass
class ProcessingConfig:
    """Resumable processing configuration"""
    enabled: bool = True
    batch_size: int = 50
    max_retries: int = 3
    cleanup_completed: bool = False

@dataclass
class FileValidationConfig:
    """File type validation configuration"""
    enabled: bool = True
    action: str = "reject"  # reject|warn|skip (changed from warn in v1.3.0 for security)

@dataclass
class Config:
    """Main configuration container"""
    chunks: ChunkConfig
    database: DatabaseConfig
    model: ModelConfig
    paths: PathConfig
    watcher: WatcherConfig
    cache: CacheConfig
    batch: BatchConfig
    docling: DoclingConfig
    processing: ProcessingConfig
    file_validation: FileValidationConfig

    @classmethod
    def from_env(cls) -> 'Config':
        """Create config from environment - delegates to EnvironmentConfigLoader"""
        from environment_config_loader import EnvironmentConfigLoader
        return EnvironmentConfigLoader().load()

# Default instance
default_config = Config.from_env()
