"""Test package for rag-kb

Shared test utilities and markers.
"""
import os
import pytest


def _huggingface_cache_accessible():
    """Check if HuggingFace cache directory is accessible."""
    cache_dir = os.path.expanduser("~/.cache/huggingface/hub")
    try:
        os.makedirs(cache_dir, exist_ok=True)
        test_file = os.path.join(cache_dir, ".write_test")
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
        return True
    except (PermissionError, OSError):
        return False


requires_huggingface = pytest.mark.skipif(
    not _huggingface_cache_accessible(),
    reason="HuggingFace cache not accessible"
)
