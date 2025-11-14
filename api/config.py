"""
Configuration constants for RAG system
"""
import os
from pathlib import Path
from dataclasses import dataclass


@dataclass
class ChunkConfig:
    """Text chunking configuration"""
    size: int = 1000
    overlap: int = 200
    min_size: int = 50


@dataclass
class DatabaseConfig:
    """Database configuration"""
    path: str = "/app/data/rag.db"
    embedding_dim: int = 384
    check_same_thread: bool = False


@dataclass
class ModelConfig:
    """Embedding model configuration"""
    name: str = "sentence-transformers/all-MiniLM-L6-v2"
    show_progress: bool = False


@dataclass
class PathConfig:
    """File path configuration"""
    knowledge_base: Path = Path("/app/knowledge_base")
    data_dir: Path = Path("/app/data")


@dataclass
class Config:
    """Main configuration container"""
    chunks: ChunkConfig
    database: DatabaseConfig
    model: ModelConfig
    paths: PathConfig

    @classmethod
    def from_env(cls) -> 'Config':
        """Create config from environment"""
        return cls(
            chunks=ChunkConfig(),
            database=DatabaseConfig(),
            model=ModelConfig(
                name=os.getenv("MODEL_NAME", ModelConfig.name)
            ),
            paths=PathConfig()
        )


# Default instance
default_config = Config.from_env()
