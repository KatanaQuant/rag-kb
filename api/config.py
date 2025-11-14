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
}


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

    def get_embedding_dim(self) -> int:
        """Get embedding dimension for configured model"""
        return MODEL_DIMENSIONS.get(self.name, 384)


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
        model = ModelConfig(
            name=os.getenv("MODEL_NAME", ModelConfig.name)
        )
        return cls(
            chunks=ChunkConfig(),
            database=DatabaseConfig(
                embedding_dim=model.get_embedding_dim()
            ),
            model=model,
            paths=PathConfig()
        )


# Default instance
default_config = Config.from_env()
