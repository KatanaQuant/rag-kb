"""Pipeline configuration dataclasses.

Defines configuration for all pipeline stages:
- Extraction: Document text extraction settings
- Chunking: Text chunking strategy settings
- Embedding: Embedding model settings
- Reranking: Search result reranking settings
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class ExtractionConfig:
    """Configuration for document extraction."""
    provider: str = "docling"


@dataclass
class ChunkingConfig:
    """Configuration for text chunking."""
    strategy: str = "hybrid"
    max_tokens: int = 512


@dataclass
class EmbeddingConfig:
    """Configuration for text embedding."""
    provider: str = "sentence-transformers"
    model: str = "Snowflake/snowflake-arctic-embed-l-v2.0"
    batch_size: int = 32


@dataclass
class RerankingConfig:
    """Configuration for search result reranking."""
    enabled: bool = True  # ON by default
    model: str = "BAAI/bge-reranker-large"
    top_n: int = 20  # Retrieve this many, rerank to top_k


@dataclass
class PipelineConfig:
    """Complete pipeline configuration."""
    extraction: ExtractionConfig = field(default_factory=ExtractionConfig)
    chunking: ChunkingConfig = field(default_factory=ChunkingConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    reranking: RerankingConfig = field(default_factory=RerankingConfig)

    @classmethod
    def from_yaml(cls, path: Path) -> 'PipelineConfig':
        """Load configuration from YAML file.

        Args:
            path: Path to pipeline.yaml config file

        Returns:
            PipelineConfig instance

        Raises:
            FileNotFoundError: If config file doesn't exist
        """
        with open(path) as f:
            data = yaml.safe_load(f)

        return cls._from_dict(data or {})

    @classmethod
    def from_env(cls) -> 'PipelineConfig':
        """Load configuration from environment variables.

        Provides backward compatibility fallback when YAML not available.
        Environment variables override defaults.
        """
        extraction = ExtractionConfig(
            provider=os.getenv("EXTRACTION_PROVIDER", "docling")
        )

        chunking = ChunkingConfig(
            strategy=os.getenv("CHUNK_STRATEGY", "hybrid"),
            max_tokens=int(os.getenv("CHUNK_MAX_TOKENS", "512"))
        )

        embedding = EmbeddingConfig(
            provider=os.getenv("EMBEDDING_PROVIDER", "sentence-transformers"),
            model=os.getenv("MODEL_NAME", "Snowflake/snowflake-arctic-embed-l-v2.0"),
            batch_size=int(os.getenv("EMBEDDING_BATCH_SIZE", "32"))
        )

        reranking = RerankingConfig(
            enabled=os.getenv("RERANKING_ENABLED", "true").lower() == "true",
            model=os.getenv("RERANKING_MODEL", "BAAI/bge-reranker-large"),
            top_n=int(os.getenv("RERANKING_TOP_N", "20"))
        )

        return cls(
            extraction=extraction,
            chunking=chunking,
            embedding=embedding,
            reranking=reranking
        )

    @classmethod
    def load(cls, config_path: Optional[Path] = None) -> 'PipelineConfig':
        """Load configuration from YAML if available, else from environment.

        Args:
            config_path: Optional path to config file. If None, tries default locations.

        Returns:
            PipelineConfig instance
        """
        if config_path and config_path.exists():
            return cls.from_yaml(config_path)

        # Try default locations
        default_paths = [
            Path("config/pipeline.yaml"),
            Path("/app/config/pipeline.yaml"),
            Path("/app/yara_config/pipeline.yaml"),  # Docker mount location
        ]

        for path in default_paths:
            if path.exists():
                return cls.from_yaml(path)

        # Fallback to environment variables
        return cls.from_env()

    @classmethod
    def _from_dict(cls, data: dict) -> 'PipelineConfig':
        """Create config from dictionary (parsed YAML)."""
        extraction_data = data.get("extraction", {})
        chunking_data = data.get("chunking", {})
        embedding_data = data.get("embedding", {})
        reranking_data = data.get("reranking", {})

        return cls(
            extraction=ExtractionConfig(
                provider=extraction_data.get("provider", "docling")
            ),
            chunking=ChunkingConfig(
                strategy=chunking_data.get("strategy", "hybrid"),
                max_tokens=chunking_data.get("max_tokens", 512)
            ),
            embedding=EmbeddingConfig(
                provider=embedding_data.get("provider", "sentence-transformers"),
                model=embedding_data.get("model", "Snowflake/snowflake-arctic-embed-l-v2.0"),
                batch_size=embedding_data.get("batch_size", 32)
            ),
            reranking=RerankingConfig(
                enabled=reranking_data.get("enabled", True),
                model=reranking_data.get("model", "BAAI/bge-reranker-large"),
                top_n=reranking_data.get("top_n", 20)
            )
        )
