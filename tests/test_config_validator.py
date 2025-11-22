"""
Tests for configuration validator
"""
import os
import pytest
from pathlib import Path
from tempfile import TemporaryDirectory
from dataclasses import dataclass

from startup.config_validator import ConfigValidator, ConfigValidationError


@dataclass
class MockPathConfig:
    """Mock path configuration"""
    knowledge_base: Path
    data_dir: Path


@dataclass
class MockConfig:
    """Mock configuration"""
    paths: MockPathConfig


def test_valid_config_passes():
    """Test that valid configuration passes validation"""
    with TemporaryDirectory() as tmpdir:
        kb_path = Path(tmpdir) / "knowledge_base"
        data_dir = Path(tmpdir) / "data"
        kb_path.mkdir()
        data_dir.mkdir()

        config = MockConfig(
            paths=MockPathConfig(
                knowledge_base=kb_path,
                data_dir=data_dir
            )
        )

        validator = ConfigValidator(config)
        # Should not raise
        validator.validate()


def test_missing_kb_directory_fails():
    """Test that missing knowledge base directory fails validation"""
    with TemporaryDirectory() as tmpdir:
        kb_path = Path(tmpdir) / "nonexistent"
        data_dir = Path(tmpdir) / "data"
        data_dir.mkdir()

        config = MockConfig(
            paths=MockPathConfig(
                knowledge_base=kb_path,
                data_dir=data_dir
            )
        )

        validator = ConfigValidator(config)
        with pytest.raises(ConfigValidationError) as exc_info:
            validator.validate()

        assert "does not exist" in str(exc_info.value)
        assert str(kb_path) in str(exc_info.value)


def test_kb_path_is_file_fails():
    """Test that knowledge base path pointing to a file fails validation"""
    with TemporaryDirectory() as tmpdir:
        kb_path = Path(tmpdir) / "file.txt"
        kb_path.touch()  # Create file, not directory
        data_dir = Path(tmpdir) / "data"
        data_dir.mkdir()

        config = MockConfig(
            paths=MockPathConfig(
                knowledge_base=kb_path,
                data_dir=data_dir
            )
        )

        validator = ConfigValidator(config)
        with pytest.raises(ConfigValidationError) as exc_info:
            validator.validate()

        assert "not a directory" in str(exc_info.value)


def test_unreadable_kb_directory_fails():
    """Test that unreadable knowledge base directory fails validation"""
    with TemporaryDirectory() as tmpdir:
        kb_path = Path(tmpdir) / "knowledge_base"
        kb_path.mkdir()
        data_dir = Path(tmpdir) / "data"
        data_dir.mkdir()

        # Remove read permission
        os.chmod(kb_path, 0o000)

        config = MockConfig(
            paths=MockPathConfig(
                knowledge_base=kb_path,
                data_dir=data_dir
            )
        )

        try:
            validator = ConfigValidator(config)
            with pytest.raises(ConfigValidationError) as exc_info:
                validator.validate()

            assert "not readable" in str(exc_info.value)
        finally:
            # Restore permissions for cleanup
            os.chmod(kb_path, 0o755)


def test_data_dir_created_if_missing():
    """Test that data directory is created if it doesn't exist"""
    with TemporaryDirectory() as tmpdir:
        kb_path = Path(tmpdir) / "knowledge_base"
        kb_path.mkdir()
        data_dir = Path(tmpdir) / "data"
        # Don't create data_dir

        config = MockConfig(
            paths=MockPathConfig(
                knowledge_base=kb_path,
                data_dir=data_dir
            )
        )

        validator = ConfigValidator(config)
        # Should create data_dir and not raise
        validator.validate()

        assert data_dir.exists()
        assert data_dir.is_dir()


def test_unwritable_data_dir_fails():
    """Test that unwritable data directory fails validation"""
    with TemporaryDirectory() as tmpdir:
        kb_path = Path(tmpdir) / "knowledge_base"
        kb_path.mkdir()
        data_dir = Path(tmpdir) / "data"
        data_dir.mkdir()

        # Remove write permission
        os.chmod(data_dir, 0o444)

        config = MockConfig(
            paths=MockPathConfig(
                knowledge_base=kb_path,
                data_dir=data_dir
            )
        )

        try:
            validator = ConfigValidator(config)
            with pytest.raises(ConfigValidationError) as exc_info:
                validator.validate()

            assert "not writable" in str(exc_info.value)
        finally:
            # Restore permissions for cleanup
            os.chmod(data_dir, 0o755)
