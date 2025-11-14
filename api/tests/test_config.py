"""
Unit tests for config module
"""
import pytest
from config import (
    ChunkConfig,
    DatabaseConfig,
    ModelConfig,
    PathConfig,
    Config
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

        # Database config
        assert config.database.embedding_dim == 384

        # Model config
        assert "sentence-transformers" in config.model.name

        # Path config
        assert "knowledge_base" in str(config.paths.knowledge_base)
