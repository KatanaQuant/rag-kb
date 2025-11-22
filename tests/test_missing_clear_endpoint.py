"""
Test for missing /indexing/clear endpoint mentioned in v0.11.0-alpha release notes
"""
from pathlib import Path


def test_indexing_clear_endpoint_exists():
    """Test that /indexing/clear endpoint exists in main.py"""
    main_path = Path(__file__).parent.parent / "api" / "main.py"
    content = main_path.read_text()

    # According to v0.11.0-alpha release notes:
    # POST /indexing/clear - Clear pending queue
    assert '/indexing/clear' in content or 'indexing/clear' in content, \
        "/indexing/clear endpoint missing (mentioned in v0.11.0-alpha release notes)"


def test_clear_endpoint_has_post_decorator():
    """Test that clear endpoint uses POST method"""
    main_path = Path(__file__).parent.parent / "api" / "main.py"
    content = main_path.read_text()

    # Find the clear endpoint section if it exists
    if 'indexing/clear' in content:
        # Check if it has @app.post decorator
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if 'indexing/clear' in line and '@app.post' in line:
                # Found the decorator line
                return
        assert False, "/indexing/clear endpoint found but doesn't use @app.post decorator"
