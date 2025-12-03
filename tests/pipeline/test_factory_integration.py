"""Integration tests for PipelineFactory and PipelineConfig."""

import pytest
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

from pipeline.factory import PipelineFactory
from pipeline.config import PipelineConfig, RerankingConfig, ChunkingConfig
from pipeline.interfaces.reranker import NoopReranker
from pipeline.interfaces.extractor import ExtractorInterface
from pipeline.interfaces.chunker import ChunkerInterface


class TestPipelineFactoryReranker:
    """Test PipelineFactory reranker creation."""

    def test_factory_creates_noop_when_disabled(self):
        """Factory must return NoopReranker when reranking disabled."""
        config = PipelineConfig(
            reranking=RerankingConfig(enabled=False)
        )
        factory = PipelineFactory(config)
        reranker = factory.create_reranker()

        assert isinstance(reranker, NoopReranker)
        assert reranker.is_enabled is False

    def test_factory_creates_bge_when_enabled(self):
        """Factory must create BGEReranker when reranking enabled."""
        config = PipelineConfig(
            reranking=RerankingConfig(enabled=True, model="BAAI/bge-reranker-large")
        )
        factory = PipelineFactory(config)

        # Mock BGEReranker to avoid loading model (imported inside method)
        with patch('pipeline.rerankers.bge_reranker.BGEReranker') as mock_bge:
            mock_bge.return_value.is_enabled = True
            factory.create_reranker()
            mock_bge.assert_called_once_with(
                model_name="BAAI/bge-reranker-large",
                enable_timing=True
            )

    def test_factory_reranking_top_n_property(self):
        """Factory.reranking_top_n must return config value."""
        config = PipelineConfig(
            reranking=RerankingConfig(enabled=True, top_n=30)
        )
        factory = PipelineFactory(config)
        assert factory.reranking_top_n == 30

    def test_factory_reranking_enabled_property(self):
        """Factory.reranking_enabled must return config value."""
        config = PipelineConfig(
            reranking=RerankingConfig(enabled=True)
        )
        factory = PipelineFactory(config)
        assert factory.reranking_enabled is True

    def test_factory_reranking_disabled_property(self):
        """Factory.reranking_enabled must return False when disabled."""
        config = PipelineConfig(
            reranking=RerankingConfig(enabled=False)
        )
        factory = PipelineFactory(config)
        assert factory.reranking_enabled is False


class TestPipelineConfigLoading:
    """Test PipelineConfig loading from YAML and environment."""

    def test_config_from_yaml(self, tmp_path):
        """PipelineConfig.from_yaml must parse YAML correctly."""
        yaml_content = '''
reranking:
  enabled: true
  model: test/model
  top_n: 25
'''
        yaml_file = tmp_path / "test_pipeline.yaml"
        yaml_file.write_text(yaml_content)

        config = PipelineConfig.from_yaml(yaml_file)
        assert config.reranking.enabled is True
        assert config.reranking.model == "test/model"
        assert config.reranking.top_n == 25

    def test_config_from_yaml_with_defaults(self, tmp_path):
        """PipelineConfig.from_yaml must use defaults for missing fields."""
        yaml_content = '''
reranking:
  enabled: false
'''
        yaml_file = tmp_path / "test_pipeline.yaml"
        yaml_file.write_text(yaml_content)

        config = PipelineConfig.from_yaml(yaml_file)
        assert config.reranking.enabled is False
        assert config.reranking.model == "BAAI/bge-reranker-large"  # default
        assert config.reranking.top_n == 20  # default

    def test_config_env_reranking_enabled_true(self):
        """Environment variable RERANKING_ENABLED=true works."""
        with patch.dict(os.environ, {"RERANKING_ENABLED": "true"}):
            config = PipelineConfig.from_env()
            assert config.reranking.enabled is True

    def test_config_env_reranking_enabled_false(self):
        """Environment variable RERANKING_ENABLED=false works."""
        with patch.dict(os.environ, {"RERANKING_ENABLED": "false"}):
            config = PipelineConfig.from_env()
            assert config.reranking.enabled is False

    def test_config_env_reranking_model(self):
        """Environment variable RERANKING_MODEL overrides default."""
        with patch.dict(os.environ, {"RERANKING_MODEL": "custom/reranker"}):
            config = PipelineConfig.from_env()
            assert config.reranking.model == "custom/reranker"

    def test_config_env_reranking_top_n(self):
        """Environment variable RERANKING_TOP_N overrides default."""
        with patch.dict(os.environ, {"RERANKING_TOP_N": "50"}):
            config = PipelineConfig.from_env()
            assert config.reranking.top_n == 50

    def test_config_default_values(self):
        """PipelineConfig defaults must be sensible."""
        config = PipelineConfig()
        assert config.reranking.enabled is True  # enabled by default
        assert config.reranking.model == "BAAI/bge-reranker-large"
        assert config.reranking.top_n == 20


