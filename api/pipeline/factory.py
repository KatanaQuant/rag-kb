"""Pipeline factory for creating pipeline components from configuration.

Follows Sandi Metz principles:
- Dependency injection via constructor
- Factory creates components from config
- Single responsibility: component creation

All pipeline stages are factory-created and YAML-configurable:
- Extractors: DoclingExtractor, CodeExtractor, EpubExtractor, MarkdownExtractor, JupyterExtractor
- Chunkers: HybridChunker, SemanticChunker, FixedChunker
- Embedders: SentenceTransformerEmbedder
- Rerankers: BGEReranker, NoopReranker
"""

import logging
from pathlib import Path
from typing import Optional, Dict, Type

from pipeline.config import PipelineConfig, RerankingConfig
from pipeline.interfaces.reranker import RerankerInterface, NoopReranker
from pipeline.interfaces.embedder import EmbedderInterface
from pipeline.interfaces.extractor import ExtractorInterface
from pipeline.interfaces.chunker import ChunkerInterface

logger = logging.getLogger(__name__)


class PipelineFactory:
    """Factory for creating pipeline components from configuration.

    Usage:
        config = PipelineConfig.load()
        factory = PipelineFactory(config)
        reranker = factory.create_reranker()
        extractor = factory.create_extractor('.pdf')
        chunker = factory.create_chunker()
    """

    # Registry of extractors by extension
    _extractor_registry: Dict[str, Type[ExtractorInterface]] = {}
    _extractors_loaded = False

    def __init__(self, config: PipelineConfig):
        """Initialize factory with configuration.

        Args:
            config: Pipeline configuration
        """
        self.config = config
        self._load_extractors()

    @classmethod
    def _load_extractors(cls):
        """Lazy-load extractor registry from implementations."""
        if cls._extractors_loaded:
            return

        # Import extractors (deferred to avoid circular imports)
        from ingestion.extractors.docling_extractor import DoclingExtractor
        from ingestion.extractors.epub_extractor import EpubExtractor
        from ingestion.extractors.code_extractor import CodeExtractor
        from ingestion.extractors.markdown_extractor import MarkdownExtractor
        from ingestion.jupyter_extractor import JupyterExtractor

        # Build registry from SUPPORTED_EXTENSIONS
        extractors = [
            DoclingExtractor,
            EpubExtractor,
            CodeExtractor,
            MarkdownExtractor,
            JupyterExtractor,
        ]

        for extractor_cls in extractors:
            for ext in extractor_cls.SUPPORTED_EXTENSIONS:
                cls._extractor_registry[ext] = extractor_cls

        cls._extractors_loaded = True
        logger.debug(f"Loaded {len(cls._extractor_registry)} extractor mappings")

    def create_extractor(self, extension: str) -> ExtractorInterface:
        """Create extractor for the given file extension.

        Args:
            extension: File extension (e.g., '.pdf', '.py')

        Returns:
            ExtractorInterface implementation for the extension

        Raises:
            ValueError: If extension is not supported
        """
        ext = extension.lower()
        if not ext.startswith('.'):
            ext = f'.{ext}'

        if ext not in self._extractor_registry:
            supported = sorted(self._extractor_registry.keys())
            raise ValueError(
                f"Unsupported extension: {extension}. "
                f"Supported: {', '.join(supported)}"
            )

        extractor_cls = self._extractor_registry[ext]
        return extractor_cls()

    def get_extractor_for_file(self, file_path: Path) -> ExtractorInterface:
        """Create extractor based on file extension.

        Args:
            file_path: Path to file

        Returns:
            ExtractorInterface implementation
        """
        return self.create_extractor(file_path.suffix)

    def create_chunker(self) -> ChunkerInterface:
        """Create chunker based on configuration.

        Returns:
            ChunkerInterface implementation based on config.chunking.strategy
        """
        strategy = self.config.chunking.strategy.lower()
        max_tokens = self.config.chunking.max_tokens

        if strategy == "hybrid":
            from pipeline.chunkers.hybrid_chunker import HybridChunker
            return HybridChunker(max_tokens=max_tokens)
        elif strategy == "semantic":
            from pipeline.chunkers.semantic_chunker import SemanticChunker
            return SemanticChunker(max_tokens=max_tokens)
        elif strategy == "fixed":
            from pipeline.chunkers.fixed_chunker import FixedChunker
            return FixedChunker(max_tokens=max_tokens)
        else:
            logger.warning(f"Unknown chunking strategy '{strategy}', using hybrid")
            from pipeline.chunkers.hybrid_chunker import HybridChunker
            return HybridChunker(max_tokens=max_tokens)

    def supports_extension(self, extension: str) -> bool:
        """Check if an extension is supported by any extractor.

        Args:
            extension: File extension (with or without leading dot)

        Returns:
            True if extension is supported
        """
        ext = extension.lower()
        if not ext.startswith('.'):
            ext = f'.{ext}'
        return ext in self._extractor_registry

    def get_supported_extensions(self) -> list:
        """Get list of all supported file extensions.

        Returns:
            Sorted list of supported extensions
        """
        return sorted(self._extractor_registry.keys())

    def create_reranker(self) -> RerankerInterface:
        """Create reranker based on configuration.

        Returns:
            RerankerInterface implementation (BGEReranker or NoopReranker)
        """
        rerank_config = self.config.reranking

        if not rerank_config.enabled:
            logger.info("Reranking disabled, using NoopReranker")
            return NoopReranker()

        logger.info(f"Creating BGEReranker with model: {rerank_config.model}")
        from pipeline.rerankers.bge_reranker import BGEReranker
        return BGEReranker(
            model_name=rerank_config.model,
            enable_timing=True
        )

    def create_embedder(self, model) -> EmbedderInterface:
        """Create embedder based on configuration.

        Args:
            model: SentenceTransformer model instance

        Returns:
            EmbedderInterface implementation
        """
        from pipeline.embedders.sentence_transformer_embedder import SentenceTransformerEmbedder
        return SentenceTransformerEmbedder(
            model=model,
            batch_size=self.config.embedding.batch_size,
            enable_timing=True
        )

    @property
    def reranking_top_n(self) -> int:
        """Get the number of candidates to retrieve for reranking."""
        return self.config.reranking.top_n

    @property
    def reranking_enabled(self) -> bool:
        """Check if reranking is enabled."""
        return self.config.reranking.enabled

    @classmethod
    def from_yaml(cls, path: Path) -> 'PipelineFactory':
        """Create factory from YAML configuration file.

        Args:
            path: Path to pipeline.yaml

        Returns:
            PipelineFactory instance
        """
        config = PipelineConfig.from_yaml(path)
        return cls(config)

    @classmethod
    def default(cls) -> 'PipelineFactory':
        """Create factory with default/environment configuration.

        Tries to load from YAML, falls back to environment variables.

        Returns:
            PipelineFactory instance
        """
        config = PipelineConfig.load()
        return cls(config)
