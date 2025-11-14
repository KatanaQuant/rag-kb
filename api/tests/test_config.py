"""
Unit tests for config module
"""
import pytest
import os
from config import (
    ChunkConfig,
    DatabaseConfig,
    ModelConfig,
    PathConfig,
    Config,
    MODEL_DIMENSIONS
)


class TestChunkConfig:
    """Tests for ChunkConfig"""

    def test_default_values(self):
        """Test default configuration values"""
        config = ChunkConfig()
        assert config.size == 1000
        assert config.overlap == 200
        assert config.min_size == 50

    def test_custom_values(self):
        """Test custom configuration"""
        config = ChunkConfig(size=500, overlap=100, min_size=25)
        assert config.size == 500
        assert config.overlap == 100
        assert config.min_size == 25


class TestDatabaseConfig:
    """Tests for DatabaseConfig"""

    def test_default_values(self):
        """Test default values"""
        config = DatabaseConfig()
        assert config.path == "/app/data/rag.db"
        assert config.embedding_dim == 384
        assert config.check_same_thread is False

    def test_custom_path(self):
        """Test custom database path"""
        config = DatabaseConfig(path="/custom/path.db")
        assert config.path == "/custom/path.db"


class TestModelConfig:
    """Tests for ModelConfig"""

    def test_default_model(self):
        """Test default model name"""
        config = ModelConfig()
        assert config.name == "sentence-transformers/all-MiniLM-L6-v2"
        assert config.show_progress is False

    def test_custom_model(self):
        """Test custom model"""
        config = ModelConfig(name="custom-model", show_progress=True)
        assert config.name == "custom-model"
        assert config.show_progress is True

    def test_get_embedding_dim_default(self):
        """Test getting embedding dimension for default model"""
        config = ModelConfig()
        assert config.get_embedding_dim() == 384

    def test_get_embedding_dim_arctic_large(self):
        """Test Arctic Embed L dimensions"""
        config = ModelConfig(name="Snowflake/snowflake-arctic-embed-l-v2.0")
        assert config.get_embedding_dim() == 1024

    def test_get_embedding_dim_arctic_medium(self):
        """Test Arctic Embed M dimensions"""
        config = ModelConfig(name="Snowflake/snowflake-arctic-embed-m-v2.0")
        assert config.get_embedding_dim() == 768

    def test_get_embedding_dim_bge_large(self):
        """Test BGE large dimensions"""
        config = ModelConfig(name="BAAI/bge-large-en-v1.5")
        assert config.get_embedding_dim() == 1024

    def test_get_embedding_dim_unknown_model(self):
        """Test unknown model defaults to 384"""
        config = ModelConfig(name="unknown/model")
        assert config.get_embedding_dim() == 384


class TestPathConfig:
    """Tests for PathConfig"""

    def test_default_paths(self):
        """Test default paths"""
        config = PathConfig()
        assert str(config.knowledge_base) == "/app/knowledge_base"
        assert str(config.data_dir) == "/app/data"


class TestConfig:
    """Tests for main Config class"""

    def test_from_env(self):
        """Test config creation from environment"""
        config = Config.from_env()
        assert isinstance(config.chunks, ChunkConfig)
        assert isinstance(config.database, DatabaseConfig)
        assert isinstance(config.model, ModelConfig)
        assert isinstance(config.paths, PathConfig)

    def test_config_structure(self):
        """Test complete config structure"""
        config = Config.from_env()

        # Chunk config
        assert config.chunks.size == 1000
        assert config.chunks.overlap == 200

        # Database config (embedding_dim depends on model)
        assert config.database.embedding_dim in [384, 768, 1024]

        # Model config
        assert config.model.name is not None

        # Path config
        assert "knowledge_base" in str(config.paths.knowledge_base)

        # Watcher config
        assert config.watcher is not None
        assert isinstance(config.watcher.enabled, bool)
        assert config.watcher.debounce_seconds > 0

    def test_config_dynamic_dimensions(self):
        """Test config with Arctic Embed model sets correct dimensions"""
        # Set environment variable
        os.environ["MODEL_NAME"] = "Snowflake/snowflake-arctic-embed-l-v2.0"

        # Create config from env
        config = Config.from_env()

        # Verify dimensions match model
        assert config.model.name == "Snowflake/snowflake-arctic-embed-l-v2.0"
        assert config.database.embedding_dim == 1024
        assert config.model.get_embedding_dim() == 1024

        # Clean up
        del os.environ["MODEL_NAME"]

    def test_model_dimensions_mapping(self):
        """Test MODEL_DIMENSIONS mapping is complete"""
        assert "sentence-transformers/all-MiniLM-L6-v2" in MODEL_DIMENSIONS
        assert "Snowflake/snowflake-arctic-embed-l-v2.0" in MODEL_DIMENSIONS
        assert "Snowflake/snowflake-arctic-embed-m-v2.0" in MODEL_DIMENSIONS
        assert MODEL_DIMENSIONS["Snowflake/snowflake-arctic-embed-l-v2.0"] == 1024
        assert MODEL_DIMENSIONS["Snowflake/snowflake-arctic-embed-m-v2.0"] == 768
