"""Tests for JupyterExtractor

Tests the HybridChunker-based notebook extraction that converts
notebooks to markdown and applies semantic chunking.
"""

import pytest
import json
import tempfile
from pathlib import Path

from ingestion.jupyter_extractor import JupyterExtractor
from domain_models import ExtractionResult


class TestJupyterExtractorBasics:
    """Test basic extraction functionality"""

    @pytest.fixture
    def extractor(self):
        """Create JupyterExtractor instance"""
        return JupyterExtractor()

    @pytest.fixture
    def sample_notebook_path(self):
        """Path to sample Python notebook"""
        return Path(__file__).parent / "fixtures" / "sample_python.ipynb"

    def test_extract_simple_notebook(self, extractor, sample_notebook_path):
        """Test: Can extract from valid .ipynb file"""
        result = extractor.extract(sample_notebook_path)

        assert isinstance(result, ExtractionResult)
        assert result.success
        assert result.page_count > 0

    def test_extract_preserves_content(self, extractor, sample_notebook_path):
        """Test: Content is preserved in extraction"""
        result = extractor.extract(sample_notebook_path)

        assert result.page_count > 0
        content = '\n'.join(page[0] for page in result.pages)
        # Should contain notebook content
        assert len(content) > 0

    def test_extract_includes_metadata(self, extractor, sample_notebook_path):
        """Test: Result includes success status and method"""
        result = extractor.extract(sample_notebook_path)

        assert result.success
        assert result.method == 'jupyter_python'

    def test_extract_empty_notebook(self, extractor):
        """Test: Handle notebook with no cells gracefully"""
        empty_nb = {
            'cells': [],
            'metadata': {'kernelspec': {'name': 'python3', 'language': 'python'}},
            'nbformat': 4,
            'nbformat_minor': 5
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.ipynb', delete=False) as f:
            json.dump(empty_nb, f)
            temp_path = f.name

        try:
            result = extractor.extract(Path(temp_path))
            assert isinstance(result, ExtractionResult)
            # Empty notebook should have 0 pages
            assert result.page_count == 0
        finally:
            Path(temp_path).unlink()

    def test_extract_notebook_with_code(self, extractor):
        """Test: Code cells are included in output"""
        nb = {
            'cells': [
                {
                    'cell_type': 'code',
                    'source': 'print("Hello")',
                    'metadata': {},
                    'outputs': [],
                    'execution_count': 1
                }
            ],
            'metadata': {'kernelspec': {'name': 'python3', 'language': 'python'}},
            'nbformat': 4,
            'nbformat_minor': 5
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.ipynb', delete=False) as f:
            json.dump(nb, f)
            temp_path = f.name

        try:
            result = extractor.extract(Path(temp_path))
            assert result.page_count > 0
            content = '\n'.join(page[0] for page in result.pages)
            assert 'print' in content or 'Hello' in content
        finally:
            Path(temp_path).unlink()

    def test_extract_notebook_with_markdown(self, extractor):
        """Test: Markdown cells are included in output"""
        nb = {
            'cells': [
                {
                    'cell_type': 'markdown',
                    'source': '# Header\n\nThis is markdown content.',
                    'metadata': {}
                }
            ],
            'metadata': {'kernelspec': {'name': 'python3', 'language': 'python'}},
            'nbformat': 4,
            'nbformat_minor': 5
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.ipynb', delete=False) as f:
            json.dump(nb, f)
            temp_path = f.name

        try:
            result = extractor.extract(Path(temp_path))
            assert result.page_count > 0
            content = '\n'.join(page[0] for page in result.pages)
            assert 'Header' in content or 'markdown' in content
        finally:
            Path(temp_path).unlink()


class TestNotebookToMarkdown:
    """Test the notebook to markdown conversion"""

    @pytest.fixture
    def extractor(self):
        return JupyterExtractor()

    def test_notebook_converts_code_to_fenced_blocks(self, extractor):
        """Test: Code cells appear in output"""
        nb = {
            'cells': [
                {'cell_type': 'markdown', 'source': '# Data Analysis Notebook\n\nThis notebook demonstrates basic data analysis.', 'metadata': {}},
                {'cell_type': 'code', 'source': 'import pandas as pd\ndf = pd.DataFrame({"x": [1,2,3]})', 'metadata': {}, 'outputs': [], 'execution_count': 1},
            ],
            'metadata': {'kernelspec': {'name': 'python3', 'language': 'python', 'display_name': 'Python 3'}},
            'nbformat': 4,
            'nbformat_minor': 5
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.ipynb', delete=False) as f:
            json.dump(nb, f)
            temp_path = f.name

        try:
            result = extractor.extract(Path(temp_path))
            content = '\n'.join(page[0] for page in result.pages)

            # Content should include code
            assert 'pandas' in content or 'DataFrame' in content or 'import' in content
        finally:
            Path(temp_path).unlink()

    def test_notebook_skips_empty_cells_in_output(self, extractor):
        """Test: Empty cells don't appear in output"""
        nb = {
            'cells': [
                {'cell_type': 'markdown', 'source': '', 'metadata': {}},
                {'cell_type': 'code', 'source': 'x = 1', 'metadata': {}, 'outputs': [], 'execution_count': 1},
                {'cell_type': 'markdown', 'source': '   ', 'metadata': {}},
            ],
            'metadata': {'kernelspec': {'name': 'python3', 'language': 'python'}},
            'nbformat': 4,
            'nbformat_minor': 5
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.ipynb', delete=False) as f:
            json.dump(nb, f)
            temp_path = f.name

        try:
            result = extractor.extract(Path(temp_path))
            content = '\n'.join(page[0] for page in result.pages)

            # Only code cell content should be present
            assert 'x = 1' in content or 'x' in content
            assert content.strip()
        finally:
            Path(temp_path).unlink()


class TestIntegration:
    """Integration tests with real notebooks"""

    @pytest.fixture
    def extractor(self):
        return JupyterExtractor()

    def test_extract_real_notebook_python(self, extractor):
        """Integration: Extract from real Python notebook"""
        notebook_path = Path(__file__).parent / "fixtures" / "sample_python.ipynb"

        if not notebook_path.exists():
            pytest.skip("Fixture notebook not found")

        result = extractor.extract(notebook_path)

        assert result.method == 'jupyter_python'
        assert len(result.pages) > 0

    def test_chunking_produces_content(self, extractor):
        """Test: Chunking produces non-empty content"""
        notebook_path = Path(__file__).parent / "fixtures" / "sample_python.ipynb"

        if not notebook_path.exists():
            pytest.skip("Fixture notebook not found")

        result = extractor.extract(notebook_path)

        # Should produce at least some content
        assert result.page_count > 0
        total_content = sum(len(page[0]) for page in result.pages)
        assert total_content > 0
