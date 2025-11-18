"""Tests for CodeExtractor - AST-based chunking

TDD approach: Write tests first, then implement
"""
import pytest
from pathlib import Path
import tempfile
from ingestion.extractors import CodeExtractor


class TestCodeExtractor:
    """Test AST-based code extraction"""

    def test_extracts_python_code_with_ast_chunking(self, tmp_path):
        """Should extract and chunk Python code using AST"""
        # Create a Python file
        python_file = tmp_path / "test.py"
        python_file.write_text("""
def hello():
    print("Hello, World!")

def goodbye():
    print("Goodbye!")

class MyClass:
    def method(self):
        pass
""")

        # Extract with AST chunking
        result = CodeExtractor.extract(python_file)

        assert result.success is True
        assert result.method == 'ast_python'
        assert len(result.pages) > 0
        # Should have actual code chunks, not empty
        assert all(len(text.strip()) > 0 for text, _ in result.pages)

    def test_fails_on_unsupported_extension(self, tmp_path):
        """Should raise ValueError for unsupported file types"""
        unsupported_file = tmp_path / "test.xyz"
        unsupported_file.write_text("some content")

        with pytest.raises(ValueError, match="Unsupported file extension"):
            CodeExtractor.extract(unsupported_file)

    def test_caches_chunker_by_language(self, tmp_path):
        """Should reuse chunker instance for same language"""
        # Create two Python files
        file1 = tmp_path / "file1.py"
        file1.write_text("def foo(): pass")
        file2 = tmp_path / "file2.py"
        file2.write_text("def bar(): pass")

        # Extract both
        CodeExtractor.extract(file1)
        CodeExtractor.extract(file2)

        # Should have cached the python chunker
        assert 'python' in CodeExtractor._chunker_cache
