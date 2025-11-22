"""
Test that startup/manager.py has required imports
"""
from pathlib import Path
import re


def test_orphan_detector_imported():
    """Test that OrphanDetector is imported in startup/manager.py"""
    manager_path = Path(__file__).parent.parent / "api" / "startup" / "manager.py"
    content = manager_path.read_text()

    # Check if OrphanDetector is used in the file
    if "OrphanDetector" in content:
        # If it's used, it must be imported
        import_pattern = r'from\s+api_services\.orphan_detector\s+import\s+OrphanDetector'
        assert re.search(import_pattern, content), \
            "OrphanDetector is used but not imported from api_services.orphan_detector"