class TestPipelineConfigLoad:
    """Test PipelineConfig.load() method (YAML vs env fallback)."""

    def test_load_from_yaml_when_exists(self, tmp_path):
        """load() should use YAML file when it exists."""
        yaml_content = '''
reranking:
  enabled: false
  model: yaml-model
'''
        yaml_file = tmp_path / "pipeline.yaml"
        yaml_file.write_text(yaml_content)

        config = PipelineConfig.load(config_path=yaml_file)
        assert config.reranking.enabled is False
        assert config.reranking.model == "yaml-model"

    def test_load_falls_back_to_env(self, tmp_path):
        """load() should fall back to env when YAML doesn't exist."""
        # Create a non-existent path
        missing_yaml = tmp_path / "missing.yaml"

        with patch.dict(os.environ, {"RERANKING_ENABLED": "false"}):
            # Patch default paths to not find any YAML
            with patch.object(Path, 'exists', return_value=False):
                config = PipelineConfig.from_env()
                assert config.reranking.enabled is False


class TestRerankingConfigDefaults:
    """Test RerankingConfig dataclass defaults."""

    def test_default_enabled(self):
        """RerankingConfig.enabled defaults to True."""
        config = RerankingConfig()
        assert config.enabled is True

    def test_default_model(self):
        """RerankingConfig.model defaults to bge-reranker-large."""
        config = RerankingConfig()
        assert config.model == "BAAI/bge-reranker-large"

    def test_default_top_n(self):
        """RerankingConfig.top_n defaults to 20."""
        config = RerankingConfig()
        assert config.top_n == 20


class TestPipelineFactoryExtractor:
    """Test PipelineFactory extractor creation."""

    def test_create_extractor_for_pdf(self):
        """Factory must create extractor for .pdf files."""
        factory = PipelineFactory.default()
        extractor = factory.create_extractor('.pdf')

        assert isinstance(extractor, ExtractorInterface)
        assert 'docling' in extractor.name

    def test_create_extractor_for_python(self):
        """Factory must create extractor for .py files."""
        factory = PipelineFactory.default()
        extractor = factory.create_extractor('.py')

        assert isinstance(extractor, ExtractorInterface)
        assert extractor.name == 'code_ast'

    def test_create_extractor_for_markdown(self):
        """Factory must create extractor for .md files."""
        factory = PipelineFactory.default()
        extractor = factory.create_extractor('.md')

        assert isinstance(extractor, ExtractorInterface)

    def test_create_extractor_for_jupyter(self):
        """Factory must create extractor for .ipynb files."""
        factory = PipelineFactory.default()
        extractor = factory.create_extractor('.ipynb')

        assert isinstance(extractor, ExtractorInterface)
        assert 'jupyter' in extractor.name

    def test_create_extractor_for_epub(self):
        """Factory must create extractor for .epub files."""
        factory = PipelineFactory.default()
        extractor = factory.create_extractor('.epub')

        assert isinstance(extractor, ExtractorInterface)

    def test_create_extractor_unsupported_raises(self):
        """Factory must raise ValueError for unsupported extensions."""
        factory = PipelineFactory.default()

        with pytest.raises(ValueError, match="Unsupported extension"):
            factory.create_extractor('.xyz')

    def test_create_extractor_without_dot(self):
        """Factory must handle extensions without leading dot."""
        factory = PipelineFactory.default()
        extractor = factory.create_extractor('pdf')

        assert isinstance(extractor, ExtractorInterface)

    def test_get_extractor_for_file(self):
        """Factory.get_extractor_for_file must work with Path objects."""
        factory = PipelineFactory.default()
        extractor = factory.get_extractor_for_file(Path('/test/file.py'))

        assert isinstance(extractor, ExtractorInterface)
        assert extractor.name == 'code_ast'

    def test_supports_extension_true(self):
        """Factory.supports_extension returns True for supported extensions."""
        factory = PipelineFactory.default()

        assert factory.supports_extension('.pdf') is True
        assert factory.supports_extension('.py') is True
        assert factory.supports_extension('md') is True  # without dot

    def test_supports_extension_false(self):
        """Factory.supports_extension returns False for unsupported extensions."""
        factory = PipelineFactory.default()

        assert factory.supports_extension('.xyz') is False
        assert factory.supports_extension('.exe') is False

    def test_get_supported_extensions(self):
        """Factory.get_supported_extensions returns all supported extensions."""
        factory = PipelineFactory.default()
        extensions = factory.get_supported_extensions()

        assert isinstance(extensions, list)
        assert '.pdf' in extensions
        assert '.py' in extensions
        assert '.md' in extensions
        assert '.ipynb' in extensions
        # Should be sorted
        assert extensions == sorted(extensions)


