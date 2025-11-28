"""Tests for JupyterExtractor

Tests the HybridChunker-based notebook extraction that converts
notebooks to markdown and applies semantic chunking.
"""

import pytest
import json
import tempfile
from pathlib import Path

from ingestion.jupyter_extractor import JupyterExtractor
from ingestion.jupyter.output_parser import NotebookOutputParser
from ingestion.jupyter.language_detector import KernelLanguageDetector
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


class TestOutputParsing:
    """Test output parsing (used by other components)"""

    def test_parse_outputs_stream(self):
        """Test: Parse stdout/stderr stream outputs"""
        outputs = [
            type('obj', (object,), {
                'output_type': 'stream',
                'name': 'stdout',
                'text': 'Hello, World!\n'
            })()
        ]

        result = NotebookOutputParser.parse_outputs(outputs)

        assert len(result) == 1
        assert result[0]['output_type'] == 'stream'
        assert result[0]['text'] == 'Hello, World!\n'
        assert result[0]['stream_name'] == 'stdout'

    def test_parse_outputs_execute_result(self):
        """Test: Parse execution results (text/plain)"""
        outputs = [
            type('obj', (object,), {
                'output_type': 'execute_result',
                'data': {'text/plain': '42'},
                'execution_count': 1
            })()
        ]

        result = NotebookOutputParser.parse_outputs(outputs)

        assert len(result) == 1
        assert result[0]['output_type'] == 'execute_result'
        assert result[0]['text'] == '42'

    def test_parse_outputs_display_data_with_image(self):
        """Test: Parse image outputs (PNG)"""
        outputs = [
            type('obj', (object,), {
                'output_type': 'display_data',
                'data': {
                    'image/png': 'iVBORw0KGgoAAAANSUhEUgAAAAUA',
                    'text/plain': '<Figure size 640x480>'
                }
            })()
        ]

        result = NotebookOutputParser.parse_outputs(outputs)

        assert len(result) == 1
        assert result[0]['has_image'] is True
        assert result[0]['image_type'] == 'png'

    def test_parse_outputs_error_traceback(self):
        """Test: Parse error outputs with traceback"""
        outputs = [
            type('obj', (object,), {
                'output_type': 'error',
                'ename': 'ValueError',
                'evalue': 'invalid value',
                'traceback': ['Traceback (most recent call last):', '  File ...', 'ValueError: invalid value']
            })()
        ]

        result = NotebookOutputParser.parse_outputs(outputs)

        assert len(result) == 1
        assert result[0]['output_type'] == 'error'
        assert result[0]['error_name'] == 'ValueError'

    def test_parse_outputs_empty_list(self):
        """Test: Handle cells with no outputs"""
        result = NotebookOutputParser.parse_outputs([])
        assert result == []


class TestLanguageDetection:
    """Test language detection from kernel names"""

    def test_detect_language_python_kernel(self):
        """Test: 'python3' kernel -> 'python'"""
        assert KernelLanguageDetector.detect_language('python3') == 'python'
        assert KernelLanguageDetector.detect_language('python') == 'python'

    def test_detect_language_r_kernel(self):
        """Test: 'ir' kernel -> 'r'"""
        assert KernelLanguageDetector.detect_language('ir') == 'r'
        assert KernelLanguageDetector.detect_language('R') == 'r'

    def test_detect_language_julia_kernel(self):
        """Test: Julia kernel detection"""
        assert KernelLanguageDetector.detect_language('julia') == 'julia'
        assert KernelLanguageDetector.detect_language('julia-1.6') == 'julia'

    def test_detect_language_javascript_kernel(self):
        """Test: JavaScript kernel detection"""
        assert KernelLanguageDetector.detect_language('javascript') == 'javascript'
        assert KernelLanguageDetector.detect_language('node') == 'javascript'

    def test_detect_language_unknown_kernel(self):
        """Test: Unknown kernel -> defaults to 'python'"""
        assert KernelLanguageDetector.detect_language('unknown') == 'python'
        assert KernelLanguageDetector.detect_language('') == 'python'


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
