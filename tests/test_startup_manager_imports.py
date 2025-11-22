"""
Test that StartupManager can be imported successfully
"""
import pytest


def test_startup_manager_imports():
    """Test that StartupManager imports without NameError"""
    try:
        from startup.manager import StartupManager
        # If we get here, imports worked
        assert StartupManager is not None
    except NameError as e:
        pytest.fail(f"Import failed with NameError: {e}")


def test_startup_manager_can_detect_orphans():
    """Test that StartupManager can use OrphanDetector"""
    from startup.manager import StartupManager
    from unittest.mock import Mock

    # Create mock state
    mock_state = Mock()
    mock_state.core.progress_tracker = Mock()
    mock_state.core.vector_store = Mock()

    manager = StartupManager(mock_state)

    # This should not raise NameError for OrphanDetector
    try:
        # Just check that the method exists and doesn't fail on import
        assert hasattr(manager, '_detect_orphans')
        assert callable(manager._detect_orphans)
    except NameError as e:
        pytest.fail(f"NameError when accessing orphan detection: {e}")
