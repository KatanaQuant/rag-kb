"""
Test API version matches release version
"""
import re
from pathlib import Path


def test_api_version_in_main_py():
    """Test that API version in main.py matches the current release"""
    expected_version = "0.11.0"

    # Read main.py file
    main_py_path = Path(__file__).parent.parent / "api" / "main.py"
    content = main_py_path.read_text()

    # Extract version from FastAPI app initialization
    version_pattern = r'app\s*=\s*FastAPI\s*\([^)]*version\s*=\s*["\']([^"\']+)["\']'
    match = re.search(version_pattern, content, re.DOTALL)

    assert match is not None, "Could not find version in main.py FastAPI initialization"

    actual_version = match.group(1)
    assert actual_version == expected_version, \
        f"API version mismatch: expected {expected_version}, got {actual_version}"
