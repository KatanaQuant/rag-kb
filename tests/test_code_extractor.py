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

    def test_extracts_go_code_with_ast_chunking(self, tmp_path):
        """Should extract and chunk Go code using AST (TDD: FAILING TEST)"""
        # Create a Go file with multiple functions
        go_file = tmp_path / "test.go"
        go_file.write_text("""package main

import "fmt"

func main() {
    fmt.Println("Hello, World!")
}

func add(a int, b int) int {
    return a + b
}

func subtract(a int, b int) int {
    return a - b
}

type Calculator struct {
    value int
}

func (c *Calculator) Add(n int) {
    c.value += n
}
""")

        # Extract with AST chunking
        result = CodeExtractor.extract(go_file)

        assert result.success is True
        assert result.method == 'ast_go'
        assert len(result.pages) > 0
        # Should have actual code chunks, not empty
        assert all(len(text.strip()) > 0 for text, _ in result.pages)
        # Should respect function boundaries (multiple chunks for multiple functions)
        assert len(result.pages) >= 3  # main, add, subtract at minimum

    def test_extracts_javascript_code_with_ast_chunking(self, tmp_path):
        """Should extract and chunk JavaScript code using AST

        Issue #4: JavaScript extraction fails because astchunk doesn't support JS.
        Solution: Use TreeSitterChunker (like Go) for JavaScript.
        """
        # Create a JavaScript file with typical code
        js_file = tmp_path / "test.js"
        js_file.write_text("""
var navLinks = document.querySelectorAll("nav a");
for (var i = 0; i < navLinks.length; i++) {
    var link = navLinks[i]
    if (link.getAttribute('href') == window.location.pathname) {
        link.classList.add("live");
        break;
    }
}

function greet(name) {
    return "Hello, " + name + "!";
}

const add = (a, b) => a + b;
""")

        # Extract with AST chunking
        result = CodeExtractor.extract(js_file)

        assert result.success is True
        assert result.method == 'ast_javascript'
        assert len(result.pages) > 0
        # Should have actual code chunks, not empty
        assert all(len(text.strip()) > 0 for text, _ in result.pages)

    def test_extracts_tsx_code_with_ast_chunking(self, tmp_path):
        """Should extract and chunk TSX code using AST

        TSX also not supported by astchunk, needs TreeSitterChunker.
        """
        tsx_file = tmp_path / "Component.tsx"
        tsx_file.write_text("""
import React from 'react';

interface Props {
    name: string;
}

const Greeting: React.FC<Props> = ({ name }) => {
    return <div>Hello, {name}!</div>;
};

export default Greeting;
""")

        result = CodeExtractor.extract(tsx_file)

        assert result.success is True
        assert result.method == 'ast_tsx'
        assert len(result.pages) > 0
        assert all(len(text.strip()) > 0 for text, _ in result.pages)
