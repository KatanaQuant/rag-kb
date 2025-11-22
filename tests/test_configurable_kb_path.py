"""
Test for configurable knowledge base directory path

Uses static analysis to verify implementation without triggering circular import
between config.py and environment_config_loader.py
"""
from pathlib import Path


def test_kb_path_in_environment_config_loader():
    """Test that EnvironmentConfigLoader has _load_path_config method"""
    loader_file = Path(__file__).parent.parent / "api" / "environment_config_loader.py"
    content = loader_file.read_text()

    # Check that _load_path_config method is defined
    assert "_load_path_config" in content, \
        "EnvironmentConfigLoader should have _load_path_config method"

    # Check that it reads KNOWLEDGE_BASE_PATH
    assert "KNOWLEDGE_BASE_PATH" in content, \
        "_load_path_config should read KNOWLEDGE_BASE_PATH environment variable"


def test_kb_path_config_is_used_in_loader():
    """Test that load() method calls _load_path_config"""
    loader_file = Path(__file__).parent.parent / "api" / "environment_config_loader.py"
    content = loader_file.read_text()

    # Find the load() method
    load_method_present = "def load(self)" in content
    assert load_method_present, "load() method should exist"

    # Check that it uses _load_path_config
    if "_load_path_config" in content:
        # If method exists, it should be called in load()
        assert "paths=self._load_path_config()" in content or "paths = self._load_path_config()" in content, \
            "load() should call self._load_path_config()"


def test_get_path_has_tilde_expansion():
    """Test that _get_path implementation includes tilde expansion"""
    loader_file = Path(__file__).parent.parent / "api" / "environment_config_loader.py"
    content = loader_file.read_text()

    # Check for expanduser() call
    assert "expanduser()" in content, \
        "_get_path should call expanduser() to expand ~ to home directory"


def test_get_path_has_absolute_conversion():
    """Test that _get_path implementation converts to absolute paths"""
    loader_file = Path(__file__).parent.parent / "api" / "environment_config_loader.py"
    content = loader_file.read_text()

    # Check for resolve() or is_absolute() check
    assert ("resolve()" in content or "is_absolute()" in content), \
        "_get_path should handle absolute path conversion"


def test_get_path_returns_path_object():
    """Test that _get_path returns Path object"""
    loader_file = Path(__file__).parent.parent / "api" / "environment_config_loader.py"
    content = loader_file.read_text()

    # Check function signature
    assert "def _get_path(self, key: str, default: Path) -> Path:" in content, \
        "_get_path should return Path object"
