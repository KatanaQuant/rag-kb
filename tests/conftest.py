"""
Pytest configuration and shared fixtures
"""
import pytest
import sys
from pathlib import Path

# Add api directory to path for imports
api_path = Path(__file__).parent.parent / "api"
sys.path.insert(0, str(api_path))
