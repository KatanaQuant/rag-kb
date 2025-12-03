"""
Extraction router.

Routes extraction requests to specialized extractors based on file type.
Uses PipelineFactory for component creation - fully modular and YAML-configurable.
"""
import logging
from pathlib import Path
from typing import Dict, Optional

from config import default_config
from domain_models import ExtractionResult
from pipeline.factory import PipelineFactory
from pipeline.interfaces.extractor import ExtractorInterface
from ingestion.obsidian_extractor import ObsidianExtractor
from ingestion.obsidian_graph import ObsidianGraphBuilder
from ingestion.obsidian_detector import get_obsidian_detector

logger = logging.getLogger(__name__)


class ExtractionRouter:
    """Routes extraction requests to specialized extractors based on file type.

    Uses PipelineFactory for extractor creation, enabling:
    - YAML configuration (config/pipeline.yaml)
    - Easy swapping of extractors
    - Consistent interface across all file types
    """

    def __init__(self, config=default_config, factory: Optional[PipelineFactory] = None):
        """Initialize router with configuration and factory.

        Args:
            config: Application configuration
            factory: Optional PipelineFactory. If None, creates default factory.
        """
        self.config = config
        self.factory = factory or PipelineFactory.default()
        self.last_method = None  # Track which method was used
        self.obsidian_graph = ObsidianGraphBuilder()  # Shared graph for vault
        self.obsidian_detector = get_obsidian_detector()
        # Cache extractor instances for reuse
        self._extractor_cache: Dict[str, ExtractorInterface] = {}

    def extract(self, file_path: Path) -> ExtractionResult:
        """Extract text based on file extension.

        Uses factory-created extractors for modularity.
        Special handling for Obsidian markdown (uses composition pattern).
        """
        # Reset last_method to prevent stale values from previous extractions
        self.last_method = None

        ext = file_path.suffix.lower()
        self._validate_extension(ext)

        # Special handling for markdown: detect Obsidian vs regular
        if ext in ['.md', '.markdown']:
            return self._extract_markdown_intelligently(file_path)

        # Get or create extractor via factory
        extractor = self._get_extractor(ext)
        self.last_method = extractor.name

        return extractor.extract(file_path)

    def _get_extractor(self, extension: str) -> ExtractorInterface:
        """Get cached extractor or create via factory.

        Args:
            extension: File extension (e.g., '.pdf')

        Returns:
            ExtractorInterface implementation
        """
        if extension not in self._extractor_cache:
            self._extractor_cache[extension] = self.factory.create_extractor(extension)
        return self._extractor_cache[extension]

    def _extract_markdown_intelligently(self, file_path: Path) -> ExtractionResult:
        """Choose between Obsidian Graph-RAG or regular markdown extraction.

        Obsidian uses composition pattern (different signature: extract(path, graph_builder))
        rather than implementing ExtractorInterface. See design decision in state.json.
        """
        if self.obsidian_detector.is_obsidian_note(file_path):
            self.last_method = 'obsidian_graph_rag'
            return ObsidianExtractor.extract(file_path, self.obsidian_graph)
        else:
            extractor = self._get_extractor('.md')
            self.last_method = extractor.name
            return extractor.extract(file_path)

    def get_last_method(self) -> str:
        """Get the last extraction method used."""
        return self.last_method or 'unknown'

    def get_obsidian_graph(self) -> ObsidianGraphBuilder:
        """Get the shared Obsidian graph (for persistence)."""
        return self.obsidian_graph

    def get_supported_extensions(self) -> list:
        """Get list of supported file extensions from factory."""
        return self.factory.get_supported_extensions()

    def _validate_extension(self, ext: str):
        """Validate extension is supported."""
        if not self.factory.supports_extension(ext):
            supported = self.factory.get_supported_extensions()
            raise ValueError(f"Unsupported: {ext}. Supported: {', '.join(supported)}")