class TestPipelineFactoryChunker:
    """Test PipelineFactory chunker creation."""

    def test_create_chunker_hybrid_default(self):
        """Factory must create HybridChunker by default."""
        config = PipelineConfig(
            chunking=ChunkingConfig(strategy='hybrid', max_tokens=512)
        )
        factory = PipelineFactory(config)
        chunker = factory.create_chunker()

        assert isinstance(chunker, ChunkerInterface)
        assert chunker.name == 'hybrid'

    def test_create_chunker_semantic(self):
        """Factory must create SemanticChunker when configured."""
        config = PipelineConfig(
            chunking=ChunkingConfig(strategy='semantic', max_tokens=256)
        )
        factory = PipelineFactory(config)
        chunker = factory.create_chunker()

        assert isinstance(chunker, ChunkerInterface)
        assert chunker.name == 'semantic'

    def test_create_chunker_fixed(self):
        """Factory must create FixedChunker when configured."""
        config = PipelineConfig(
            chunking=ChunkingConfig(strategy='fixed', max_tokens=1024)
        )
        factory = PipelineFactory(config)
        chunker = factory.create_chunker()

        assert isinstance(chunker, ChunkerInterface)
        assert chunker.name == 'fixed'

    def test_create_chunker_unknown_falls_back_to_hybrid(self):
        """Factory must fall back to HybridChunker for unknown strategy."""
        config = PipelineConfig(
            chunking=ChunkingConfig(strategy='unknown_strategy', max_tokens=512)
        )
        factory = PipelineFactory(config)
        chunker = factory.create_chunker()

        assert isinstance(chunker, ChunkerInterface)
        assert chunker.name == 'hybrid'

    def test_chunker_respects_max_tokens(self):
        """Chunker must respect max_tokens from config."""
        config = PipelineConfig(
            chunking=ChunkingConfig(strategy='fixed', max_tokens=256)
        )
        factory = PipelineFactory(config)
        chunker = factory.create_chunker()

        assert chunker.max_tokens == 256


class TestPipelineFactoryFromYaml:
    """Test PipelineFactory.from_yaml() class method."""

    def test_from_yaml_creates_factory(self, tmp_path):
        """from_yaml must create a functional PipelineFactory."""
        yaml_content = '''
extraction:
  provider: docling
chunking:
  strategy: semantic
  max_tokens: 256
reranking:
  enabled: false
'''
        yaml_file = tmp_path / "pipeline.yaml"
        yaml_file.write_text(yaml_content)

        factory = PipelineFactory.from_yaml(yaml_file)

        assert isinstance(factory, PipelineFactory)
        assert factory.config.chunking.strategy == 'semantic'
        assert factory.config.chunking.max_tokens == 256
        assert factory.reranking_enabled is False

    def test_default_creates_factory(self):
        """default() must create a functional PipelineFactory."""
        factory = PipelineFactory.default()

        assert isinstance(factory, PipelineFactory)
        # Should have default config values
        assert factory.config.chunking.strategy == 'hybrid'
