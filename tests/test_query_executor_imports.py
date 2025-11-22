"""
Test that QueryExecutor can be imported successfully
"""
import pytest


def test_query_executor_imports():
    """Test that QueryExecutor imports without NameError"""
    try:
        from api_services.query_executor import QueryExecutor
        # If we get here, imports worked
        assert QueryExecutor is not None
    except NameError as e:
        pytest.fail(f"Import failed with NameError: {e}")
